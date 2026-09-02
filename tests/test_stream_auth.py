"""
0.7 — PIN kimlik doğrulama: header-öncelikli (X-Pardus-PIN), query deprecated.

`MJPEGHandler._check_auth` HTTP altyapısı olmadan test edilir: sahte handler
örneğine `headers`/`path`/`client_address`/`server_instance` enjekte edilir.
Amaç: PIN artık URL query yerine header'dan okunur (access-log/proxy sızıntısı
kapatılır); query yalnız geriye-uyum için ve kullanılınca bir kez uyarır.
"""

import email.message
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from pardus_paylasim.screen.stream_server import (
    MJPEGHandler,
    ScreenStreamServer,
)


def _headers(pairs: dict) -> email.message.Message:
    """dict → HTTP header nesnesi (BaseHTTPRequestHandler.headers gibi)."""
    msg = email.message.Message()
    for k, v in pairs.items():
        msg[k] = v
    return msg


def _make_handler(path: str, headers: dict, server) -> MJPEGHandler:
    """__init__ çalıştırmadan sahte handler kur (soket açmadan)."""
    handler = MJPEGHandler.__new__(MJPEGHandler)
    handler.path = path
    handler.headers = _headers(headers)
    handler.client_address = ("10.0.0.5", 54321)
    handler.server_instance = server
    return handler


class TestCheckAuth(unittest.TestCase):
    """Header/Cookie öncelikli Session doğrulama."""

    def _server(self, accept="123456"):
        server = ScreenStreamServer(device_name="Test", port=52398)
        # Inject our token directly into the real SessionManager
        server.session_mgr.sessions[accept] = {
            "created_at": time.time(),
            "capabilities": ["stream"],
        }
        return server

    def test_header_session_accepted(self):
        server = self._server(accept="token123")
        h = _make_handler("/stream", {"X-Pardus-Session": "token123"}, server)
        self.assertTrue(h._check_auth())

    def test_cookie_session_accepted(self):
        server = self._server(accept="token123")
        h = _make_handler("/stream", {"Cookie": "pardus_session=token123"}, server)
        self.assertTrue(h._check_auth())

    def test_header_session_rejected_when_wrong(self):
        server = self._server(accept="token123")
        h = _make_handler("/stream", {"X-Pardus-Session": "wrong"}, server)
        self.assertFalse(h._check_auth())

    def test_header_session_stripped(self):
        server = self._server(accept="token123")
        h = _make_handler("/stream", {"X-Pardus-Session": "  token123 "}, server)
        self.assertTrue(h._check_auth())

    def test_no_session_anywhere_rejected(self):
        server = self._server()
        h = _make_handler("/stream", {}, server)
        self.assertFalse(h._check_auth())


if __name__ == "__main__":
    unittest.main()
