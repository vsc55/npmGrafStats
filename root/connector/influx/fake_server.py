#!/usr/bin/env python3
"""Fake InfluxDB server for testing purposes."""
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import socket


class FakeHTTPServer(HTTPServer):
    """HTTPServer that knows its parent FakeInfluxServer."""
    def __init__(self, server_address, handler_class, parent_server):
        super().__init__(server_address, handler_class)
        self.parent = parent_server  # "real" server reference


class FakeInfluxHandler(BaseHTTPRequestHandler):
    """ A simple HTTP handler that simulates basic InfluxDB endpoints. """

    def do_GET(self): # pylint: disable=invalid-name
        """Handle GET requests."""
        if self.path == "/ping":
            self.send_response(204)  # equivalent to InfluxDB /ping
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self): # pylint: disable=invalid-name
        """Handle POST requests."""
        if self.path.startswith("/api/v2/write"):
            # ready and discard the body
            length = int(self.headers.get("Content-Length", 0))
            _ = self.rfile.read(length)
            self.send_response(204)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args): # pylint: disable=useless-return, redefined-builtin
        """Override to disable logging."""
        if getattr(self.server, "parent", None) and self.server.parent.debug:
            super().log_message(format, *args)
        return


class FakeInfluxServer:
    """ A fake InfluxDB server for testing purposes. """
    def __init__(
            self, host: str = "127.0.0.1", port: int | None = None, debug: bool = False
    ) -> None:
        self.debug = debug
        self.host = host
        self.port = port  # if None, choose a free one on start
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def _log(self, message: str) -> None:
        if self.debug:
            print(f"[FakeInfluxServer] {message}", flush=True)

    @staticmethod
    def _get_free_port(host: str) -> int:
        sock = socket.socket()
        sock.bind((host, 0))
        _, port = sock.getsockname()
        sock.close()
        return port

    @property
    def url(self) -> str:
        """Return the URL of the fake InfluxDB server."""
        if self.port is None or self._server is None:
            raise RuntimeError("FakeInfluxServer is not started yet.")
        return f"http://{self.host}:{self.port}"

    @property
    def is_running(self) -> bool:
        """Check if the server is running."""
        return self._server is not None

    @property
    def get_port(self) -> int:
        """Get the port the server is running on."""
        if self.port is None or self._server is None:
            raise RuntimeError("FakeInfluxServer is not started yet.")
        return self.port

    @property
    def get_host(self) -> str:
        """Get the host the server is running on."""
        return self.host

    def start(self) -> None:
        """Start the fake InfluxDB server."""
        self._log("Starting server...")
        if self._server is not None:
            self._log("Server is already running.")
            return

        if self.port is None:
            self._log("No port specified, selecting a free port.")
            self.port = self._get_free_port(self.host)

        self._server = FakeHTTPServer(
            (self.host, self.port),
            FakeInfluxHandler,
            parent_server=self,
        )
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
        )
        self._thread.start()
        self._log(f"Server started at {self.url}")

    def stop(self) -> None:
        """Stop the fake InfluxDB server."""
        self._log("Stopping server...")
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
            self._thread = None
            self._log("Server stopped.")
        else:
            self._log("Server is not running.")

    # for use with "with FakeInfluxServer() as s:"
    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.stop()
