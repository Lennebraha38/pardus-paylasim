"""
0.8 — CORS kilit: joker '*' asla; yalnız allowlist origin echo edilir.

`parse_allowed_origins` saf fonksiyon olarak, `MJPEGHandler._cors_origin` /
`_send_cors` ise HTTP altyapısı olmadan (sahte handler + kaydedici) test edilir.
Amaç: eski `Access-Control-Allow-Origin: *` davranışı kaldırıldı; CORS yalnız
`config.allow_web_origin` allowlist'indeki origin'lere, tam eşleşmeyle verilir.
"""

import email.message
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from pardus_paylasim.screen.stream_server import (
    MJPEGHandler,
    ScreenStreamServer,
    parse_allowed_origins,
)


class TestParseAllowedOrigins(unittest.TestCase):
    """Allowlist string → origin kümesi ayrıştırma."""

    def test_empty_returns_empty_set(self):
        self.assertEqual(parse_allowed_origins(""), frozenset())

    def test_none_returns_empty_set(self):
        self.assertEqual(parse_allowed_origins(None), frozenset())

    def test_single_origin(self):
        self.assertEqual(
            parse_allowed_origins("https://a.local"),
            frozenset({"https://a.local"}),
        )

    def test_multiple_origins_split_and_trimmed(self):
        result = parse_allowed_origins(" https://a.local , https://b.local:8443 ")
        self.assertEqual(result, frozenset({"https://a.local", "https://b.local:8443"}))

    def test_wildcard_never_accepted(self):
        # '*' allowlist'e giremez: tek başına da, listede de reddedilir.
        self.assertEqual(parse_allowed_origins("*"), frozenset())
        self.assertEqual(
            parse_allowed_origins("*, https://a.local"),
            frozenset({"https://a.local"}),
        )

    def test_blank_parts_dropped(self):
        self.assertEqual(
            parse_allowed_origins("https://a.local,,  ,"),
            frozenset({"https://a.local"}),
        )


class _RecordingHandler(MJPEGHandler):
    """send_header çağrılarını kaydeden sahte handler (soket açmaz)."""

    def __init__(self, origin, server):
        # __init__ atlanır (soket yok); alanlar elle enjekte edilir.
        self.sent_headers: list = []
        self.headers = email.message.Message()
        if origin is not None:
            self.headers["Origin"] = origin
        self.server_instance = server

    def send_header(self, key, value):  # BaseHTTPRequestHandler override
        self.sent_headers.append((key, value))


def _server(allowlist: str) -> ScreenStreamServer:
    server = ScreenStreamServer(device_name="Test", port=52396)
    server.allowed_web_origins = parse_allowed_origins(allowlist)
    return server


class TestCorsOrigin(unittest.TestCase):
    """`_cors_origin` / `_send_cors`: yalnız allowlist origin, asla '*'."""

    def _cors_headers(self, handler) -> dict:
        handler.sent_headers = []
        handler._send_cors()
        return dict(handler.sent_headers)

    def test_allowlisted_origin_echoed(self):
        server = _server("https://a.local")
        h = _RecordingHandler("https://a.local", server)
        headers = self._cors_headers(h)
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), "https://a.local")
        self.assertEqual(headers.get("Vary"), "Origin")

    def test_non_allowlisted_origin_gets_no_cors(self):
        server = _server("https://a.local")
        h = _RecordingHandler("https://evil.example", server)
        headers = self._cors_headers(h)
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_no_origin_header_gets_no_cors(self):
        # Native/same-origin istemci: Origin yok → CORS header hiç yok.
        server = _server("https://a.local")
        h = _RecordingHandler(None, server)
        headers = self._cors_headers(h)
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_empty_allowlist_never_echoes(self):
        # Varsayılan (boş) allowlist: hiçbir origin echo edilmez.
        server = _server("")
        h = _RecordingHandler("https://a.local", server)
        headers = self._cors_headers(h)
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_wildcard_never_emitted(self):
        # Regresyon kilidi: hiçbir koşulda '*' gönderilmemeli.
        for allowlist, origin in [
            ("", "https://a.local"),
            ("https://a.local", "https://a.local"),
            ("https://a.local", "https://evil.example"),
            ("*", "https://a.local"),
        ]:
            server = _server(allowlist)
            h = _RecordingHandler(origin, server)
            headers = self._cors_headers(h)
            self.assertNotEqual(headers.get("Access-Control-Allow-Origin"), "*")


class TestLoadAllowedOrigins(unittest.TestCase):
    """Sunucu başlatınca allowlist AppConfig'ten yüklenir (fail-safe boş)."""

    def test_default_server_has_empty_allowlist(self):
        # AppConfig varsayılanı boş → hiçbir origin izinli değil.
        server = ScreenStreamServer(device_name="Test", port=52395)
        self.assertNotIn("*", server.allowed_web_origins)
        # Varsayılan kurulumda joker yok, tip frozenset.
        self.assertIsInstance(server.allowed_web_origins, frozenset)


if __name__ == "__main__":
    unittest.main()
