import os
import sys
import time
import subprocess
import asyncio
import socket
import threading
from queue import Queue
from contextlib import closing


from ..tools import workfiles
from avalon import api, tvpaint
from pype.api import Logger

from aiohttp import web
from aiohttp_json_rpc import JsonRpc
from aiohttp_json_rpc.protocol import (
    encode_request, encode_error, decode_msg, JsonRpcMsgTyp
)
from aiohttp_json_rpc.exceptions import RpcError

log = Logger().get_logger(__name__)


class CommunicatorWrapper:
    # TODO add logs and exceptions
    communicator = None
    _connected_client = None

    @classmethod
    def create_communicator(cls, *args, **kwargs):
        if not cls.communicator:
            cls.communicator = Communicator(*args, **kwargs)
        return cls.communicator

    @classmethod
    def _client(cls):
        if not cls.communicator:
            log.warning("Communicator object was not created yet.")
            return None

        if not cls.communicator.websocket_rpc:
            log.warning("Communicator's server did not start yet.")
            return None

        for client in cls.communicator.websocket_rpc.clients:
            if not client.ws.closed:
                return client
        log.warning("Client is not yet connected to Communicator.")
        return None

    @classmethod
    def client(cls):
        if not cls._connected_client or cls._connected_client.ws.closed:
            cls._connected_client = cls._client()
        return cls._connected_client

    @classmethod
    def send_request(cls, method, params=[], client=None):
        if client is None:
            client = cls.client()

        if not client:
            return

        return cls.communicator.websocket_rpc.send_request(
            client, method, params
        )

    @classmethod
    def send_notification(cls, method, params=[], client=None):
        if client is None:
            client = cls.client()

        if not client:
            return

        cls.communicator.websocket_rpc.send_notification(
            client, method, params
        )


class WebSocketServer:
    def __init__(self):
        self.client = None

        self.loop = asyncio.new_event_loop()
        self.app = web.Application(loop=self.loop)
        self.port = self.find_free_port()
        self.websocket_thread = WebsocketServerThread(
            self, self.port, loop=self.loop
        )

    @property
    def server_is_running(self):
        return self.websocket_thread.server_is_running

    def add_route(self, *args, **kwargs):
        self.app.router.add_route(*args, **kwargs)

    @staticmethod
    def find_free_port():
        with closing(
            socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ) as sock:
            sock.bind(("", 0))
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            port = sock.getsockname()[1]
        return port

    def start(self):
        self.websocket_thread.start()

    def stop(self):
        try:
            log.debug("Stopping websocket server")
            self.websocket_thread.is_running = False
            self.websocket_thread.stop()
        except Exception:
            log.warning(
                "Error has happened during Killing websocket server",
                exc_info=True
            )


class WebsocketServerThread(threading.Thread):
    """ Listener for websocket rpc requests.

        It would be probably better to "attach" this to main thread (as for
        example Harmony needs to run something on main thread), but currently
        it creates separate thread and separate asyncio event loop
    """
    def __init__(self, module, port, loop):
        super(WebsocketServerThread, self).__init__()
        self.is_running = False
        self.server_is_running = False
        self.port = port
        self.module = module
        self.loop = loop
        self.runner = None
        self.site = None
        self.tasks = []

    def run(self):
        self.is_running = True

        try:
            log.info("Starting websocket server")

            self.loop.run_until_complete(self.start_server())

            log.debug(
                "Running Websocket server on URL:"
                " \"ws://localhost:{}\"".format(self.port)
            )

            asyncio.ensure_future(self.check_shutdown(), loop=self.loop)

            self.server_is_running = True
            self.loop.run_forever()

        except Exception:
            log.warning(
                "Websocket Server service has failed", exc_info=True
            )
        finally:
            self.server_is_running = False
            # optional
            self.loop.close()

        self.is_running = False
        log.info("Websocket server stopped")

    async def start_server(self):
        """ Starts runner and TCPsite """
        self.runner = web.AppRunner(self.module.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "localhost", self.port)
        await self.site.start()

    def stop(self):
        """Sets is_running flag to false, 'check_shutdown' shuts server down"""
        self.is_running = False

    async def check_shutdown(self):
        """ Future that is running and checks if server should be running
            periodically.
        """
        while self.is_running:
            while self.tasks:
                task = self.tasks.pop(0)
                log.debug("waiting for task {}".format(task))
                await task
                log.debug("returned value {}".format(task.result))

            await asyncio.sleep(0.5)

        log.debug("Starting shutdown")
        await self.site.stop()
        log.debug("Site stopped")
        await self.runner.cleanup()
        log.debug("Runner stopped")
        tasks = [
            task for task in asyncio.all_tasks()
            if task is not asyncio.current_task()
        ]
        list(map(lambda task: task.cancel(), tasks))  # cancel all the tasks
        results = await asyncio.gather(*tasks, return_exceptions=True)
        log.debug(f"Finished awaiting cancelled tasks, results: {results}...")
        await self.loop.shutdown_asyncgens()
        # to really make sure everything else has time to stop
        await asyncio.sleep(0.07)
        self.loop.stop()


class TVPaintRpc(JsonRpc):
    def __init__(self, communication_obj, route_name="", **kwargs):
        super().__init__(**kwargs)
        self.requests_ids = collections.defaultdict(lambda: 0)
        self.waiting_requests = collections.defaultdict(list)
        self.responses = collections.defaultdict(list)

        self.route_name = route_name
        self.communication_obj = communication_obj
        # Register methods
        self.add_methods(
            (route_name, self.workfiles_route)
        )

    async def _handle_rpc_msg(self, http_request, raw_msg):
        # This is duplicated code from super but there is no way how to do it
        # to be able handle server->client requests
        remote = http_request.remote
        if remote in self.waiting_requests:
            try:
                msg = decode_msg(raw_msg.data)

            except RpcError as error:
                await self._ws_send_str(http_request, encode_error(error))
                return

            if (
                msg.type == JsonRpcMsgTyp.RESULT
                and msg.data["id"] in self.waiting_requests[remote]
            ):
                self.responses[remote].append(msg)
                return

        return await super()._handle_rpc_msg(http_request, raw_msg)

    def client_connected(self):
        # TODO This is poor check. Add check it is client from TVPaint
        if self.clients:
            return True
        return False

    # Panel routes for tools
    async def workfiles_route(self):
        log.info("Triggering Workfile tool")
        item = MainThreadItem(workfiles.show)
        result = self._execute_in_main_thread(item)
        return result

    def _execute_in_main_thread(self, item):
        return self.communication_obj.execute_in_main_thread(item)

    def send_notification(self, client, method, params=[]):
        future = asyncio.run_coroutine_threadsafe(
            client.ws.send_str(encode_request(method, params=params)),
            loop=self.loop
        )
        result = future.result()

    def send_request(self, client, method, params=[]):
        client_remote = client.remote
        request_id = self.requests_ids[client_remote]
        self.requests_ids[client_remote] += 1
        self.waiting_requests[client_remote].append(request_id)
        future = asyncio.run_coroutine_threadsafe(
            client.ws.send_str(encode_request(method, request_id, params)),
            loop=self.loop
        )
        result = future.result()

        response = None
        while True:
            # TODO raise exception?
            if client.ws.closed:
                return None

            for _response in self.responses[client_remote]:
                _id = _response.data.get("id")
                if _id == request_id:
                    response = _response
                    break

        if response is None:
            raise Exception("Connection closed")

        error = response.data.get("error")
        result = response.data.get("result")
        if error:
            raise Exception("Error happened: {}".format(error))
        return result


class MainThreadItem:
    not_set = object()
    sleep_time = 0.1

    def __init__(self, callback, *args, **kwargs):
        self.done = False
        self.exc_info = self.not_set
        self.result = self.not_set
        self.callback = callback
        self.args = args
        self.kwargs = kwargs

    def handle_result(self):
        if self.exc_info is self.not_set:
            return self.result
        raise self.exc_info

    def wait(self):
        while not self.done:
            time.sleep(self.sleep_time)
        return self.handle_result()

    async def asyncio_wait(self):
        while not self.done:
            await asyncio.sleep(self.sleep_time)
        return self.handle_result()


class Communicator:
    def __init__(self, qt_app, debug_mode=False):
        self.debug_mode = debug_mode

        self.callback_queue = Queue()
        self.qt_app = qt_app

        self.process = None
        self.websocket_route = None
        self.websocket_server = None
        self.websocket_rpc = None

    def execute_in_main_thread(self, main_thread_item):
        self.callback_queue.put(main_thread_item)
        return main_thread_item.wait()

    def main_thread_listen(self):
        # check if host still running
        if not self.debug_mode and self.process.poll() is not None:
            self.websocket_server.stop()
            return self.qt_app.quit()

        if self.callback_queue.empty():
            return None
        return self.callback_queue.get()

    def launch(self, host_executable):
        log.info("Installing TVPaint implementation")
        api.install(tvpaint)

        # Launch TVPaint and the websocket server.
        log.info("Launching TVPaint")
        self.websocket_server = WebSocketServer()
        self.websocket_rpc = TVPaintRpc(self, loop=self.websocket_server.loop)

        os.environ["WEBSOCKET_URL"] = "ws://localhost:{}".format(
            self.websocket_server.port
        )
        self.websocket_server.add_route(
            "*", "/", self.websocket_rpc.handle_request
        )
        log.info("Added request handler for url: {}".format(
            os.environ["WEBSOCKET_URL"]
        ))

        self.websocket_server.start()
        # Make sure RPC is using same loop as websocket server
        while not self.websocket_server.server_is_running:
            time.sleep(0.1)

        # Start TVPaint when server is running
        if not self.debug_mode:
            self.process = subprocess.Popen(
                host_executable,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=os.environ
            )

        log.info("Waiting for client connection")
        while True:
            if not self.debug_mode and self.process.poll() is not None:
                log.debug("Host process is not alive. Exiting")
                self.websocket_server.stop()
                self.qt_app.quit()
                return

            if self.websocket_rpc.client_connected():
                log.info("Client has connected")
                break
            time.sleep(0.1)

        api.emit("application.launched")

    def stop(self):
        log.info("Stopping communication")
        self.websocket_server.stop()
        self.qt_app.quit()
