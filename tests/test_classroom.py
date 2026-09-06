"""Sınıf Modu testleri: yayın mantığı + UI bağlantısı (GTK yok)."""

import os
import sys
import unittest
from types import SimpleNamespace

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))


def _dev(ip, port=8901):
    return SimpleNamespace(address=ip, name=f"Cihaz-{ip}",
                           service_ports={"clip_port": port})


class TestBroadcast(unittest.TestCase):
    def test_empty_text_rejected(self):
        from pardus_paylasim.discovery.classroom import broadcast_text
        with self.assertRaises(ValueError):
            broadcast_text([_dev("10.0.0.1")], "   ")

    def test_no_devices_empty_result(self):
        from pardus_paylasim.discovery.classroom import broadcast_text
        self.assertEqual(broadcast_text([], "merhaba"), {})

    def test_success_and_failure_per_device(self):
        import pardus_paylasim.discovery.clipboard_sync as CS

        calls = []

        class FakeClient:
            def __init__(self, ip, port):
                self.ip = ip

            def send_text(self, text, timeout=5.0):
                calls.append((self.ip, text))
                if self.ip == "10.0.0.2":
                    raise OSError("kapali")

        real = CS.ClipboardSyncClient
        CS.ClipboardSyncClient = FakeClient
        try:
            from pardus_paylasim.discovery.classroom import broadcast_text
            res = broadcast_text([_dev("10.0.0.1"), _dev("10.0.0.2")],
                                 "duyuru")
        finally:
            CS.ClipboardSyncClient = real
        self.assertEqual(res, {"10.0.0.1": True, "10.0.0.2": False})
        self.assertEqual(len(calls), 2)

    def test_summarize(self):
        from pardus_paylasim.discovery.classroom import summarize_broadcast
        self.assertIn("2/3", summarize_broadcast(
            {"a": True, "b": True, "c": False}))

    def test_roles_defined(self):
        from pardus_paylasim.discovery.classroom import (
            ROLES, ROLE_BOARD, ROLE_TEACHER,
        )
        self.assertIn(ROLE_TEACHER, ROLES)
        self.assertIn(ROLE_BOARD, ROLES)


if __name__ == "__main__":
    unittest.main()
