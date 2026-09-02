"""
End-to-end Integration Test for Pardus Güvenli Paylaşım application.
"""

import unittest

from pardus_paylasim.cleaner.metadata_cleaner import MetadataCleaner
from pardus_paylasim.clipboard.sensitive_masker import SensitiveMasker
from pardus_paylasim.discovery.device_manager import DeviceManager
from pardus_paylasim.screen.stream_server import ScreenStreamServer


class TestIntegration(unittest.TestCase):
    def test_full_application_stack(self):
        # 1. Cleaner
        cleaner = MetadataCleaner()
        self.assertIsNotNone(cleaner)

        # 2. Discovery
        dm = DeviceManager(local_device_name="Pardus Test Suite")
        dm.start_discovery()
        dm.stop_discovery()

        # 3. Screen Server
        srv = ScreenStreamServer(port=52399)
        pin = srv.start_server()
        self.assertEqual(len(pin), 6)
        srv.stop_server()

        # 4. Clipboard
        masked = SensitiveMasker.mask_text("E-posta: demo@pardus.org.tr")
        self.assertIn("***@pardus.org.tr", masked)


if __name__ == "__main__":
    unittest.main()
