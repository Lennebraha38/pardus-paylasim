"""
Cihazlar arası pano paylaşımı (ClipboardSyncClient/Server) uçtan-uca testleri.
"""

import socket
import struct
import time
import unittest

from pardus_paylasim.discovery.clipboard_sync import (
    ClipboardSyncClient,
    ClipboardSyncServer,
)

_PORT_OK = 8981
_PORT_MAGIC = 8982
_PORT_UNICODE = 8983


def _wait_for(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


class TestClipboardSync(unittest.TestCase):
    def test_round_trip(self):
        received = []
        server = ClipboardSyncServer(port=_PORT_OK)
        server.on_clipboard_received = lambda t, ip: received.append((t, ip))
        server.start()
        try:
            ClipboardSyncClient("127.0.0.1", _PORT_OK).send_text("merhaba pano")
            self.assertTrue(_wait_for(lambda: len(received) == 1))
            self.assertEqual(received[0][0], "merhaba pano")
            # Gönderen IP kaydedilmeli.
            self.assertTrue(received[0][1])
        finally:
            server.stop()

    def test_unicode_preserved(self):
        received = []
        server = ClipboardSyncServer(port=_PORT_UNICODE)
        server.on_clipboard_received = lambda t, ip: received.append(t)
        server.start()
        try:
            text = "Türkçe: şğüöçİ 日本語 😀"
            ClipboardSyncClient("127.0.0.1", _PORT_UNICODE).send_text(text)
            self.assertTrue(_wait_for(lambda: len(received) == 1))
            self.assertEqual(received[0], text)
        finally:
            server.stop()

    def test_wrong_magic_rejected(self):
        # Yanlış magic ile bağlanan istemci callback tetiklememeli.
        received = []
        server = ClipboardSyncServer(port=_PORT_MAGIC)
        server.on_clipboard_received = lambda t, ip: received.append(t)
        server.start()
        try:
            ack = b""
            # Sunucu yanlış magic'te bağlantıyı kapatır; sonraki sendall
            # Windows'ta abort edebilir — bu beklenen ret davranışıdır.
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(3)
                    s.connect(("127.0.0.1", _PORT_MAGIC))
                    s.sendall(b"XXXX")  # Yanlış magic
                    s.sendall(struct.pack("!I", 5))
                    s.sendall(b"hello")
                    ack = s.recv(1)
            except OSError:
                ack = b""
            time.sleep(0.3)
            self.assertEqual(received, [])
            self.assertNotEqual(ack, b"\x01")
        finally:
            server.stop()

    def test_oversize_raises_client_side(self):
        # 2 MiB üstü içerik istemci tarafında reddedilmeli.
        client = ClipboardSyncClient("127.0.0.1", _PORT_OK)
        huge = "a" * (2 * 1024 * 1024 + 1)
        with self.assertRaises(ValueError):
            client.send_text(huge)


if __name__ == "__main__":
    unittest.main()
