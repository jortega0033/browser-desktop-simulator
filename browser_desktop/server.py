"""HTTP server: JSON API plus allowlisted static files (standard library only)."""

from __future__ import annotations

import json
import socket
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote

from . import __version__, storage as st

MAX_BODY = 131072
DRAIN_LIMIT = 1024 * 1024
STATIC_DIR = Path(__file__).resolve().parent / "static"

_HTML = ("index.html", "text/html; charset=utf-8")
STATIC_ROUTES = {
    "/": _HTML,
    "/index.html": _HTML,
    "/static/app.css": ("app.css", "text/css; charset=utf-8"),
    "/static/app.js": ("app.js", "text/javascript; charset=utf-8"),
}

SECURITY_HEADERS = (
    ("Cache-Control", "no-store"),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    (
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; base-uri 'none'; form-action 'self'; "
        "frame-ancestors 'none'",
    ),
)

FILES_PREFIX = "/api/v1/files/"
MUTATING = frozenset({"POST", "PUT", "DELETE", "PATCH"})


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, extra=None, headers=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.extra = extra
        self.headers = headers or ()


def _error_payload(code: str, message: str, extra=None) -> dict:
    payload = {"error": {"code": code, "message": message}}
    if extra:
        payload.update(extra)
    return payload


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = 10
    server_version = "BrowserDesktop/0.1"
    sys_version = ""

    def version_string(self) -> str:
        return self.server_version

    def log_message(self, format, *args):  # noqa: A002 - keep quiet
        pass

    # -- response helpers -------------------------------------------------

    def _send(self, status: int, body: bytes, ctype: str, extra=()):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for key, value in SECURITY_HEADERS:
            self.send_header(key, value)
        self.send_header("Connection", "close")
        for key, value in extra:
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
        self.close_connection = True

    def _send_json(self, status: int, payload: dict, extra=()):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8", extra)

    def _send_api_error(self, err: ApiError):
        self._send_json(
            err.status, _error_payload(err.code, err.message, err.extra), err.headers
        )

    def send_error(self, code, message=None, explain=None):
        """Replace the stock HTML error page (used for malformed requests)."""
        try:
            phrase = HTTPStatus(code).phrase
        except ValueError:
            phrase = "Error"
        self.close_connection = True
        codes = {400: "bad_request", 414: "uri_too_long", 431: "headers_too_large",
                 501: "method_not_allowed", 505: "bad_request"}
        try:
            self._send_json(
                code, _error_payload(codes.get(code, "bad_request"), message or phrase)
            )
        except OSError:
            pass

    # -- request entry points --------------------------------------------

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_PUT(self):
        self._handle("PUT")

    def do_DELETE(self):
        self._handle("DELETE")

    def do_PATCH(self):
        self._handle("PATCH")

    def do_OPTIONS(self):
        self._handle("OPTIONS")

    def do_HEAD(self):
        self._handle("HEAD")

    def _handle(self, method: str):
        self.close_connection = True
        self._unread = 0
        declared = (self.headers.get("Content-Length") or "").strip()
        if declared.isascii() and declared.isdigit() and len(declared) <= 12:
            # If we reject before reading the body, _drain() discards it.
            self._unread = int(declared)
        try:
            self._route(method)
        except ApiError as err:
            self._safe(lambda: self._send_api_error(err))
        except (ConnectionError, TimeoutError, socket.timeout):
            return
        except Exception:  # never leak details to the client
            self._safe(
                lambda: self._send_json(
                    500, _error_payload("internal_error", "Internal server error.")
                )
            )
        finally:
            self._drain()

    @staticmethod
    def _safe(fn):
        try:
            fn()
        except OSError:
            pass

    def _drain(self):
        """Discard an unread request body so closing does not reset the connection."""
        remaining = min(self._unread, DRAIN_LIMIT)
        self._unread = 0
        if remaining <= 0:
            return
        try:
            self.connection.settimeout(0.25)
            while remaining > 0:
                chunk = self.rfile.read(min(65536, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
        except (OSError, ValueError):
            pass

    # -- routing ----------------------------------------------------------

    def _check_origin(self, method: str):
        port = self.server.server_port
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        host = self.headers.get("Host")
        if host is None or host.strip().lower() not in hosts:
            raise ApiError(403, "forbidden_origin", "Request host is not allowed.")
        if method in MUTATING:
            origin = self.headers.get("Origin")
            if origin is not None and origin.strip().lower() not in {
                f"http://127.0.0.1:{port}",
                f"http://localhost:{port}",
            }:
                raise ApiError(403, "forbidden_origin", "Request origin is not allowed.")

    def _route(self, method: str):
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        self._check_origin(method)

        if path in STATIC_ROUTES:
            allowed, action = ("GET",), lambda: self._static(path)
        elif path == "/api/v1/health":
            allowed, action = ("GET",), self._health
        elif path == "/api/v1/files":
            allowed = ("GET", "POST")
            action = self._list_files if method == "GET" else self._create_file
        elif path == "/api/v1/fixtures":
            allowed, action = ("POST",), self._fixtures
        elif path.startswith(FILES_PREFIX) and len(path) > len(FILES_PREFIX):
            allowed = ("GET", "PUT")
            raw = path[len(FILES_PREFIX):]
            action = (
                (lambda: self._get_file(raw))
                if method == "GET"
                else (lambda: self._put_file(raw))
            )
        else:
            raise ApiError(404, "not_found", "No such resource.")

        if method not in allowed:
            raise ApiError(
                405,
                "method_not_allowed",
                f"Method {method} is not allowed here.",
                headers=(("Allow", ", ".join(allowed)),),
            )
        try:
            action()
        except st.ValidationError as err:
            raise ApiError(400, err.code, err.message) from None
        except st.NotFound:
            raise ApiError(404, "not_found", "File not found.") from None
        except st.AlreadyExists:
            raise ApiError(409, "already_exists", "A file with that name already exists.") from None
        except st.FileLimitReached:
            raise ApiError(
                409, "file_limit", f"At most {st.MAX_FILES} files are allowed."
            ) from None
        except st.Conflict as err:
            raise ApiError(
                409,
                "conflict",
                "The file changed since you opened it.",
                extra={"current": err.current},
            ) from None

    # -- body handling ----------------------------------------------------

    def _read_json(self, keys: set) -> dict:
        if self.headers.get("Transfer-Encoding") is not None:
            raise ApiError(411, "length_required", "Chunked bodies are not supported.")
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ApiError(411, "length_required", "Content-Length is required.")
        raw_length = raw_length.strip()
        if not (raw_length.isascii() and raw_length.isdigit()) or len(raw_length) > 12:
            raise ApiError(400, "invalid_request", "Invalid Content-Length.")
        length = int(raw_length)
        if length > MAX_BODY:
            self._unread = length
            raise ApiError(
                413, "payload_too_large", f"Request body exceeds {MAX_BODY} bytes."
            )
        self._unread = length

        ctype = self.headers.get("Content-Type", "")
        parts = [p.strip().lower() for p in ctype.split(";")]
        if parts[0] != "application/json" or any(
            p and p not in ("charset=utf-8", 'charset="utf-8"') for p in parts[1:]
        ):
            raise ApiError(
                415, "unsupported_media_type", "Content-Type must be application/json."
            )

        body = self.rfile.read(length) if length else b""
        self._unread = 0
        if len(body) != length:
            raise ApiError(400, "invalid_request", "Request body was truncated.")
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError):
            raise ApiError(400, "invalid_request", "Body must be valid UTF-8 JSON.") from None
        if not isinstance(data, dict) or set(data.keys()) != keys:
            raise ApiError(
                400,
                "invalid_request",
                "Body must be a JSON object with exactly the keys: "
                + ", ".join(sorted(keys)) + ".",
            )
        return data

    # -- endpoints --------------------------------------------------------

    def _static(self, path: str):
        filename, ctype = STATIC_ROUTES[path]
        try:
            body = (STATIC_DIR / filename).read_bytes()
        except OSError:
            raise ApiError(404, "not_found", "No such resource.") from None
        self._send(200, body, ctype)

    def _health(self):
        self._send_json(
            200,
            {
                "status": "ok",
                "version": __version__,
                "schema_version": self.server.storage.schema_version(),
            },
        )

    def _list_files(self):
        self._send_json(200, {"files": self.server.storage.list_files()})

    def _create_file(self):
        data = self._read_json({"name", "text"})
        name, text = data["name"], data["text"]
        if not isinstance(name, str):
            raise ApiError(400, "invalid_name", "name must be a string.")
        created = self.server.storage.create_file(name, text)
        self._send_json(
            201, created, (("Location", FILES_PREFIX + quote(name, safe="")),)
        )

    def _decode_name(self, raw: str) -> str:
        try:
            name = unquote(raw, errors="strict")
        except UnicodeDecodeError:
            raise st.ValidationError("invalid_name", "File name is not valid UTF-8.") from None
        return st.validate_name(name)

    def _get_file(self, raw: str):
        name = self._decode_name(raw)
        self._send_json(200, self.server.storage.get_file(name))

    def _put_file(self, raw: str):
        data = self._read_json({"text", "base_revision"})
        name = self._decode_name(raw)
        updated = self.server.storage.update_file(
            name, data["text"], data["base_revision"]
        )
        self._send_json(200, updated)

    def _fixtures(self):
        self._read_json(set())
        storage = self.server.storage
        created = [st.FIXTURE_NAME] if storage.ensure_fixture() else []
        self._send_json(200, {"created": created, "files": storage.list_files()})


class DesktopServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 64
    # On Windows SO_REUSEADDR would allow binding a port already in use.
    allow_reuse_address = sys.platform != "win32"

    def __init__(self, address, handler, storage: st.Storage):
        self.storage = storage
        super().__init__(address, handler)

    def server_close(self):
        super().server_close()
        self.storage.close()


def create_server(data_dir, port: int):
    """Open storage and bind 127.0.0.1:port. Returns (server, actual_port).

    Raises storage.StorageError for data-dir/schema problems and OSError if
    the port cannot be bound. The caller runs serve_forever() (e.g. in a
    thread) and later calls shutdown() and server_close().
    """
    storage = st.Storage(data_dir)
    try:
        server = DesktopServer(("127.0.0.1", port), Handler, storage)
    except BaseException:
        storage.close()
        raise
    return server, server.server_address[1]
