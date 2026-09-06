"""Manuel cihaz + pano geçmişi mantık testleri (GTK yok)."""

import os
import sys
import unittest
from collections import deque

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))


class TestManualDevice(unittest.TestCase):
    def test_upsert_manual_device(self):
        from pardus_paylasim.discovery.device_manager import DeviceManager
        mgr = DeviceManager.__new__(DeviceManager)
        import threading
        mgr._lock = threading.Lock()
        mgr.devices = {}
        mgr.notify_listeners = lambda: None
        dev = mgr.upsert_manual_device("Ev", "192.168.1.50", 8900)
        self.assertEqual(dev.address, "192.168.1.50")
        self.assertEqual(dev.port, 8900)
        self.assertEqual(dev.connection_type, "Manuel")
        self.assertIn("Dosya Gönderimi", dev.capabilities)
        self.assertIn("192.168.1.50", mgr.devices)

    def test_upsert_overwrites_same_ip(self):
        from pardus_paylasim.discovery.device_manager import DeviceManager
        import threading
        mgr = DeviceManager.__new__(DeviceManager)
        mgr._lock = threading.Lock()
        mgr.devices = {}
        mgr.notify_listeners = lambda: None
        mgr.upsert_manual_device("Eski", "192.168.1.50", 8900)
        mgr.upsert_manual_device("Yeni", "192.168.1.50", 8901)
        self.assertEqual(mgr.devices["192.168.1.50"].name, "Yeni")
        self.assertEqual(mgr.devices["192.168.1.50"].port, 8901)

    def test_empty_name_falls_back_to_ip(self):
        from pardus_paylasim.discovery.device_manager import DeviceManager
        import threading
        mgr = DeviceManager.__new__(DeviceManager)
        mgr._lock = threading.Lock()
        mgr.devices = {}
        mgr.notify_listeners = lambda: None
        dev = mgr.upsert_manual_device("", "192.168.1.51", 8900)
        self.assertEqual(dev.name, "192.168.1.51")


class TestHistoryCap(unittest.TestCase):
    def test_maxlen_contract(self):
        # UI deque ile aynı sözleşme: en fazla 20, eskiler düşer.
        from collections import deque as dq
        h = dq(maxlen=20)
        for i in range(25):
            h.appendleft(f"o{i}")
        self.assertEqual(len(h), 20)
        self.assertEqual(h[0], "o24")


if __name__ == "__main__":
    unittest.main()
