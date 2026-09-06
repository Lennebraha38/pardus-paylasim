"""Parmak izi + güven deposu testleri (soket/ağ yok)."""

import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

FP_A = "a" * 64
FP_B = "b" * 64


class TestTrustStore(unittest.TestCase):
    def _store(self, tmp):
        from pardus_paylasim.auth.trust_store import TrustStore
        return TrustStore(file_path=os.path.join(tmp, "trust.json"))

    def test_record_and_lookup(self):
        from pardus_paylasim.auth.trust_store import TrustStore
        with tempfile.TemporaryDirectory() as tmp:
            s = self._store(tmp)
            self.assertTrue(s.record_pairing(FP_A, "Ev PC", "192.168.1.10"))
            self.assertTrue(s.is_trusted(FP_A))
            self.assertTrue(s.is_trusted(FP_A.upper()))  # büyük/küçük duyarsız
            found = s.find_by_ip("192.168.1.10")
            self.assertIsNotNone(found)
            self.assertEqual(found.device_name, "Ev PC")
            self.assertTrue(s.is_ip_trusted("192.168.1.10"))
            self.assertFalse(s.is_ip_trusted("192.168.1.99"))
            self.assertIsNone(s.find_by_ip(None))

    def test_invalid_fingerprint_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self._store(tmp)
            self.assertFalse(s.record_pairing("", "X", "1.1.1.1"))
            self.assertFalse(s.record_pairing("xyz", "X", "1.1.1.1"))
            self.assertFalse(s.record_pairing("a" * 63, "X", "1.1.1.1"))
            self.assertFalse(s.is_trusted("xyz"))

    def test_remove(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self._store(tmp)
            s.record_pairing(FP_A, "Ev", "192.168.1.10")
            s.remove_trusted_device(FP_A)
            self.assertFalse(s.is_trusted(FP_A))
            self.assertFalse(s.is_ip_trusted("192.168.1.10"))

    def test_persistence_and_old_format(self):
        import json
        from pardus_paylasim.auth.trust_store import TrustStore
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "trust.json")
            # Eski format (last_ip yok) okunabilmeli.
            with open(path, "w", encoding="utf-8") as f:
                json.dump({FP_B: {"device_name": "Ofis",
                                  "added_at": 123.0}}, f)
            s = TrustStore(file_path=path)
            self.assertTrue(s.is_trusted(FP_B))
            devs = s.get_all()
            self.assertEqual(len(devs), 1)
            self.assertIsNone(devs[0].last_ip)
            # Yeniden kaydetme last_ip ekler, okunabilir kalır.
            s.record_pairing(FP_B, "Ofis", "10.0.0.2")
            s2 = TrustStore(file_path=path)
            self.assertEqual(s2.find_by_ip("10.0.0.2").device_name, "Ofis")

    def test_should_auto_accept(self):
        from pardus_paylasim.auth.trust_store import TrustStore, should_auto_accept
        with tempfile.TemporaryDirectory() as tmp:
            s = self._store(tmp)
            # Ayar kapalıysa güvenilir bile olsa ret.
            s.record_pairing(FP_A, "Ev", "192.168.1.10")
            self.assertFalse(should_auto_accept("192.168.1.10", s, False))
            # Ayar açık + güvenilir -> kabul.
            self.assertTrue(should_auto_accept("192.168.1.10", s, True))
            # Ayar açık + bilinmeyen -> ret.
            self.assertFalse(should_auto_accept("192.168.1.99", s, True))
            self.assertFalse(should_auto_accept(None, s, True))

    def test_group_fingerprint(self):
        from pardus_paylasim.auth.trust_store import group_fingerprint
        g = group_fingerprint(FP_A)
        self.assertEqual(len(g.split(":")), 32)
        self.assertTrue(g.startswith("AA:AA"))
        self.assertEqual(group_fingerprint(""), "")


class TestMdnsFingerprintFlow(unittest.TestCase):
    def test_mdns_props_carry_fingerprint(self):
        from pardus_paylasim.discovery.device_manager import DeviceManager
        mgr = DeviceManager.__new__(DeviceManager)
        import threading
        mgr._lock = threading.Lock()
        mgr.devices = {}
        mgr._trusted_ids = set()
        mgr.notify_listeners = lambda: None
        props = {"os": "Pardus", "type": "Wi-Fi (mDNS)",
                 "file_share": "1", "fp": FP_A}
        mgr._on_mdns_found("EvPC", "192.168.1.20", 8900, props)
        dev = mgr.devices["192.168.1.20"]
        self.assertEqual(dev.fingerprint, FP_A)

    def test_mdns_without_fp_defaults_empty(self):
        from pardus_paylasim.discovery.device_manager import DeviceManager
        import threading
        mgr = DeviceManager.__new__(DeviceManager)
        mgr._lock = threading.Lock()
        mgr.devices = {}
        mgr._trusted_ids = set()
        mgr.notify_listeners = lambda: None
        mgr._on_mdns_found("EvPC", "192.168.1.21", 8900, {})
        self.assertEqual(mgr.devices["192.168.1.21"].fingerprint, "")

    def test_mdns_broken_fp_ignored(self):
        from pardus_paylasim.discovery.device_manager import DeviceManager
        import threading
        mgr = DeviceManager.__new__(DeviceManager)
        mgr._lock = threading.Lock()
        mgr.devices = {}
        mgr._trusted_ids = set()
        mgr.notify_listeners = lambda: None
        mgr._on_mdns_found("EvPC", "192.168.1.22", 8900, {"fp": "bozuk"})
        self.assertEqual(mgr.devices["192.168.1.22"].fingerprint, "")


class TestDeviceCert(unittest.TestCase):
    def test_no_crypto_raises_clear_error(self):
        from pardus_paylasim.screen import tls_util
        from pardus_paylasim.auth import trust_store as ts
        if tls_util.HAS_TLS:
            self.skipTest("cryptography kurulu; yokluk yolu test edilemez")
        with self.assertRaises(RuntimeError):
            tls_util.get_or_create_device_cert()
        self.assertEqual(ts.own_fingerprint(), "")


class TestQRFingerprint(unittest.TestCase):
    def test_fp_roundtrip(self):
        from pardus_paylasim.discovery import qr_pairing
        uri = qr_pairing.build_pairing_uri("Ev", ip="192.168.1.10",
                                           fingerprint=FP_A)
        self.assertIn("fp=", uri)
        info = qr_pairing.parse_pairing_uri(uri)
        self.assertEqual(info["fingerprint"], FP_A)

    def test_no_fp_backward_compat(self):
        from pardus_paylasim.discovery import qr_pairing
        uri = qr_pairing.build_pairing_uri("Ev", ip="192.168.1.10")
        self.assertNotIn("fp=", uri)
        info = qr_pairing.parse_pairing_uri(uri)
        self.assertEqual(info["fingerprint"], "")

    def test_broken_fp_ignored(self):
        from pardus_paylasim.discovery import qr_pairing
        uri = "pardus://pair?name=X&ip=10.0.0.1&fp=bozuk!"
        info = qr_pairing.parse_pairing_uri(uri)
        self.assertEqual(info["fingerprint"], "")


if __name__ == "__main__":
    unittest.main()
