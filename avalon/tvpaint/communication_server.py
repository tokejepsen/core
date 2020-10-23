import os
import sys
import time
import subprocess
import asyncio
import socket
import functools
import threading
from queue import Queue
from contextlib import closing

from aiohttp import web
from wsrpc_aiohttp import WebSocketRoute, WebSocketAsync

from ..tools import workfiles
from avalon import api, tvpaint
from pype.api import Logger

log = Logger().get_logger(__name__)


class WebSocketServer:
    def __init__(self):
        self.client = None

        self.app = web.Application()
        self.app.router.add_route("*", "/", WebSocketAsync)

        self.port = self.find_free_port()
        self.websocket_thread = WebsocketServerThread(self, self.port)

    @staticmethod
    def find_free_port():
        with closing(
            socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ) as sock:
            sock.bind(("", 0))
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            port = sock.getsockname()[1]
        return port

    def call(self, func):
        log.debug("websocket.call {}".format(func))
        future = asyncio.run_coroutine_threadsafe(
            func, self.websocket_thread.loop
        )
        result = future.result()
        return result

    def get_client(self):
        """
            Return first connected client to WebSocket
            TODO implement selection by Route
        :return: <WebSocketAsync> client
        """
        clients = WebSocketAsync.get_clients()
        client = None
        if len(clients) > 0:
            key = list(clients.keys())[0]
            client = clients.get(key)

        return client

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
    def __init__(self, module, port):
        super(WebsocketServerThread, self).__init__()
        self.is_running = False
        self.port = port
        self.module = module
        self.loop = None
        self.runner = None
        self.site = None
        self.tasks = []

    def run(self):
        self.is_running = True

        try:
            log.info("Starting websocket server")
            self.loop = asyncio.new_event_loop()  # create new loop for thread
            asyncio.set_event_loop(self.loop)

            self.loop.run_until_complete(self.start_server())

            log.debug(
                "Running Websocket server on URL:"
                " \"ws://localhost:{}\"".format(self.port)
            )

            asyncio.ensure_future(self.check_shutdown(), loop=self.loop)
            self.loop.run_forever()
        except Exception:
            log.warning(
                "Websocket Server service has failed", exc_info=True
            )
        finally:
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


class TVPaintServerStub:
    def __init__(self, websocketserver, client):
        self.websocketserver = websocketserver
        self.client = client

    def close(self):
        self.client.close()


class TVPaintRoute(WebSocketRoute):
    instance = None
    communication_obj = None

    @classmethod
    def set_communication_obj(cls, communication_obj):
        cls.communication_obj = communication_obj

    def init(self, **kwargs):
        # Python __init__ must be return "self".
        # This method might return anything.
        log.debug("someone called Photoshop route")
        self.instance = self
        return kwargs

    # server functions
    async def ping(self):
        log.debug("someone called Photoshop route ping")

    # panel routes for tools
    async def workfiles_route(self):
        log.info("Triggering Workfile tool")
        self._execute_in_main_thread(workfiles.show)

    def _execute_in_main_thread(self, func, *args, **kwargs):
        partial_method = functools.partial(func, *args, **kwargs)
        self.communication_obj.execute_in_main_thread(partial_method)


class Communicator:
    def __init__(self, qt_app, debug_mode=False):
        self.debug_mode = debug_mode

        self.callback_queue = Queue()
        self.qt_app = qt_app

        self.process = None
        self.stub = None
        self.websocket_route = None
        self.websocket_server = None

    def execute_in_main_thread(self, func_to_call_from_main_thread):
        self.callback_queue.put(func_to_call_from_main_thread)

    def main_thread_listen(self):
        # check if host still running
        if self.process.poll() is not None:
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
        self.process = subprocess.Popen(
            host_executable, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        self.websocket_server = WebSocketServer()
        TVPaintRoute.set_communication_obj(self)
        WebSocketAsync.add_route(TVPaintRoute.__name__, TVPaintRoute)
        self.websocket_server.websocket_thread.start()

        log.info("Waiting for client connection")
        while True:
            if not self.debug_mode and self.process.poll() is not None:
                log.debug("Host process is not alive. Exiting")
                self.websocket_server.stop()
                self.qt_app.close()
                return
            try:
                client = self.websocket_server.get_client()
                if client:
                    self.stub = TVPaintServerStub(
                        self.websocket_server, client
                    )
                    break

            except Exception:
                log.debug("Client not conencted yet")
                time.sleep(0.2)

        log.info("Stub has connected")
        api.emit("application.launched")
