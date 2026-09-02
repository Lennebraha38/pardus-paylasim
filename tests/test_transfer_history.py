"""
TransferHistory JSONL deposu birim testleri: ekleme, okuma sırası, bozuk-satır
toleransı, temizleme ve alıcı-sunucu entegrasyonu.
"""

import json
import os
import tempfile
import threading
import time
import unittest

from pardus_paylasim.discovery.history import (
    DIRECTION_RECEIVED,
    DIRECTION_SENT,
    STATUS_OK,
    TransferHistory,
)


class TestTransferHistory(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._tmp.name, "history.jsonl")
        self.history = TransferHistory(path=self.path)

    def tearDown(self):
        self._tmp.cleanup()

    def test_empty_history_returns_empty_list(self):
        self.assertEqual(self.history.read_all(), [])

    def test_add_sent_and_received(self):
        self.history.add_sent("a.txt", 100, "10.0.0.1", secret=True)
        self.history.add_received("b.pdf", 2048, "10.0.0.2")

        entries = self.history.read_all()
        self.assertEqual(len(entries), 2)
        # En yeni önce (received en son eklendi).
        self.assertEqual(entries[0]["direction"], DIRECTION_RECEIVED)
        self.assertEqual(entries[0]["file_name"], "b.pdf")
        self.assertEqual(entries[1]["direction"], DIRECTION_SENT)
        self.assertTrue(entries[1]["secret"])

    def test_record_has_required_fields(self):
        self.history.add_sent("x", 1, "ip")
        entry = self.history.read_all()[0]
        for key in (
            "timestamp",
            "direction",
            "file_name",
            "size_bytes",
            "peer",
            "status",
            "secret",
        ):
            self.assertIn(key, entry)
        self.assertEqual(entry["status"], STATUS_OK)

    def test_corrupt_line_is_skipped(self):
        self.history.add_sent("good.txt", 10, "ip")
        # Elle bozuk satır ekle.
        with open(self.path, "a", encoding="utf-8") as f:
            f.write("{ bozuk json satiri\n")
        self.history.add_received("good2.txt", 20, "ip")

        entries = self.history.read_all()
        # Bozuk satır atlanmalı; 2 geçerli kayıt kalmalı.
        self.assertEqual(len(entries), 2)

    def test_read_limit(self):
        for i in range(10):
            self.history.add_sent(f"f{i}", i, "ip")
        entries = self.history.read_all(limit=3)
        self.assertEqual(len(entries), 3)
        # En yeni f9 önce olmalı.
        self.assertEqual(entries[0]["file_name"], "f9")

    def test_clear_removes_all(self):
        self.history.add_sent("a", 1, "ip")
        self.history.clear()
        self.assertEqual(self.history.read_all(), [])
        self.assertFalse(os.path.exists(self.path))

    def test_concurrent_appends_are_safe(self):
        # 5 thread eşzamanlı ekler; hiçbir kayıt kaybolmamalı/bozulmamalı.
        def worker(n):
            for i in range(20):
                self.history.add_sent(f"t{n}_{i}", i, "ip")

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        entries = self.history.read_all(limit=1000)
        self.assertEqual(len(entries), 100)
        # Her satır geçerli JSON olmalı (bozulma yok).
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    json.loads(line)  # Raise ederse test düşer.


class TestReceiverHistoryIntegration(unittest.TestCase):
    """FileReceiverServer -> TransferHistory uçtan-uca kayıt."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.download_dir = self._tmp.name
        self.history = TransferHistory(path=os.path.join(self.download_dir, "h.jsonl"))

    def tearDown(self):
        self._tmp.cleanup()

    def test_received_file_is_logged(self):
        from pardus_paylasim.discovery.transfer import (
            FileReceiverServer,
            FileSender,
        )
        from pardus_paylasim.screen import tls_util

        cert, key, _ = tls_util.generate_self_signed_cert()
        server_ctx = tls_util.build_server_context(cert, key)
        client_ctx = tls_util.build_client_context(cert)

        server = FileReceiverServer(self.download_dir, port=8961, ssl_context=server_ctx)
        server.history = self.history
        server.on_file_request = lambda name, size, ip: True
        server.start()
        try:
            src = os.path.join(self.download_dir, "_kaynak.txt")
            with open(src, "wb") as f:
                f.write(b"veri")
            sender = FileSender("127.0.0.1", 8961)
            sender.ssl_context = client_ctx
            sender.send_file(src)

            deadline = time.time() + 5
            while time.time() < deadline and not self.history.read_all():
                time.sleep(0.05)

            entries = self.history.read_all()
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["direction"], "received")
            self.assertEqual(entries[0]["status"], "ok")
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()
