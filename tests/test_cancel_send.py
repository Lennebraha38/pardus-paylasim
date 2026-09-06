"""İptal + --send CLI testleri (soket yok; iptal ağa çıkmadan doğrulanır)."""

import os
import sys
import tempfile
import threading
import unittest

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))


class TestCancelEvent(unittest.TestCase):
    def test_preset_cancel_raises_before_connect(self):
        from pardus_paylasim.discovery.transfer import (
            FileSender,
            FileTransferError,
        )
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"x" * 100)
            path = f.name
        try:
            ev = threading.Event()
            ev.set()
            sender = FileSender("127.0.0.1", 1)  # bağlanılamaz port bile denenmez
            with self.assertRaises(FileTransferError):
                sender.send_file(path, cancel_event=ev)
        finally:
            os.unlink(path)

    def test_no_cancel_flows_to_connect(self):
        from pardus_paylasim.discovery.transfer import (
            FileSender,
            FileTransferError,
        )
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"x" * 100)
            path = f.name
        try:
            sender = FileSender("127.0.0.1", 1)
            sender.ssl_context = None
            # Bağlantı reddedilmeli (iptal değil) — iptal yolu tetiklenmedi.
            with self.assertRaises(Exception) as ctx:
                sender.send_file(path, cancel_event=threading.Event())
            self.assertNotIn("iptal", str(ctx.exception).lower())
        finally:
            os.unlink(path)


class TestSendCLI(unittest.TestCase):
    def test_send_without_target_and_history_explains(self):
        from pardus_paylasim.app import PardusPaylasimApp
        with tempfile.TemporaryDirectory() as home:
            os.environ["HOME"] = home
            os.makedirs(os.path.join(home, ".local", "share",
                                      "pardus-paylasim"), exist_ok=True)
            src = os.path.join(home, "a.txt")
            with open(src, "w") as f:
                f.write("x")
            try:
                code = PardusPaylasimApp().run(["--send", src])
            finally:
                del os.environ["HOME"]
            # Hedef yok (GUI'de hiç gönderim yapılmadı) → açıklayıcı çıkış.
            self.assertEqual(code, 1)

    def test_send_missing_file_skipped(self):
        from pardus_paylasim.app import PardusPaylasimApp
        with tempfile.TemporaryDirectory() as home:
            os.environ["HOME"] = home
            try:
                code = PardusPaylasimApp().run(
                    ["--send", os.path.join(home, "yok.txt"),
                     "--to", "127.0.0.1:1"])
            finally:
                del os.environ["HOME"]
            self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
