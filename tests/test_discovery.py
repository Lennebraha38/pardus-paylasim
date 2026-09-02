"""
Unit tests for DeviceManager & Discovery logic.
"""

import time
import unittest

from pardus_paylasim.discovery.device_manager import DeviceManager, PardusDevice


class TestDiscovery(unittest.TestCase):
    def test_device_manager_registration(self):
        mgr = DeviceManager(local_device_name="Test Pardus PC")
        discovered_list = []

        def callback(devices):
            discovered_list.clear()
            discovered_list.extend(devices)

        mgr.register_listener(callback)
        mgr.start_discovery()
        time.sleep(2)

        devices = mgr.get_devices()
        self.assertGreater(len(devices), 0)
        dev = devices[0]
        self.assertIsInstance(dev, PardusDevice)
        self.assertIsNotNone(dev.address)
        mgr.stop_discovery()


if __name__ == "__main__":
    unittest.main()
