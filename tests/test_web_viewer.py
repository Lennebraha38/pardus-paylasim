"""
Faz 2.1 — Web viewer statik kabuğu: sabit-allowlist servis + katı CSP.

`read_web_viewer_asset` / `_resolve_web_viewer_dir` saf (soket/GTK yok) olarak,
`MJPEGHandler.do_GET` viewer dalı ise sahte kaydedici handler ile test edilir.
Amaç: (1) yalnız index.html/viewer.css/viewer.js servis edilir, doğru
Content-Type ile; (2) allowlist dışı hiçbir yol dosya döndürmez (path-traversal
imkansız); (3) yanıt katı CSP + güvenlik header'ları taşır; (4) kabuk
kimlik-doğrulamasız (PIN'siz) gelir — içindeki /stream, /control hâlâ PIN ister.
"""

import email.message
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from pardus_paylasim.screen.stream_server import (  # noqa: E402
    _VIEWER_CSP,
    _WEB_VIEWER_ASSETS,
    MJPEGHandler,
    ScreenStreamServer,
    _resolve_web_viewer_dir,
    read_web_viewer_asset,
)


class TestResolveViewerDir(unittest.TestCase):
    """Dev repo-kökü `data/web-viewer` dizini çözülür ve üç varlık orada."""

    def test_dev_dir_resolved(self):
        base = _resolve_web_viewer_dir()
        self.assertIsNotNone(base)
        self.assertTrue(os.path.isdir(base))

    def test_all_three_assets_exist_on_disk(self):
        base = _resolve_web_viewer_dir()
        for filename in ("index.html", "viewer.css", "viewer.js"):
            self.assertTrue(
                os.path.isfile(os.path.join(base, filename)),
                f"{filename} eksik",
            )


class TestReadWebViewerAsset(unittest.TestCase):
    """Sabit-allowlist okuma: doğru içerik-tipi, allowlist dışı → None."""

    def test_root_serves_index_html(self):
        result = read_web_viewer_asset("/")
        self.assertIsNotNone(result)
        body, content_type = result
        self.assertEqual(content_type, "text/html; charset=utf-8")
        self.assertIn(b"<!DOCTYPE html>", body)
        # Kabuk viewer.js + viewer.css'i harici yükler (satır-içi yok → CSP).
        self.assertIn(b"/viewer.js", body)
        self.assertIn(b"/viewer.css", body)

    def test_index_html_alias(self):
        # /index.html de kök ile aynı dosyaya çözülür.
        root = read_web_viewer_asset("/")
        alias = read_web_viewer_asset("/index.html")
        self.assertEqual(root, alias)

    def test_css_content_type(self):
        result = read_web_viewer_asset("/viewer.css")
        self.assertIsNotNone(result)
        _, content_type = result
        self.assertEqual(content_type, "text/css; charset=utf-8")

    def test_js_content_type(self):
        result = read_web_viewer_asset("/viewer.js")
        self.assertIsNotNone(result)
        body, content_type = result
        self.assertEqual(content_type, "application/javascript; charset=utf-8")
        # Kontrol istemcisi: /control WS + normalize koord protokolü içerir.
        self.assertIn(b"/control", body)

    def test_non_allowlisted_route_returns_none(self):
        # Allowlist dışı: dosya var olsa bile servis EDİLMEZ.
        for route in (
            "/stream",
            "/info",
            "/../src/pardus_paylasim/screen/stream_server.py",
            "/viewer.js/../../secret",
            "/etc/passwd",
            "/index.html/",
            "",
        ):
            self.assertIsNone(read_web_viewer_asset(route), f"{route} servis edilmemeli")

    def test_allowlist_maps_exactly_three_files(self):
        # Yalnız üç mantıksal dosya (kök + alias = 4 route, 3 dosya adı).
        filenames = {fn for fn, _ in _WEB_VIEWER_ASSETS.values()}
        self.assertEqual(
            filenames,
            {
                "index.html",
                "viewer.css",
                "viewer.js",
                "file-manager.html",
                "file-manager.css",
                "file-manager.js",
            },
        )


class _RecordingHandler(MJPEGHandler):
    """do_GET viewer dalını test için sahteleyen handler (soket açmaz)."""

    def __init__(self, path, server):
        # __init__ atlanır (soket yok); alanlar elle enjekte edilir.
        self.path = path
        self.sent_headers: list = []
        self.status_code = None
        self.written = b""
        self.headers = email.message.Message()
        self.server_instance = server

    def send_response(self, code, message=None):  # override
        self.status_code = code

    def send_header(self, key, value):  # override
        self.sent_headers.append((key, value))

    def end_headers(self):  # override
        pass

    class _Wfile:
        def __init__(self, outer):
            self._outer = outer

        def write(self, data):
            self._outer.written += data

    @property
    def wfile(self):
        return _RecordingHandler._Wfile(self)


def _server() -> ScreenStreamServer:
    return ScreenStreamServer(device_name="Test", port=52397)


class TestViewerRouteResponse(unittest.TestCase):
    """`do_GET` viewer dalı: 200 + katı CSP + güvenlik header'ları + gövde."""

    def _dispatch(self, path):
        server = _server()
        h = _RecordingHandler(path, server)
        h.do_GET()
        return h

    def test_root_returns_200_html(self):
        h = self._dispatch("/")
        self.assertEqual(h.status_code, 200)
        headers = dict(h.sent_headers)
        self.assertEqual(headers.get("Content-type"), "text/html; charset=utf-8")
        self.assertIn(b"<!DOCTYPE html>", h.written)

    def test_strict_csp_header_present(self):
        h = self._dispatch("/")
        headers = dict(h.sent_headers)
        csp = headers.get("Content-Security-Policy")
        self.assertEqual(csp, _VIEWER_CSP)
        # Satır-içi izin yok, joker yok → sıkı 'self' politikası.
        self.assertNotIn("unsafe-inline", csp)
        self.assertNotIn("*", csp)
        self.assertIn("default-src 'none'", csp)
        self.assertIn("script-src 'self'", csp)
        self.assertIn("connect-src 'self'", csp)

    def test_security_headers_present(self):
        h = self._dispatch("/viewer.css")
        headers = dict(h.sent_headers)
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(headers.get("Referrer-Policy"), "no-referrer")

    def test_content_length_matches_body(self):
        h = self._dispatch("/viewer.js")
        headers = dict(h.sent_headers)
        self.assertEqual(headers.get("Content-Length"), str(len(h.written)))

    def test_unknown_route_is_404(self):
        # Allowlist dışı yol viewer dalına düşmez → NOT_FOUND.
        h = self._dispatch("/nope")
        self.assertEqual(h.status_code, 404)
        self.assertIn(b"NOT_FOUND", h.written)

    def test_viewer_shell_needs_no_pin(self):
        # Kabuk kimlik-doğrulamasız gelmeli: PIN header'ı olmadan 200.
        # (İçindeki /stream ve /control hâlâ PIN ister — ayrı test setleri.)
        h = self._dispatch("/")
        self.assertEqual(h.status_code, 200)


if __name__ == "__main__":
    unittest.main()
