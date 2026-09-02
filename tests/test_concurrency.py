"""
Thread-safety test for DeviceManager mDNS registration under concurrent load.
Moved from a root-level script into the pytest suite.
"""

import threading
import time
import unittest

from pardus_paylasim.discovery.device_manager import DeviceManager


class TestDeviceManagerConcurrency(unittest.TestCase):
    def test_concurrent_mdns_registration(self):
        manager = DeviceManager()

        def add_devices(prefix, count):
            for i in range(count):
                manager._on_mdns_found(
                    f"{prefix}_device_{i}",
                    f"192.168.1.{i % 255}",
                    5000,
                    {"type": "test", "ip": f"10.0.{i % 255}.{i % 255}"},
                )
                time.sleep(0.001)

        threads = [
            threading.Thread(target=add_devices, args=(f"thread_{i}", 100)) for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        devices = manager.get_devices()
        self.assertGreater(len(devices), 0)


if __name__ == "__main__":
    unittest.main()
