"""Tarayıcıdan paylaşım (web-share) testleri — soket/GTK yok.

Kapsar: dosya yöneticisi yükleme UI öğeleri, JS yükleme akışı,
host paneli dosya linki bağlantısı. Sunucu tarafı (upload handler)
mevcut test_stream_* kapsamındadır.
"""

import os
import sys
import unittest

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

WEB_DIR = os.path.join(REPO_ROOT, "data", "web-viewer")
WINDOW_FILE = os.path.join(REPO_ROOT, "src", "pardus_paylasim", "window.py")


def _read(name):
    with open(os.path.join(WEB_DIR, name), encoding="utf-8") as f:
        return f.read()


class TestUploadUI(unittest.TestCase):
    def test_html_has_upload_controls(self):
        html = _read("file-manager.html")
        for needle in ("upload-input", "btn-upload", "upload-progress",
                       "upload-status"):
            self.assertIn(needle, html, needle)

    def test_js_uploads_raw_bytes_with_name(self):
        js = _read("file-manager.js")
        self.assertIn("/api/v1/files/upload?name=", js)
        self.assertIn("XMLHttpRequest", js)
        self.assertIn("upload.onprogress", js)
        # Sunucu multipart beklemez: dosya doğrudan gövde.
        self.assertIn("xhr.send(file)", js)

    def test_js_enforces_size_limits(self):
        js = _read("file-manager.js")
        self.assertIn("100 * 1024 * 1024", js)


class TestHostLinkWiring(unittest.TestCase):
    def test_window_shows_file_link(self):
        with open(WINDOW_FILE, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("lbl_host_files", content)
        self.assertIn("file-manager.html", content)


if __name__ == "__main__":
    unittest.main()
