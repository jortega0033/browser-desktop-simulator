import contextlib
import http.client
import io
import json
import socket
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from browser_desktop import cli
from browser_desktop import server as srv
from browser_desktop import storage as st

FIXTURE = b"orbit alpha ready\ndock lights green\norbit beta synced\n"


class Resp:
    def __init__(self, status, headers, body):
        self.status = status
        self.headers = headers
        self.body = body

    def json(self):
        return json.loads(self.body.decode("utf-8"))


class Running:
    """A server on an ephemeral port serving a given data dir."""

    def __init__(self, data_dir):
        self.server, self.port = srv.create_server(str(data_dir), 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(10)

    def request(self, method, path, body=None, headers=None, raw=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            hdrs = dict(headers or {})
            data = raw
            if body is not None:
                data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            if data is not None:
                hdrs.setdefault("Content-Type", "application/json")
            conn.request(method, path, body=data, headers=hdrs)
            r = conn.getresponse()
            return Resp(r.status, r.headers, r.read())
        finally:
            conn.close()

    def raw_socket(self, payload: bytes) -> bytes:
        with socket.create_connection(("127.0.0.1", self.port), timeout=10) as s:
            s.sendall(payload)
            chunks = []
            while True:
                try:
                    c = s.recv(65536)
                except ConnectionResetError:
                    break
                if not c:
                    break
                chunks.append(c)
        return b"".join(chunks)


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data_dir = Path(self._tmp.name) / "data"
        self.app = Running(self.data_dir)
        self.addCleanup(self._stop_app)

    def _stop_app(self):
        if self.app is not None:
            self.app.stop()
            self.app = None

    def req(self, *a, **kw):
        return self.app.request(*a, **kw)

    def create(self, name="a.txt", text="hello"):
        r = self.req("POST", "/api/v1/files", {"name": name, "text": text})
        self.assertEqual(r.status, 201, r.body)
        return r.json()

    def assertError(self, resp, status, code):
        self.assertEqual(resp.status, status, resp.body)
        self.assertEqual(resp.json()["error"]["code"], code)
        self.assertIn("message", resp.json()["error"])


class HealthAndStaticTests(ApiTestCase):
    def test_health(self):
        r = self.req("GET", "/api/v1/health")
        self.assertEqual(r.status, 200)
        self.assertEqual(
            r.json(), {"status": "ok", "version": "0.1.0", "schema_version": 1}
        )
        self.assertEqual(r.headers.get("Cache-Control"), "no-store")
        self.assertTrue(r.headers.get("Content-Type").startswith("application/json"))

    def test_security_headers_everywhere(self):
        paths = ["/api/v1/health", "/nope", "/api/v1/files/..", "/"]
        for p in paths:
            r = self.req("GET", p)
            with self.subTest(path=p):
                self.assertEqual(r.headers.get("X-Content-Type-Options"), "nosniff")
                self.assertEqual(r.headers.get("Referrer-Policy"), "no-referrer")
                csp = r.headers.get("Content-Security-Policy")
                self.assertIn("default-src 'self'", csp)
                self.assertIn("frame-ancestors 'none'", csp)
                self.assertEqual(r.headers.get("Cache-Control"), "no-store")

    def test_static_allowlist_serves_existing_assets(self):
        cases = {
            "/": ("index.html", "text/html"),
            "/index.html": ("index.html", "text/html"),
            "/static/app.css": ("app.css", "text/css"),
            "/static/app.js": ("app.js", "text/javascript"),
        }
        for path, (fname, ctype) in cases.items():
            f = srv.STATIC_DIR / fname
            if not f.is_file():
                continue  # written by the interface engineer
            with self.subTest(path=path):
                r = self.req("GET", path)
                self.assertEqual(r.status, 200)
                self.assertTrue(r.headers.get("Content-Type").startswith(ctype))
                self.assertEqual(r.body, f.read_bytes())

    def test_static_routes_cover_exactly_the_allowlist(self):
        self.assertEqual(
            set(srv.STATIC_ROUTES),
            {"/", "/index.html", "/static/app.css", "/static/app.js"},
        )

    def test_traversal_and_unknown_paths_are_404(self):
        for path in [
            "/static/../storage.py",
            "/static/../x",
            "/%2e%2e/",
            "/static/%2e%2e%2fstorage.py",
            "/static/%2e%2e/storage.py",
            "/static/app.css/",
            "/static/",
            "/static",
            "/static/index.html",
            "/browser_desktop/server.py",
            "/..%5cserver.py",
            "/index.html/extra",
            "/api/v1/",
            "/api/v1/unknown",
            "/api/v1/files/",
        ]:
            with self.subTest(path=path):
                self.assertError(self.req("GET", path), 404, "not_found")

    def test_query_string_ignored_for_routing(self):
        self.assertEqual(self.req("GET", "/api/v1/health?x=1").status, 200)

    def test_method_not_allowed_and_options(self):
        r = self.req("OPTIONS", "/api/v1/files")
        self.assertError(r, 405, "method_not_allowed")
        self.assertEqual(r.headers.get("Allow"), "GET, POST")
        r = self.req("POST", "/api/v1/health", {})
        self.assertError(r, 405, "method_not_allowed")
        self.assertEqual(r.headers.get("Allow"), "GET")
        self.assertError(self.req("DELETE", "/api/v1/files/a"), 405, "method_not_allowed")
        self.assertError(self.req("POST", "/"), 405, "method_not_allowed")
        self.assertError(self.req("GET", "/api/v1/fixtures"), 405, "method_not_allowed")

    def test_no_cors_headers(self):
        for r in [
            self.req("GET", "/api/v1/health"),
            self.req("OPTIONS", "/api/v1/files", headers={"Origin": "http://evil.example"}),
            self.req("GET", "/api/v1/files", headers={"Origin": f"http://127.0.0.1:{self.app.port}"}),
        ]:
            self.assertFalse(
                [k for k in r.headers.keys() if k.lower().startswith("access-control-")]
            )


class FileApiTests(ApiTestCase):
    def test_empty_list(self):
        self.assertEqual(self.req("GET", "/api/v1/files").json(), {"files": []})

    def test_create_list_get_update(self):
        c = self.create("b.txt", "café\r\nline")
        self.assertEqual(c["revision"], 1)
        self.assertEqual(c["size"], len("café\r\nline".encode()))
        self.create("a.txt", "x")
        r = self.req("POST", "/api/v1/files", {"name": "c.txt", "text": ""})
        self.assertEqual(r.headers.get("Location"), "/api/v1/files/c.txt")
        names = [f["name"] for f in self.req("GET", "/api/v1/files").json()["files"]]
        self.assertEqual(names, ["a.txt", "b.txt", "c.txt"])
        listed = self.req("GET", "/api/v1/files").json()["files"][1]
        self.assertEqual(set(listed), {"name", "size", "revision", "updated_at"})
        g = self.req("GET", "/api/v1/files/b.txt").json()
        self.assertEqual(g["text"], "café\r\nline")
        self.assertEqual(set(g), {"name", "text", "revision", "size", "updated_at"})
        u = self.req("PUT", "/api/v1/files/b.txt", {"text": "new", "base_revision": 1})
        self.assertEqual(u.status, 200)
        self.assertEqual((u.json()["revision"], u.json()["text"]), (2, "new"))
        self.assertEqual(self.req("GET", "/api/v1/files/b.txt").json()["revision"], 2)

    def test_get_missing_and_invalid_name(self):
        self.assertError(self.req("GET", "/api/v1/files/missing"), 404, "not_found")
        self.assertError(self.req("GET", "/api/v1/files/.hidden"), 400, "invalid_name")
        self.assertError(self.req("GET", "/api/v1/files/" + "x" * 65), 400, "invalid_name")

    def test_percent_decoded_once_then_validated(self):
        self.create("launch-notes.txt", "x")
        self.assertEqual(self.req("GET", "/api/v1/files/launch%2Dnotes.txt").status, 200)
        for p in ["/api/v1/files/%2e%2e", "/api/v1/files/%2Fetc", "/api/v1/files/a%252e",
                  "/api/v1/files/a%2e%2eb", "/api/v1/files/a/b", "/api/v1/files/%ff",
                  "/api/v1/files/a%00", "/api/v1/files/a%20b"]:
            with self.subTest(path=p):
                self.assertError(self.req("GET", p), 400, "invalid_name")

    def test_put_missing_is_404(self):
        r = self.req("PUT", "/api/v1/files/ghost", {"text": "x", "base_revision": 1})
        self.assertError(r, 404, "not_found")

    def test_conflict_returns_current(self):
        self.create("a.txt", "v1")
        self.req("PUT", "/api/v1/files/a.txt", {"text": "v2", "base_revision": 1})
        r = self.req("PUT", "/api/v1/files/a.txt", {"text": "mine", "base_revision": 1})
        self.assertError(r, 409, "conflict")
        cur = r.json()["current"]
        self.assertEqual((cur["name"], cur["text"], cur["revision"]), ("a.txt", "v2", 2))
        self.assertEqual(set(cur), {"name", "text", "revision", "size", "updated_at"})
        # Keep-mine flow: re-save using the current revision.
        r = self.req("PUT", "/api/v1/files/a.txt", {"text": "mine", "base_revision": 2})
        self.assertEqual(r.json()["revision"], 3)

    def test_duplicate_create(self):
        self.create("a.txt")
        r = self.req("POST", "/api/v1/files", {"name": "a.txt", "text": "other"})
        self.assertError(r, 409, "already_exists")
        self.assertEqual(self.req("GET", "/api/v1/files/a.txt").json()["text"], "hello")

    def test_create_validation(self):
        bad_names = ["", "a/b", "..", "a..b", ".x", "x" * 65, "a b", 5, None, ["a"]]
        for n in bad_names:
            with self.subTest(name=n):
                self.assertError(
                    self.req("POST", "/api/v1/files", {"name": n, "text": "t"}),
                    400, "invalid_name")
        for t in [5, None, ["x"], "nul\x00here"]:
            with self.subTest(text=t):
                self.assertError(
                    self.req("POST", "/api/v1/files", {"name": "ok", "text": t}),
                    400, "invalid_request")
        self.assertError(
            self.req("POST", "/api/v1/files", {"name": "ok", "text": "x" * 65537}),
            400, "text_too_large")
        self.assertEqual(
            self.req("POST", "/api/v1/files", {"name": "ok", "text": "x" * 65536}).status, 201)
        # lone surrogate escape cannot be stored as UTF-8
        r = self.req("POST", "/api/v1/files", raw=b'{"name":"s","text":"\\ud800"}')
        self.assertError(r, 400, "invalid_request")
        self.assertEqual(self.req("GET", "/api/v1/files").json()["files"][0]["name"], "ok")

    def test_shape_validation(self):
        bodies = [
            {}, {"name": "a"}, {"text": "a"},
            {"name": "a", "text": "b", "extra": 1},
        ]
        for b in bodies:
            with self.subTest(body=b):
                self.assertError(self.req("POST", "/api/v1/files", b), 400, "invalid_request")
        for raw in [b"[]", b'"str"', b"null", b"5", b"{bad", b"", b"\xff\xfe",
                    b'{"name":"a","text":"b"} trailing']:
            with self.subTest(raw=raw):
                self.assertError(
                    self.req("POST", "/api/v1/files", raw=raw), 400, "invalid_request")
        self.create("a.txt")
        for b in [{"text": "x"}, {"base_revision": 1}, {"text": "x", "base_revision": 1, "name": "a.txt"}]:
            with self.subTest(body=b):
                self.assertError(
                    self.req("PUT", "/api/v1/files/a.txt", b), 400, "invalid_request")
        for rev in [0, -1, True, False, "1", 1.5, None, [1]]:
            with self.subTest(rev=rev):
                self.assertError(
                    self.req("PUT", "/api/v1/files/a.txt", {"text": "x", "base_revision": rev}),
                    400, "invalid_request")
        self.assertEqual(self.req("GET", "/api/v1/files/a.txt").json()["revision"], 1)

    def test_put_text_limits(self):
        self.create("a.txt")
        r = self.req("PUT", "/api/v1/files/a.txt", {"text": "é" * 32769, "base_revision": 1})
        self.assertError(r, 400, "text_too_large")
        r = self.req("PUT", "/api/v1/files/a.txt", {"text": "a\x00", "base_revision": 1})
        self.assertError(r, 400, "invalid_request")
        self.assertEqual(self.req("GET", "/api/v1/files/a.txt").json()["text"], "hello")

    def test_file_limit(self):
        storage = self.app.server.storage
        for i in range(st.MAX_FILES):
            storage.create_file(f"f{i}", "")
        r = self.req("POST", "/api/v1/files", {"name": "extra", "text": ""})
        self.assertError(r, 409, "file_limit")
        r = self.req("POST", "/api/v1/fixtures", {})
        self.assertError(r, 409, "file_limit")

    def test_concurrent_writers_single_winner(self):
        self.create("a.txt", "base")
        n = 8
        barrier = threading.Barrier(n)
        statuses = []
        lock = threading.Lock()

        def worker(i):
            barrier.wait()
            try:
                status = self.req("PUT", "/api/v1/files/a.txt", {"text": f"w{i}", "base_revision": 1}).status
            except Exception as exc:  # recorded so the assertion shows the cause
                status = repr(exc)
            with lock:
                statuses.append(status)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        self.assertEqual(sorted(statuses, key=str), sorted([200] + [409] * (n - 1), key=str))
        self.assertEqual(self.req("GET", "/api/v1/files/a.txt").json()["revision"], 2)


class FixtureTests(ApiTestCase):
    def test_fixture_exact_bytes_and_idempotence(self):
        r = self.req("POST", "/api/v1/fixtures", {})
        self.assertEqual(r.status, 200)
        body = r.json()
        self.assertEqual(body["created"], ["launch-notes.txt"])
        self.assertEqual([f["name"] for f in body["files"]], ["launch-notes.txt"])
        g = self.req("GET", "/api/v1/files/launch-notes.txt").json()
        self.assertEqual(g["text"].encode("utf-8"), FIXTURE)
        self.assertEqual(g["size"], len(FIXTURE))
        lines = g["text"].splitlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual(sum("orbit" in l for l in lines), 2)

        self.req("PUT", "/api/v1/files/launch-notes.txt", {"text": "edited", "base_revision": 1})
        r2 = self.req("POST", "/api/v1/fixtures", {}).json()
        self.assertEqual(r2["created"], [])
        self.assertEqual(r2["files"][0]["revision"], 2)
        self.assertEqual(self.req("GET", "/api/v1/files/launch-notes.txt").json()["text"], "edited")

    def test_fixture_body_must_be_empty_object(self):
        for b in [{"x": 1}]:
            self.assertError(self.req("POST", "/api/v1/fixtures", b), 400, "invalid_request")
        self.assertError(self.req("POST", "/api/v1/fixtures", raw=b"[]"), 400, "invalid_request")


class RequestHygieneTests(ApiTestCase):
    def test_wrong_content_type(self):
        for ct in ["text/plain", "application/x-www-form-urlencoded", "application/jsonx",
                   "application/json; charset=latin-1", ""]:
            with self.subTest(ct=ct):
                r = self.req("POST", "/api/v1/files", raw=b'{"name":"a","text":"b"}',
                             headers={"Content-Type": ct})
                self.assertError(r, 415, "unsupported_media_type")
        r = self.req("POST", "/api/v1/files", raw=b'{"name":"a","text":"b"}',
                     headers={"Content-Type": "Application/JSON; charset=utf-8"})
        self.assertEqual(r.status, 201)
        self.assertEqual(self.req("GET", "/api/v1/files").json()["files"][0]["name"], "a")

    def test_missing_content_type(self):
        payload = (
            b"POST /api/v1/files HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nContent-Length: 2\r\n\r\n{}"
            % self.app.port
        )
        out = self.app.raw_socket(payload)
        self.assertTrue(out.startswith(b"HTTP/1.1 415"), out[:80])

    def test_oversize_body_rejected(self):
        raw = b'{"name":"a","text":"' + b"x" * 140000 + b'"}'
        r = self.req("POST", "/api/v1/files", raw=raw)
        self.assertError(r, 413, "payload_too_large")
        self.assertEqual(self.req("GET", "/api/v1/files").json(), {"files": []})
        # Declared size alone is enough; the body is not read.
        out = self.app.raw_socket(
            b"POST /api/v1/files HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n"
            b"Content-Type: application/json\r\nContent-Length: 131073\r\n\r\n" % self.app.port
        )
        self.assertTrue(out.startswith(b"HTTP/1.1 413"), out[:80])

    def test_body_at_limit_is_accepted_for_parsing(self):
        pad = b" " * (srv.MAX_BODY - len(b'{"name":"a","text":"b"}'))
        r = self.req("POST", "/api/v1/files", raw=b'{"name":"a","text":"b"}' + pad)
        self.assertEqual(r.status, 201)

    def test_length_required(self):
        out = self.app.raw_socket(
            b"POST /api/v1/files HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n"
            b"Content-Type: application/json\r\n\r\n" % self.app.port
        )
        self.assertTrue(out.startswith(b"HTTP/1.1 411"), out[:80])
        self.assertIn(b"length_required", out)
        out = self.app.raw_socket(
            b"PUT /api/v1/files/a HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n"
            b"Content-Type: application/json\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n"
            % self.app.port
        )
        self.assertTrue(out.startswith(b"HTTP/1.1 411"), out[:80])

    def test_bad_content_length(self):
        for cl in [b"abc", b"-1", b"1.5"]:
            out = self.app.raw_socket(
                b"POST /api/v1/files HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n"
                b"Content-Type: application/json\r\nContent-Length: %s\r\n\r\n"
                % (self.app.port, cl)
            )
            with self.subTest(cl=cl):
                self.assertTrue(out.startswith(b"HTTP/1.1 400"), out[:80])

    def test_truncated_body_is_400_and_server_survives(self):
        # Declares 50 bytes, sends 5 then half-closes.
        with socket.create_connection(("127.0.0.1", self.app.port), timeout=10) as s:
            s.sendall(
                b"POST /api/v1/files HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n"
                b"Content-Type: application/json\r\nContent-Length: 50\r\n\r\n{\"na\""
                % self.app.port
            )
            s.shutdown(socket.SHUT_WR)
            data = b""
            while True:
                c = s.recv(4096)
                if not c:
                    break
                data += c
        self.assertTrue(data.startswith(b"HTTP/1.1 400"), data[:80])
        self.assertEqual(self.req("GET", "/api/v1/health").status, 200)

    def test_foreign_host_rejected(self):
        body = {"name": "evil", "text": "x"}
        r = self.req("POST", "/api/v1/files", body, headers={"Host": "evil.example"})
        self.assertError(r, 403, "forbidden_origin")
        r = self.req("POST", "/api/v1/files", body,
                     headers={"Host": f"127.0.0.1:{self.app.port + 1}"})
        self.assertError(r, 403, "forbidden_origin")
        r = self.req("GET", "/api/v1/files", headers={"Host": "evil.example"})
        self.assertError(r, 403, "forbidden_origin")
        r = self.req("GET", "/", headers={"Host": "evil.example:80"})
        self.assertError(r, 403, "forbidden_origin")
        self.assertEqual(self.req("GET", "/api/v1/files").json(), {"files": []})

    def test_foreign_origin_rejected_on_mutations(self):
        body = {"name": "evil", "text": "x"}
        for origin in ["http://evil.example", "null", "https://127.0.0.1:%d" % self.app.port,
                       "http://127.0.0.1:1", "http://127.0.0.1.evil.example:%d" % self.app.port]:
            with self.subTest(origin=origin):
                r = self.req("POST", "/api/v1/files", body, headers={"Origin": origin})
                self.assertError(r, 403, "forbidden_origin")
        self.create("a.txt")
        r = self.req("PUT", "/api/v1/files/a.txt", {"text": "x", "base_revision": 1},
                     headers={"Origin": "http://evil.example"})
        self.assertError(r, 403, "forbidden_origin")
        r = self.req("POST", "/api/v1/fixtures", {}, headers={"Origin": "http://evil.example"})
        self.assertError(r, 403, "forbidden_origin")
        self.assertEqual([f["name"] for f in self.req("GET", "/api/v1/files").json()["files"]],
                         ["a.txt"])

    def test_same_origin_and_localhost_allowed(self):
        p = self.app.port
        for host, origin in [(f"127.0.0.1:{p}", f"http://127.0.0.1:{p}"),
                             (f"localhost:{p}", f"http://localhost:{p}")]:
            r = self.req("POST", "/api/v1/files", {"name": "h" + host[0], "text": "x"},
                         headers={"Host": host, "Origin": origin})
            self.assertEqual(r.status, 201)

    def test_malformed_request_line_gets_json_error(self):
        out = self.app.raw_socket(b"GARBAGE\r\n\r\n")
        self.assertNotIn(b"<html", out.lower())

    def test_unknown_method_does_not_crash(self):
        out = self.app.raw_socket(
            b"TRACE / HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n\r\n" % self.app.port
        )
        self.assertTrue(out.startswith(b"HTTP/1.1 501"), out[:80])
        self.assertEqual(self.req("GET", "/api/v1/health").status, 200)

    def test_internal_error_is_generic(self):
        with mock.patch.object(
            st.Storage, "list_files", side_effect=RuntimeError("secret detail /etc/passwd")
        ):
            r = self.req("GET", "/api/v1/files")
        self.assertError(r, 500, "internal_error")
        self.assertNotIn(b"secret", r.body)
        self.assertNotIn(b"Traceback", r.body)
        self.assertEqual(self.req("GET", "/api/v1/health").status, 200)

    def test_database_failure_is_500_not_crash(self):
        with mock.patch.object(
            st.Storage, "create_file", side_effect=sqlite3.OperationalError("database is locked")
        ):
            r = self.req("POST", "/api/v1/files", {"name": "a", "text": "b"})
        self.assertError(r, 500, "internal_error")


class PersistenceTests(unittest.TestCase):
    def test_data_survives_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "data"
            app = Running(d)
            try:
                app.request("POST", "/api/v1/files", {"name": "keep.txt", "text": "saved é"})
                app.request("PUT", "/api/v1/files/keep.txt", {"text": "saved2", "base_revision": 1})
            finally:
                app.stop()
            app2 = Running(d)
            try:
                g = app2.request("GET", "/api/v1/files/keep.txt").json()
                self.assertEqual((g["text"], g["revision"]), ("saved2", 2))
                self.assertEqual(app2.request("GET", "/api/v1/health").json()["schema_version"], 1)
            finally:
                app2.stop()


class CreateServerTests(unittest.TestCase):
    def test_binds_loopback_and_reports_port(self):
        with tempfile.TemporaryDirectory() as tmp:
            server, port = srv.create_server(tmp, 0)
            try:
                self.assertGreater(port, 0)
                self.assertEqual(server.server_address, ("127.0.0.1", port))
                self.assertTrue(server.daemon_threads)
            finally:
                server.server_close()

    def test_bad_data_dir_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "file"
            f.write_text("x")
            with self.assertRaises(st.DataDirError):
                srv.create_server(str(f), 0)
            with self.assertRaises(st.DataDirError):
                srv.create_server("", 0)

    def test_refuses_newer_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            st.Storage(tmp)
            conn = sqlite3.connect(str(Path(tmp) / "desktop.sqlite3"))
            conn.execute("INSERT INTO schema_migrations(version) VALUES (7)")
            conn.commit()
            conn.close()
            with self.assertRaises(st.SchemaTooNew):
                srv.create_server(tmp, 0)

    def test_port_in_use_closes_storage_and_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            blocker = socket.socket()
            blocker.bind(("127.0.0.1", 0))
            blocker.listen(1)
            try:
                with self.assertRaises(OSError):
                    srv.create_server(tmp, blocker.getsockname()[1])
            finally:
                blocker.close()


class CliTests(unittest.TestCase):
    def run_cli(self, argv):
        err = io.StringIO()
        out = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
            try:
                code = cli.main(argv)
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def test_data_dir_is_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "f"
            f.write_text("x")
            code, out, err = self.run_cli(["--data-dir", str(f), "--port", "0"])
            self.assertEqual(code, 2)
            self.assertEqual(out, "")
            self.assertEqual(len(err.strip().splitlines()), 1)

    def test_empty_data_dir(self):
        code, _, err = self.run_cli(["--data-dir", "", "--port", "0"])
        self.assertEqual(code, 2)
        self.assertEqual(len(err.strip().splitlines()), 1)

    def test_newer_schema_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            st.Storage(tmp)
            conn = sqlite3.connect(str(Path(tmp) / "desktop.sqlite3"))
            conn.execute("INSERT INTO schema_migrations(version) VALUES (2)")
            conn.commit()
            conn.close()
            code, _, err = self.run_cli(["--data-dir", tmp, "--port", "0"])
            self.assertEqual(code, 2)
            self.assertEqual(len(err.strip().splitlines()), 1)

    def test_argument_errors_exit_2(self):
        for argv in [[], ["--port", "0"], ["--data-dir", "x"],
                     ["--data-dir", "x", "--port", "70000"],
                     ["--data-dir", "x", "--port", "-1"],
                     ["--data-dir", "x", "--port", "abc"]]:
            with self.subTest(argv=argv):
                code, _, _ = self.run_cli(argv)
                self.assertEqual(code, 2)

    def test_serves_prints_url_and_closes_on_interrupt(self):
        with tempfile.TemporaryDirectory() as tmp:
            real_create = srv.create_server
            created = []

            def fake_create(data_dir, port):
                server, p = real_create(data_dir, port)
                created.append(server)

                def interrupted(*a, **k):
                    raise KeyboardInterrupt

                server.serve_forever = interrupted
                return server, p

            with mock.patch.object(cli, "create_server", fake_create):
                code, out, _ = self.run_cli(["--data-dir", tmp, "--port", "0"])
            self.assertEqual(code, 0)
            port = created[0].server_address[1]
            self.assertEqual(out, f"Serving on http://127.0.0.1:{port}/\n")
            self.assertEqual(created[0].socket.fileno(), -1)  # closed


if __name__ == "__main__":
    unittest.main()
