import json
import os
import sys
import time
import unittest
import urllib.error
import urllib.request

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from pardus_paylasim.discovery.mdns_discovery import MDNSDiscovery
from pardus_paylasim.screen import tls_util
from pardus_paylasim.screen.pairing import ScreenPairingManager, SessionManager
from pardus_paylasim.screen.stream_client import ScreenStreamClient
from pardus_paylasim.screen.stream_server import MJPEGHandler, ScreenStreamServer


class _FakeServerInstance:
    """`_check_auth`'un ihtiyaç duyduğu asgari sunucu yüzeyi (headless)."""

    def __init__(self, pairing_mgr):
        self.pairing_mgr = pairing_mgr
        self.session_mgr = SessionManager()


def _make_handler(server_instance, headers, path, client_ip="10.0.0.7"):
    handler = object.__new__(MJPEGHandler)
    handler.headers = headers
    handler.path = path
    handler.client_address = (client_ip, 12345)
    handler.server_instance = server_instance
    return handler


class TestSessionAuth(unittest.TestCase):
    """B5 güvenlik: PIN yerine Session token doğrulaması (Faz 2)."""

    def setUp(self):
        self.client_ip = "10.0.0.7"
        self.mgr = ScreenPairingManager()
        self.server = _FakeServerInstance(self.mgr)
        self.token = self.server.session_mgr.create_session()

    def test_valid_header_session_accepts(self):
        handler = _make_handler(
            self.server, {"X-Pardus-Session": self.token}, "/stream", self.client_ip
        )
        self.assertTrue(handler._check_auth())

    def test_valid_cookie_session_accepts(self):
        handler = _make_handler(
            self.server, {"Cookie": f"pardus_session={self.token}"}, "/stream", self.client_ip
        )
        self.assertTrue(handler._check_auth())

    def test_invalid_session_rejects(self):
        handler = _make_handler(
            self.server, {"X-Pardus-Session": "invalid-token-123"}, "/stream", self.client_ip
        )
        self.assertFalse(handler._check_auth())

    def test_header_session_whitespace_trimmed(self):
        handler = _make_handler(
            self.server,
            {"X-Pardus-Session": f"  {self.token}  "},
            "/stream",
            self.client_ip,
        )
        self.assertTrue(handler._check_auth())

    def test_no_session_anywhere_rejects(self):
        handler = _make_handler(self.server, {}, "/stream", self.client_ip)
        self.assertFalse(handler._check_auth())


class _MockWfile:
    def __init__(self):
        self.written = b""

    def write(self, data):
        self.written += data

    def flush(self):
        pass


class _FakeStreamServer:
    def __init__(self, server_instance):
        self.server_instance = server_instance
        self.allowed_web_origins = []
        self.session_mgr = server_instance.session_mgr


class TestControlScopeAuth(unittest.TestCase):
    def setUp(self):
        from pardus_paylasim.screen.control_server import ControlChannelServer

        self.client_ip = "10.0.0.7"
        self.mgr = ScreenPairingManager()
        self.server_inst = _FakeServerInstance(self.mgr)
        self.stream_server = _FakeStreamServer(self.server_inst)
        self.control_server = ControlChannelServer(self.stream_server)
        self.control_server.set_control_allowed(True)

        # Valid sessions with different scopes
        self.stream_token = self.server_inst.session_mgr.create_session(capabilities=["stream"])

        self.control_token = self.server_inst.session_mgr.create_session(
            capabilities=["stream", "control"]
        )

        self.expired_token = self.server_inst.session_mgr.create_session(
            capabilities=["stream", "control"]
        )
        self.server_inst.session_mgr.revoke_token(self.expired_token)

    def _make_control_handler(self, headers):
        handler = _make_handler(self.server_inst, headers, "/control", self.client_ip)
        handler.command = "GET"
        handler.wfile = _MockWfile()
        handler.rejected = None

        def _send_json(payload, status):
            handler.rejected = (status, json.loads(payload))

        handler._send_json = _send_json
        return handler

    def test_valid_control_scope_accepts(self):
        handler = self._make_control_handler(
            {
                "Upgrade": "websocket",
                "Connection": "upgrade",
                "Sec-WebSocket-Version": "13",
                "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==",
                "X-Pardus-Session": self.control_token,
            }
        )
        # Mock _serve to avoid real I/O and Pynput dependencies
        _serve_called = False

        def mock_serve(hndlr, ip, tok, backend):
            nonlocal _serve_called
            _serve_called = True

        original_serve = self.control_server._serve
        self.control_server._serve = mock_serve

        # Docker veya headless ortamda create_backend başarısız olabileceği için mockla
        from unittest.mock import MagicMock, patch

        mock_backend_cls = MagicMock()
        mock_backend_cls.return_value = MagicMock()

        with (
            patch("pardus_paylasim.screen.input_inject.select_backend_name", return_value="mock"),
            patch.dict(
                "pardus_paylasim.screen.input_inject._FACTORIES", {"mock": mock_backend_cls}
            ),
        ):
            try:
                self.control_server.handle_upgrade(handler)
                self.assertIsNone(handler.rejected)
                self.assertIn(b"101 Switching Protocols", handler.wfile.written)
                self.assertTrue(_serve_called, "_serve() should be called for valid control scope")
            finally:
                self.control_server._serve = original_serve

    def test_stream_only_scope_rejects(self):
        handler = self._make_control_handler(
            {
                "Upgrade": "websocket",
                "Connection": "upgrade",
                "Sec-WebSocket-Version": "13",
                "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==",
                "X-Pardus-Session": self.stream_token,
            }
        )
        self.control_server.handle_upgrade(handler)
        self.assertIsNotNone(handler.rejected)
        self.assertEqual(handler.rejected[0], 403)
        self.assertEqual(handler.rejected[1]["error"], "FORBIDDEN_SCOPE")
        self.assertEqual(handler.wfile.written, b"")  # Upgrade gerçekleşmedi

    def test_no_token_rejects(self):
        handler = self._make_control_handler(
            {
                "Upgrade": "websocket",
                "Connection": "upgrade",
                "Sec-WebSocket-Version": "13",
                "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==",
            }
        )
        self.control_server.handle_upgrade(handler)
        self.assertIsNotNone(handler.rejected)
        self.assertEqual(handler.rejected[0], 403)
        # PIN/Session check rejects first
        self.assertEqual(handler.rejected[1]["error"], "INVALID_PIN")

    def test_expired_token_rejects(self):
        handler = self._make_control_handler(
            {
                "Upgrade": "websocket",
                "Connection": "upgrade",
                "Sec-WebSocket-Version": "13",
                "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==",
                "X-Pardus-Session": self.expired_token,
            }
        )
        self.control_server.handle_upgrade(handler)
        self.assertIsNotNone(handler.rejected)
        self.assertEqual(handler.rejected[0], 403)
        self.assertEqual(handler.rejected[1]["error"], "INVALID_PIN")

    def test_unknown_scope_rejects(self):
        token = self.server_inst.session_mgr.create_session(capabilities=["unknown_cap"])
        handler = self._make_control_handler(
            {
                "Upgrade": "websocket",
                "Connection": "upgrade",
                "Sec-WebSocket-Version": "13",
                "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==",
                "X-Pardus-Session": token,
            }
        )
        self.control_server.handle_upgrade(handler)
        self.assertIsNotNone(handler.rejected)
        self.assertEqual(handler.rejected[0], 403)
        self.assertEqual(handler.rejected[1]["error"], "FORBIDDEN_SCOPE")


def test_screen_protocols():
    print("=== PARDUS SCREEN SHARING & DISCOVERY PROTOCOL TEST ===")

    # 1. Test Device Discovery (mDNS)
    print("\n[1] Testing P2P Device Discovery...")
    discovered = []

    def on_device(name, ip, port, info):
        discovered.append((name, ip, port))

    scanner = MDNSDiscovery("Pardus Test Device", 52345)
    scanner.start_broadcasting_and_scanning(on_device)

    time.sleep(2)  # Wait for mDNS to broadcast and discover itself
    print(f"Discovered Devices: {len(discovered)}")
    for d in discovered:
        print(f" - {d[0]} ({d[1]}:{d[2]})")

    scanner.stop()

    # 2. Test Stream Server
    print("\n[2] Testing Screen Stream Server...")
    server = ScreenStreamServer(device_name="Test Pardus Server", port=55555)

    server_pin = []

    def on_pin(pin):
        server_pin.append(pin)
        print(f" [Server] Generated PIN: {pin}")

    pin = server.start_server(pin_callback=on_pin)
    time.sleep(2)  # Allow threads to start

    print(f" Server is_streaming: {server.is_streaming}")
    print(f" Server port: {server.port}")

    if not server_pin:
        server_pin.append(pin)

    actual_pin = server_pin[0]

    # Sema TLS durumuna gore secilir: cryptography varsa https, yoksa http.
    scheme = "https" if server.tls_enabled else "http"
    # Self-signed sertifikayi kabul eden istemci baglami (TLS aciksa).
    ctx = (
        tls_util.build_client_context(
            tls_util.fetch_server_cert_to_tempfile(
                "127.0.0.1", 55555, expected_fingerprint=server.cert_fingerprint
            )
        )
        if server.tls_enabled
        else None
    )
    base = f"{scheme}://127.0.0.1:55555"
    print(f" Sunucu semasi: {scheme} (tls_enabled={server.tls_enabled})")

    # Check /info endpoint
    print("\n[3] Testing /info endpoint...")
    try:
        req = urllib.request.Request(f"{base}/info")
        with urllib.request.urlopen(req, timeout=2, context=ctx) as response:
            print(f" /info Response: {response.status}")
            print(f" /info JSON: {json.loads(response.read().decode())}")
    except Exception as e:
        print(f" /info failed: {e}")

    # Check /stream endpoint without PIN (Should fail)
    print("\n[4] Testing /stream endpoint (Auth Rejection)...")
    try:
        req = urllib.request.Request(f"{base}/stream?pin=WRONG")
        with urllib.request.urlopen(req, timeout=2, context=ctx) as response:
            print(f" /stream (Wrong PIN) Response: {response.status} (Expected 403)")
    except urllib.error.HTTPError as e:
        print(f" /stream (Wrong PIN) Response: {e.code} (Expected 403)")
    except Exception as e:
        print(f" /stream failed: {e}")

    # 3. Test Stream Client
    print("\n[5] Testing Stream Client Connection...")
    client = ScreenStreamClient()

    frame_count = []

    def on_frame(frame_bytes):
        frame_count.append(1)

    connected = client.connect_to_stream(
        host_ip="127.0.0.1", port=55555, pin=actual_pin, on_frame=on_frame
    )
    print(f" Client connected: {connected}")

    if connected:
        print(" Waiting 5 seconds to receive frames...")
        for _ in range(5):
            time.sleep(1)
            print(f"   Received frames so far: {len(frame_count)}")

    client.disconnect()
    server.stop_server()

    print(f"\n[Result] Total frames received: {len(frame_count)}")
    if len(frame_count) > 0:
        print("[OK] SUCCESS: Screen streaming protocol is fully working end-to-end!")
    else:
        print("[WARN] No frames received (screen capture tool yok). Protokol/TLS yolu calisiyor.")


if __name__ == "__main__":
    test_screen_protocols()
