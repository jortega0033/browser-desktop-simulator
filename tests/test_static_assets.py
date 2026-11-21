"""Static checks for the browser UI files (stdlib only, read from disk)."""

import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "browser_desktop" / "static"


class _Collector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.tags = []  # (tag, attrs dict)
        self.script_bodies = []
        self.text = []
        self._in_script = False

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        self.tags.append((tag, d))
        if "id" in d:
            self.ids.add(d["id"])
        if tag == "script":
            self._in_script = True

    def handle_endtag(self, tag):
        if tag == "script":
            self._in_script = False

    def handle_data(self, data):
        if self._in_script:
            self.script_bodies.append(data)
        else:
            self.text.append(data)


class StaticAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (STATIC / "index.html").read_text(encoding="utf-8")
        cls.js = (STATIC / "app.js").read_text(encoding="utf-8")
        cls.css = (STATIC / "app.css").read_text(encoding="utf-8")
        cls.parsed = _Collector()
        cls.parsed.feed(cls.html)
        cls.visible = " ".join(cls.parsed.text)

    def test_required_ids(self):
        for ident in (
            "files-heading", "editor-heading", "file-list", "new-file",
            "load-fixtures", "file-name", "file-text", "save", "status",
            "conflict", "load-latest", "keep-mine",
        ):
            self.assertIn(ident, self.parsed.ids)

    def test_required_labels(self):
        for label in (
            "File list", "Text editor", "File name", "File text", "New file",
            "Load example files", "Save", "Load latest", "Keep mine and save",
            "No files yet. Choose New file or Load example files.",
        ):
            self.assertIn(label, self.visible)
        self.assertIn("Unsaved changes", self.js)

    def test_semantics(self):
        tags = self.parsed.tags
        self.assertTrue(any(t == "main" for t, _ in tags))
        status = [a for t, a in tags if a.get("id") == "status"][0]
        self.assertEqual(status.get("role"), "status")
        self.assertEqual(status.get("aria-live"), "polite")
        fname = [a for t, a in tags if a.get("id") == "file-name"][0]
        self.assertEqual(fname.get("maxlength"), "64")
        self.assertIn("for=\"file-name\"", self.html)
        self.assertIn("for=\"file-text\"", self.html)
        sections = [a for t, a in tags if t == "section"]
        self.assertEqual(
            sorted(a.get("aria-labelledby") for a in sections),
            ["editor-heading", "files-heading"],
        )

    def test_viewport_meta(self):
        metas = [a for t, a in self.parsed.tags if t == "meta"]
        self.assertTrue(any(a.get("name") == "viewport" for a in metas))

    def test_no_inline_script_style_or_handlers(self):
        for body in self.parsed.script_bodies:
            self.assertEqual(body.strip(), "")
        for tag, attrs in self.parsed.tags:
            self.assertNotEqual(tag, "style")
            for name in attrs:
                self.assertNotEqual(name, "style")
                self.assertFalse(name.startswith("on"), name)
        self.assertNotIn("javascript:", self.html.lower())

    def test_no_external_urls(self):
        for blob in (self.html, self.css, self.js):
            self.assertIsNone(re.search(r"(?i)(https?:)?//[a-z0-9.-]+\.[a-z]{2,}", blob))
            self.assertNotIn("http://", blob)
            self.assertNotIn("https://", blob)

    def test_js_safety(self):
        self.assertNotIn("innerHTML", self.js)
        self.assertNotIn("outerHTML", self.js)
        self.assertNotIn("insertAdjacentHTML", self.js)
        self.assertNotIn("document.write", self.js)
        self.assertNotIn("eval(", self.js)
        self.assertIn("encodeURIComponent", self.js)
        self.assertIn("beforeunload", self.js)
        self.assertIn("'/api/v1'", self.js)
        self.assertIn("API + '/fixtures'", self.js)

    def test_assets_referenced_by_allowlisted_paths(self):
        self.assertIn('href="/static/app.css"', self.html)
        self.assertIn('src="/static/app.js"', self.html)

    def test_css_focus_and_breakpoint(self):
        self.assertIn(":focus-visible", self.css)
        self.assertIn("max-width: 719px", self.css)


if __name__ == "__main__":
    unittest.main()
