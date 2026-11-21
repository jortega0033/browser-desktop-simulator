import re
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from browser_desktop import storage as st


class StorageTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name) / "data"  # created by Storage
        self.store = st.Storage(self.dir)


class CrudTests(StorageTestCase):
    def test_create_get_list_sorted(self):
        a = self.store.create_file("b.txt", "two")
        self.store.create_file("a.txt", "one")
        self.assertEqual(a["revision"], 1)
        self.assertRegex(a["updated_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual([f["name"] for f in self.store.list_files()], ["a.txt", "b.txt"])
        self.assertNotIn("text", self.store.list_files()[0])
        self.assertEqual(self.store.get_file("a.txt")["text"], "one")

    def test_size_is_utf8_bytes_and_newlines_kept(self):
        f = self.store.create_file("u.txt", "h\u00e9\r\nx\n")
        self.assertEqual(f["size"], len("h\u00e9\r\nx\n".encode()))
        self.assertEqual(self.store.get_file("u.txt")["text"], "h\u00e9\r\nx\n")
        self.assertEqual(self.store.list_files()[0]["size"], f["size"])

    def test_names_are_case_sensitive(self):
        self.store.create_file("A.txt", "1")
        self.store.create_file("a.txt", "2")
        self.assertEqual(len(self.store.list_files()), 2)

    def test_duplicate_and_missing(self):
        self.store.create_file("a", "x")
        with self.assertRaises(st.AlreadyExists):
            self.store.create_file("a", "y")
        with self.assertRaises(st.NotFound):
            self.store.get_file("nope")
        with self.assertRaises(st.NotFound):
            self.store.update_file("nope", "t", 1)

    def test_update_cas(self):
        self.store.create_file("a", "v1")
        u = self.store.update_file("a", "v2", 1)
        self.assertEqual((u["revision"], u["text"]), (2, "v2"))
        with self.assertRaises(st.Conflict) as ctx:
            self.store.update_file("a", "stale", 1)
        self.assertEqual(ctx.exception.current["revision"], 2)
        self.assertEqual(ctx.exception.current["text"], "v2")
        self.assertEqual(self.store.get_file("a")["text"], "v2")

    def test_file_limit(self):
        for i in range(st.MAX_FILES):
            self.store.create_file(f"f{i}", "")
        with self.assertRaises(st.FileLimitReached):
            self.store.create_file("extra", "")
        with self.assertRaises(st.FileLimitReached):
            self.store.ensure_fixture()
        self.store.update_file("f0", "still works", 1)
        self.assertEqual(len(self.store.list_files()), st.MAX_FILES)

    def test_fixture_idempotent_never_overwrites(self):
        self.assertTrue(self.store.ensure_fixture())
        f = self.store.get_file("launch-notes.txt")
        self.assertEqual(f["text"], "orbit alpha ready\ndock lights green\norbit beta synced\n")
        self.store.update_file("launch-notes.txt", "mine", 1)
        self.assertFalse(self.store.ensure_fixture())
        self.assertEqual(self.store.get_file("launch-notes.txt")["text"], "mine")

    def test_failed_write_leaves_no_partial_state(self):
        self.store.create_file("a", "v1")
        with self.assertRaises(st.ValidationError):
            self.store.update_file("a", "bad\x00", 1)
        self.assertEqual(self.store.get_file("a")["revision"], 1)


class ValidationTests(StorageTestCase):
    def test_bad_names(self):
        bad = ["", ".hidden", "-x", "_x", "a/b", "a\\b", "a b", "a..b", "..", "x" * 65,
               "caf\u00e9", "a\n", "a\x00", None, 5, "a:b"]
        for name in bad:
            with self.subTest(name=name):
                with self.assertRaises(st.ValidationError) as ctx:
                    self.store.create_file(name, "t")
                self.assertEqual(ctx.exception.code, "invalid_name")

    def test_good_names(self):
        for name in ["a", "A1", "x" * 64, "a.b-c_d", "0.txt", "a.b"]:
            with self.subTest(name=name):
                self.store.create_file(name, "t")

    def test_text_rules(self):
        self.store.create_file("max", "x" * st.MAX_TEXT_BYTES)
        with self.assertRaises(st.ValidationError) as ctx:
            self.store.create_file("big", "x" * (st.MAX_TEXT_BYTES + 1))
        self.assertEqual(ctx.exception.code, "text_too_large")
        # 32769 two-byte characters exceed the limit in bytes, not characters
        with self.assertRaises(st.ValidationError) as ctx:
            self.store.create_file("bytes", "\u00e9" * 32769)
        self.assertEqual(ctx.exception.code, "text_too_large")
        self.store.create_file("bytes-ok", "\u00e9" * 32768)
        for bad in ["a\x00b", "\ud800", 5, None, ["x"]]:
            with self.subTest(text=bad):
                with self.assertRaises(st.ValidationError) as ctx:
                    self.store.create_file("t", bad)
                self.assertEqual(ctx.exception.code, "invalid_request")

    def test_bad_revisions(self):
        self.store.create_file("a", "x")
        for bad in [0, -1, True, False, "1", 1.0, None]:
            with self.subTest(rev=bad):
                with self.assertRaises(st.ValidationError):
                    self.store.update_file("a", "y", bad)


class MigrationTests(StorageTestCase):
    def _versions(self):
        conn = sqlite3.connect(str(self.dir / "desktop.sqlite3"))
        try:
            return [r[0] for r in conn.execute("SELECT version FROM schema_migrations")]
        finally:
            conn.close()

    def test_migration_idempotent_and_data_survives(self):
        self.store.create_file("a", "keep")
        st.Storage(self.dir)
        st.Storage(self.dir)
        self.assertEqual(self._versions(), [1])
        self.assertEqual(self.store.schema_version(), 1)
        self.assertEqual(st.Storage(self.dir).get_file("a")["text"], "keep")

    def test_refuses_newer_schema(self):
        conn = sqlite3.connect(str(self.dir / "desktop.sqlite3"))
        conn.execute("INSERT INTO schema_migrations(version) VALUES (99)")
        conn.commit()
        conn.close()
        with self.assertRaises(st.SchemaTooNew):
            st.Storage(self.dir)

    def test_db_check_constraints(self):
        conn = sqlite3.connect(str(self.dir / "desktop.sqlite3"))
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO files VALUES ('x', 'ok', 0, 't', 't')"
                )
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO files VALUES ('x', ?, 1, 't', 't')", ("y" * 65537,)
                )
        finally:
            conn.close()

    def test_wal_mode(self):
        conn = sqlite3.connect(str(self.dir / "desktop.sqlite3"))
        try:
            self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        finally:
            conn.close()


class DataDirTests(unittest.TestCase):
    def test_empty_string(self):
        with self.assertRaises(st.DataDirError):
            st.Storage("")

    def test_path_is_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "afile"
            p.write_text("x")
            with self.assertRaises(st.DataDirError):
                st.Storage(p)
            self.assertEqual(p.read_text(), "x")

    def test_parent_is_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "afile"
            p.write_text("x")
            with self.assertRaises(st.DataDirError):
                st.Storage(p / "child")

    def test_creates_nested_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "a" / "b"
            st.Storage(target)
            self.assertTrue((target / "desktop.sqlite3").is_file())

    def test_corrupt_database_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "desktop.sqlite3").write_bytes(b"this is not sqlite" * 100)
            with self.assertRaises(st.StorageError):
                st.Storage(tmp)


class ConcurrencyTests(StorageTestCase):
    def test_single_winner_per_revision(self):
        self.store.create_file("a", "base")
        n = 8
        barrier = threading.Barrier(n)
        results = []
        lock = threading.Lock()

        def worker(i):
            barrier.wait()
            try:
                self.store.update_file("a", f"w{i}", 1)
                outcome = "ok"
            except st.Conflict:
                outcome = "conflict"
            with lock:
                results.append(outcome)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        self.assertEqual(results.count("ok"), 1)
        self.assertEqual(results.count("conflict"), n - 1)
        self.assertEqual(self.store.get_file("a")["revision"], 2)

    def test_concurrent_creates_respect_limit_and_uniqueness(self):
        n = 8
        barrier = threading.Barrier(n)
        results = []
        lock = threading.Lock()

        def worker():
            barrier.wait()
            try:
                self.store.create_file("same", "x")
                outcome = "ok"
            except st.AlreadyExists:
                outcome = "exists"
            with lock:
                results.append(outcome)

        threads = [threading.Thread(target=worker) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        self.assertEqual(results.count("ok"), 1)
        self.assertEqual(results.count("exists"), n - 1)


if __name__ == "__main__":
    unittest.main()
