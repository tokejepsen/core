# -*- coding: utf-8 -*-
"""Server-side implementation of Toon Boon Harmony communication."""
import socket
import logging
import json
import traceback
import importlib
import functools
import time
from datetime import datetime

from . import lib


class Server(object):
    """Class for communication with Toon Boon Harmony.

    Attributes:
        connection (Socket): connection holding object.
        recieved (str): recieved data buffer.any(iterable)
        port (int): port number.
        message_id (int): index of last message going out.
        queue (dict): dictionary holding queue of incoming messages.

    """

    def __init__(self, port):
        """Constructor."""
        self.connection = None
        self.received = ""
        self.port = port
        self.message_id = 1

        # Setup logging.
        self.log = logging.getLogger(__name__)
        self.log.setLevel(logging.DEBUG)

        # Create a TCP/IP socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Bind the socket to the port
        server_address = ("localhost", port)
        self.log.debug("Starting up on {}".format(server_address))
        self.socket.bind(server_address)

        # Listen for incoming connections
        self.socket.listen(1)
        self.queue = {}

    def process_request(self, request):
        """Process incoming request.

        Args:
            request (dict): {
                "module": (str),  # Module of method.
                "method" (str),  # Name of method in module.
                "args" (list),  # Arguments to pass to method.
                "kwargs" (dict),  # Keywork arguments to pass to method.
                "reply" (bool),  # Optional wait for method completion.
            }
        """
        timestamp = datetime.now().strftime("%H:%M:%S.%f")
        self.log.debug(
            "Processing request [{}]: {}".format(timestamp, request))

        try:
            module = importlib.import_module(request["module"])
            method = getattr(module, request["method"])

            args = request.get("args", [])
            kwargs = request.get("kwargs", {})
            partial_method = functools.partial(method, *args, **kwargs)

            lib.execute_in_main_thread(partial_method)
        except Exception:
            self.log.error(traceback.format_exc())

    def receive(self):
        """Receives data from `self.connection`.

        When the data is a json serializable string, a reply is sent then
        processing of the request.
        """
        current_time = time.time()
        while True:

            # Receive the data in small chunks and retransmit it
            request = None
            while True:
                time.sleep(0.1)
                if time.time() > current_time + 30:
                    self.log.error("Connection timeout.")
                    break
                if self.connection is None:
                    break

                data = self.connection.recv(4096)
                if data:
                    self.received += data.decode("utf-8")
                    current_time = time.time()
                else:
                    break

                timestamp = datetime.now().strftime("%H:%M:%S.%f")
                self.log.debug(
                    "Received [{}]: {}".format(timestamp, self.received))

                try:
                    request = json.loads(self.received)
                    break
                except json.decoder.JSONDecodeError:
                    pass

            if request is None:
                break

            self.received = ""
            timestamp = datetime.now().strftime("%H:%M:%S.%f")
            self.log.debug("Request [{}]: {}".format(timestamp, request))
            if "message_id" in request.keys():
                self.log.debug("--- storing request as {}".format(
                    request["message_id"]))
                self.queue[request["message_id"]] = request
            if "reply" not in request.keys():
                request["reply"] = True
                self.log.debug("Sending reply ...")
                self._send(json.dumps(request))
                self.log.debug("Processing request ...")
                self.process_request(request)

                if "message_id" in request.keys():
                    try:
                        self.log.debug("Removing from queue {}".format(
                            request["message_id"]))
                        del self.queue[request["message_id"]]
                    except IndexError:
                        self.log.debug("{} is no longer in queue".format(
                            request["message_id"]))
            else:
                self.log.debug("Recieved data was just reply.")

    def start(self):
        """Entry method for server.

        Waits for a connection on `self.port` before going into listen mode.
        """
        # Wait for a connection
        self.log.debug("Waiting for a connection.")
        self.connection, client_address = self.socket.accept()

        self.log.debug("Connection from: {}".format(client_address))

        self.receive()

    def stop(self):
        """Shutdown socket server gracefully."""
        self.log.debug("Shutting down server.")
        if self.connection is None:
            self.log.debug("Connect to shutdown.")
            socket.socket(
                socket.AF_INET, socket.SOCK_STREAM
            ).connect(("localhost", self.port))

        self.connection.close()
        self.connection = None

        self.socket.close()

    def _send(self, message):
        """Send a message to Harmony.

        Args:
            message (str): Data to send to Harmony.
        """
        # Wait for a connection.
        while not self.connection:
            pass

        timestamp = datetime.now().strftime("%H:%M:%S.%f")
        self.log.debug(
            "Sending [{}][{}]: {}".format(self.message_id, timestamp, message))
        self.connection.sendall(message.encode("utf-8"))
        self.message_id += 1

    def send(self, request):
        """Send a request in dictionary to Harmony.

        Waits for a reply from Harmony.

        Args:
            request (dict): Data to send to Harmony.
        """
        request["message_id"] = self.message_id
        self._send(json.dumps(request))
        if request.get("reply"):
            self.log.debug("sent reply, not waiting for anything.")
            return None
        result = None
        current_time = time.time()
        try_index = 1
        while True:
            time.sleep(0.1)
            if time.time() > current_time + 30:
                timestamp = datetime.now().strftime("%H:%M:%S.%f")
                self.log.error(("[{}][{}] No reply from Harmony in 30s. "
                                "Retrying {}").format(request["message_id"],
                                                      timestamp, try_index))
                try_index += 1
                current_time = time.time()
            if try_index > 4:
                break
            try:
                result = self.queue[request["message_id"]]
                self.log.debug(("  - got request id {}, "
                                "removing from queue").format(
                                    request["message_id"]))
                del self.queue[request["message_id"]]
                break
            except KeyError:
                # response not in recieved queue yey
                pass
            try:
                result = json.loads(self.received)
                break
            except json.decoder.JSONDecodeError:
                pass

        self.received = ""

        return result
