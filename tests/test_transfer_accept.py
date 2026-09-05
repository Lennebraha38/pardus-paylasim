"""
Dosya kabul diyaloğu (accept gate) ve dizin-aşımı (path traversal) korumasının
uçtan-uca testleri. FileReceiverServer + FileSender gerçek soket üzerinden.
"""

import os
import socket
import struct
import tempfile
import time
import unittest

from pardus_paylasim.discovery.transfer import FileReceiverServer, FileSender

# Testler arası çakışmayı önlemek için ayrı portlar.
_PORT_ACCEPT = 8951
_PORT_REJECT = 8952
_PORT_DEFAULT = 8953
_PORT_TRAVERSAL = 8954
_PORT_SECRET = 8955


def _wait_for(predicate, timeout=5.0):
    """Koşul sağlanana kadar kısa aralıklarla bekler (deterministik)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


class TestFileAcceptGate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.download_dir = self._tmp.name
        from pardus_paylasim.screen import tls_util

        cert, key, _ = tls_util.generate_self_signed_cert()
        self.server_ctx = tls_util.build_server_context(cert, key)
        self.client_ctx = tls_util.build_client_context(cert)

    def tearDown(self):
        self._tmp.cleanup()

    def _make_source_file(self, name="belge.txt", content=b"pardus test verisi"):
        path = os.path.join(self.download_dir, "_kaynak_" + name)
        with open(path, "wb") as f:
            f.write(content)
        return path

    def test_accept_saves_file(self):
        # Kabul edilirse dosya diske yazılmalı.
        received = []
        server = FileReceiverServer(
            self.download_dir, port=_PORT_ACCEPT, ssl_context=self.server_ctx
        )
        server.on_file_received = lambda p: received.append(p)
        server.on_file_request = lambda name, size, ip: True
        server.start()
        try:
            src = self._make_source_file()
            sender = FileSender("127.0.0.1", _PORT_ACCEPT)
            sender.ssl_context = self.client_ctx
            sender.send_file(src)
            self.assertTrue(_wait_for(lambda: len(received) == 1))
            self.assertTrue(os.path.exists(received[0]))
        finally:
            server.stop()

    def test_reject_discards_file(self):
        # Reddedilirse hiçbir dosya kaydedilmemeli; gönderici ACK'i \x00 alır.
        received = []
        server = FileReceiverServer(
            self.download_dir, port=_PORT_REJECT, ssl_context=self.server_ctx
        )
        server.on_file_received = lambda p: received.append(p)
        server.on_file_request = lambda name, size, ip: False
        server.start()
        try:
            src = self._make_source_file()
            # Ret durumunda ACK \x01 gelmez -> FileTransferError beklenir.
            with self.assertRaises(Exception):
                sender = FileSender("127.0.0.1", _PORT_REJECT)
                sender.ssl_context = self.client_ctx
                sender.send_file(src)
            time.sleep(0.3)
            self.assertEqual(len(received), 0)
            # download_dir içinde kaydedilmiş alıcı dosyası olmamalı.
            saved = [f for f in os.listdir(self.download_dir) if not f.startswith("_kaynak_")]
            self.assertEqual(saved, [])
        finally:
            server.stop()

    def test_none_callback_auto_rejects(self):
        # Fail-closed politikası: on_file_request None ise otomatik RED.
        received = []
        server = FileReceiverServer(
            self.download_dir, port=_PORT_DEFAULT, ssl_context=self.server_ctx
        )
        server.on_file_received = lambda p: received.append(p)
        # on_file_request atanmaz (None).
        server.start()
        try:
            src = self._make_source_file()
            # Ret durumunda ACK \x01 gelmez -> Exception beklenir.
            with self.assertRaises(Exception):
                sender = FileSender("127.0.0.1", _PORT_DEFAULT)
                sender.ssl_context = self.client_ctx
                sender.send_file(src)
            time.sleep(0.3)
            self.assertEqual(len(received), 0)
        finally:
            server.stop()

    def test_path_traversal_sanitized(self):
        # Saldırgan '../' içeren ad gönderse bile alıcı yalnız basename
        # kullanmalı; dosya download_dir dışına asla yazılmamalı.
        # FileSender basename uyguladığından, saldırıyı taklit için ham
        # protokolü elle gönderiyoruz (normal modda: mode|namelen|name|size|body).
        received = []
        server = FileReceiverServer(
            self.download_dir, port=_PORT_TRAVERSAL, ssl_context=self.server_ctx
        )
        server.on_file_received = lambda p: received.append(p)
        server.on_file_request = lambda name, size, ip: True
        server.start()
        try:
            evil_name = "../../../../tmp/pardus_evil.bin"
            body = b"zararli icerik"
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                s.connect(("127.0.0.1", _PORT_TRAVERSAL))
                with self.client_ctx.wrap_socket(s, server_hostname="127.0.0.1") as tls_sock:
                    tls_sock.sendall(b"\x00")  # Normal mod
                    name_bytes = evil_name.encode("utf-8")
                    tls_sock.sendall(struct.pack("!I", len(name_bytes)))
                    tls_sock.sendall(name_bytes)
                    tls_sock.sendall(struct.pack("!Q", len(body)))
                    tls_sock.sendall(body)
                    ack = tls_sock.recv(1)
                    self.assertEqual(ack, b"\x01")

            self.assertTrue(_wait_for(lambda: len(received) == 1))
            # Kaydedilen yol mutlaka download_dir içinde olmalı.
            real_dir = os.path.realpath(self.download_dir)
            real_saved = os.path.realpath(received[0])
            self.assertTrue(
                real_saved.startswith(real_dir),
                f"Dosya dizin dışına yazıldı: {real_saved}",
            )
            # Aşım hedefi oluşmamalı.
            self.assertFalse(os.path.exists("/tmp/pardus_evil.bin"))
        finally:
            server.stop()

    @unittest.skipUnless(
        __import__("pardus_paylasim.discovery.transfer", fromlist=["HAS_CRYPTO"]).HAS_CRYPTO,
        "cryptography not installed",
    )
    def test_secret_transfer_round_trip(self):
        received = []
        server = FileReceiverServer(
            self.download_dir, port=_PORT_SECRET, ssl_context=self.server_ctx
        )
        server.on_file_received = lambda p: received.append(p)
        server.on_file_request = lambda name, size, ip: True
        server.get_secret_pin_callback = lambda name: "123456"
        server.start()
        try:
            content = b"secret data" * 10000
            src = self._make_source_file("secret.bin", content)
            sender = FileSender("127.0.0.1", _PORT_SECRET, self.client_ctx)
            sender.send_file(src, secret_pin="123456")
            self.assertTrue(_wait_for(lambda: len(received) == 1))
            with open(received[0], "rb") as f:
                self.assertEqual(f.read(), content)
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()
