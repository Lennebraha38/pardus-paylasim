"""Çekirdek kablo bağlantılarına (wiring) karşı regresyon testleri.

Jüri denetiminde bulunan kritik hataları kilitlemek için:
1. TLS alıcı + TLS gönderici uçtan uca (GUI kablolamasının özü).
2. İsim uzunluğu bellek DoS kapısı (name_len sınırı).
3. Kontrol el sıkışma isteği oturum token'ı taşıyor (native /auth akışı).
"""

import os
import socket
import struct
import tempfile
import time
import unittest

from pardus_paylasim.discovery.transfer import (
    FileReceiverServer,
    FileSender,
    build_peer_tls_context,
)

_PORT_TLS = 8991
_PORT_NAME = 8992


def _wait_for(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def _receiver_file():
    """Alıcının mevcut açık bağlantılarını kapatmak gerekmez; dosya varsa döner."""
    return None


class TestCoreWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pardus_paylasim.screen import tls_util

        cls.tls_available = tls_util.HAS_TLS

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmp.cleanup()

    def _write_source(self, name="kaynak.bin", size=256 * 1024):
        src = os.path.join(self._tmp.name, name)
        with open(src, "wb") as f:
            f.write(os.urandom(size))
        return src

    @unittest.skipUnless(hasattr(FileReceiverServer, "__dict__"), "tls şart")
    def test_tls_loopback_transfer(self):
        """B1: TLS'li alıcı + TLS'li gönderici = gerçek uçtan uca aktarım."""
        from pardus_paylasim.screen import tls_util

        if not self.tls_available:
            self.skipTest("cryptography kurulu değil, TLS testi atlanır")

        cert, key, _ = tls_util.generate_self_signed_cert()
        server_ctx = tls_util.build_server_context(cert, key)
        recv = FileReceiverServer(
            self._tmp.name, port=_PORT_TLS, ssl_context=server_ctx
        )
        recv.on_file_request = lambda *a, **k: True  # otomatik kabul
        recv.start()

        try:
            self.assertTrue(_wait_for(lambda: recv._running), "alıcı açılmadı")
            src = self._write_source()
            ctx = build_peer_tls_context("127.0.0.1", _PORT_TLS)
            sender = FileSender("127.0.0.1", _PORT_TLS, ssl_context=ctx)
            sender.send_file(src, verify_hash=True, resume=True)

            dest = os.path.join(self._tmp.name, os.path.basename(src))
            self.assertTrue(_wait_for(lambda: os.path.exists(dest)), "dosya inmedi")
            with open(src, "rb") as a, open(dest, "rb") as b:
                self.assertEqual(a.read(), b.read())
        finally:
            recv.stop()

    def test_oversized_name_rejected(self):
        """name_len DoS kapısı: sınırsız uzunluktaki adlar reddedilir."""
        recv = FileReceiverServer(self._tmp.name)

        c2s, s2c = socket.socketpair()
        done = {"value": None}

        def serve():
            try:
                recv._handle_client(s2c)
            except Exception as e:
                done["value"] = e

        import threading

        t = threading.Thread(target=serve, daemon=True)
        t.start()
        try:
            c2s.sendall(b"\x00")  # MODE_NORMAL
            c2s.sendall(struct.pack("!I", 1 << 24))  # çok büyük ad (16 MiB)
            self.assertEqual(c2s.recv(1), b"\x00")  # reddedildi
            t.join(timeout=3)
        finally:
            c2s.close()
            s2c.close()

    def test_control_handshake_carries_session_token(self):
        """B3: kontrol el sıkışması /auth token'ını header+cookie taşır."""
        from pardus_paylasim.screen import control_client

        req = control_client.build_handshake_request(
            "127.0.0.1", 8080, "dGVzdGtleQ==", pin="654321",
            session_token="tok123",
        ).decode("iso-8859-1")
        self.assertIn("X-Pardus-Session: tok123", req)
        self.assertIn("Cookie: pardus_session=tok123", req)
        self.assertIn("X-Pardus-PIN: 654321", req)
        # tokensız istek pin'i korur, token eklemez
        req2 = control_client.build_handshake_request(
            "127.0.0.1", 8080, "dGVzdGtleQ==", pin="654321", session_token=""
        ).decode("iso-8859-1")
        self.assertIn("X-Pardus-PIN: 654321", req2)
        self.assertNotIn("X-Pardus-Session", req2)


if __name__ == "__main__":
    unittest.main(verbosity=2)