"""Websocket server which can communicate with TVPaint."""
import uuid
import json
import copy
import time
import logging
import socket
from queue import Queue
from contextlib import closing
from socketserver import TCPServer

from avalon.vendor import websocket_server

INTERNAL_ERROR_CODE = -32603
PARSE_ERROR_CODE = -32700


def find_free_port():
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("", 0))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        port = sock.getsockname()[1]
    return port


class TVPaintHandler(websocket_server.WebSocketHandler):
    client = None

    def cancel(self):
        """To stop handler's loop."""
        self.keep_alive = False
        self.server._client_left_(self)
        self.client = None


class TVPaintRequestAbstract:
    def __init__(self, id, from_client, params, callback, client):
        self.id = id
        self.from_client = from_client
        self.callback = callback
        self.params = params

        self.client = client

        self._done = False
        self.failed = False

    def process(self):
        pass


class TVPaintClientRequest:
    def process(self):
        try:
            self.result = self.callback(*self.params)
            if self.id is not None:
                self.client.send_result(self.id, self.result)
        except Exception as exc:
            self.failed = True
            self.client.send_error_response(
                self.id, INTERNAL_ERROR_CODE, str(exc)
            )

        self._done = True


class TVPaintClient:
    """Representation of client connected to server.

    Client has 2 immutable atributes `id` and `handler` and `data` which is
    dictionary where additional data to client may be stored.

    Client object behaves as dictionary, all accesses are to `data` attribute.
    Except getting `id`. It is possible to get `id` as attribute or as dict
    item.
    """

    def __init__(self, handler):
        self._handler = handler
        self._id = str(uuid.uuid4())


        self.requests_queue = Queue()
        self.requests_thread = None

        self._data = {}
        handler.client = self

        self.thread_is_running = False
        self.create_request_thread()

    def _requests_queue_processing(self):
        while self.thread_is_running:
            if self.requests_queue.isEmpty():
                time.sleep(0.01)
                continue

            request = self.requests_queue.get()
            request.process()

    def create_request_thread(self):
        thread = threading.Thread(target)

    def __getitem__(self, key):
        if key == "id":
            return self.id
        return self._data[key]

    def __setitem__(self, key, value):
        if key == "id":
            raise TypeError("'id' is not mutable attribute.")
        self._data[key] = value

    def __repr__(self):
        return "Client <{}> ({})".format(self.id, self.address)

    def __iter__(self):
        for item in self.items():
            yield item

    def get(self, key, default=None):
        self._data.get(key, default)

    def items(self):
        return self._data.items()

    def values(self):
        return self._data.values()

    def keys(self):
        return self._data.keys()

    def to_dict(self):
        """Converts client to pure dictionary."""
        return {
            "id": self._id,
            "handler": self._handler,
            "data": copy.deepcopy(self._data)
        }

    @property
    def handler(self):
        return self._handler

    @property
    def server(self):
        return self._handler.server

    @property
    def address(self):
        """Client's adress, should be localhost and random port."""
        return self.handler.client_address

    @property
    def id(self):
        """Uniqu identifier of client."""
        return self._id

    @property
    def data(self):
        return self.data

    def cancel(self):
        """Stops client communication. This is not API method!"""
        self._handler.cancel()
        self._handler = None

    def on_message(self, message):
        try:
            in_data = json.loads(message)
        except Exception:
            data = {
                "error": {"code": PARSE_ERROR_CODE, "message": "Parse error"},
                "id": None
            }
            return self.send_response(data)

    def send_message(self, message):
        self.handler.send_message(message)

    def notify(self, notification, *params):
        if params:
            params = list(params)
        else:
            params = list()

        request_data = {"method": notification, "params": params}
        message = json.dumps(request_data)
        self.send_message(message)

    def send_error_response(self, id, error_code, message):
        data = {
            "id": id,
            "error": {
                "code": error_code,
                "message": message
            }
        }
        self.send_response(data)

    def send_result(self, id, result):
        data = {
            "id": id,
            "result": result
        }
        self.send_response(data)

    def send_response(self, id, data):
        self.send_message(json.dumps(data))


class TVPaintWebsocketServer(websocket_server.WebsocketServer):
    def __init__(
        self, port, host="127.0.0.1", loglevel=logging.WARNING
    ):
        websocket_server.logger.setLevel(loglevel)

        TCPServer.__init__(self, (host, port), TVPaintHandler)
        self.port = self.socket.getsockname()[1]

        self.clients = {}
        self.tvpaint_client = None

        self.waiting_for_response = False

    def _message_received_(self, handler, msg):
        """Recieved message from client."""
        client = handler.client
        client.on_message(msg)

    def _new_client_(self, handler):
        """New client connected."""
        # TODO check if there is only one client as TVPaint can
        #   have only 1 instance.
        client = TVPaintClient(handler)
        self.clients[client.id] = client
        print("New client", client)

    def _client_left_(self, handler):
        client = handler.client
        if not client:
            print("*BUG: Handler does not containt client information.")
            return
        self.clients.pop(client.id, None)

    def _unicast_(self, to_client, msg):
        to_client.handler.send_message(msg)

    def _multicast_(self, msg):
        for client in self.clients.values():
            self._unicast_(client, msg)

    def handler_to_client(self, handler):
        """Find client by handler object."""
        for client in self.clients.values():
            if client.handler == handler:
                return client

    def start(self):
        """Run server in thread."""
        print("Running server {}:{}".format(*self.server_address))
        self.run_forever()

    def stop(self):
        """Stop threaded server."""
        self.server_close()
