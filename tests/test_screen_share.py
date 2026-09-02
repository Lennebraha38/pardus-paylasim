"""
Unit tests for Screen Stream Server, Client & PIN Pairing.
"""

import time
import unittest

from pardus_paylasim.screen.pairing import ScreenPairingManager
from pardus_paylasim.screen.stream_client import ScreenStreamClient
from pardus_paylasim.screen.stream_server import ScreenStreamServer


class TestScreenShare(unittest.TestCase):
    def test_screen_pairing(self):
        mgr = ScreenPairingManager()
        pin = mgr.generate_pin_for_request("192.168.1.50", "Pardus Client")
        self.assertEqual(len(pin), 6)
        self.assertTrue(pin.isdigit())

        self.assertFalse(mgr.verify_pin("192.168.1.50", "000000"))
        self.assertTrue(mgr.verify_pin("192.168.1.50", pin))

    def test_pin_brute_force_lockout(self):
        # 5 ardışık yanlış deneme sonrası IP kilitlenmeli; kilit
        # aktifken doğru PIN dahi reddedilir (kaba-kuvvet koruması).
        mgr = ScreenPairingManager()
        attacker_ip = "10.0.0.7"
        real_pin = mgr.generate_pin_for_request(attacker_ip, "Saldırgan")

        # İlk 5 yanlış deneme: hepsi False döner, 5.'de kilit devreye girer.
        for _ in range(5):
            self.assertFalse(mgr.verify_pin(attacker_ip, "111111"))

        # Kilit aktif: doğru PIN bile reddedilmeli.
        self.assertFalse(mgr.verify_pin(attacker_ip, real_pin))

    def test_pin_lockout_isolated_per_ip(self):
        # Bir IP'nin kilidi başka IP'yi etkilememeli.
        mgr = ScreenPairingManager()
        blocked_ip = "10.0.0.8"
        clean_ip = "10.0.0.9"
        mgr.generate_pin_for_request(blocked_ip, "Kötü")
        good_pin = mgr.generate_pin_for_request(clean_ip, "İyi")

        for _ in range(5):
            mgr.verify_pin(blocked_ip, "999999")

        # Temiz IP hâlâ doğrulanabilmeli.
        self.assertTrue(mgr.verify_pin(clean_ip, good_pin))

    def test_screen_server_client(self):
        server = ScreenStreamServer(port=52349)
        pin = server.start_server()
        self.assertEqual(len(pin), 6)
        time.sleep(0.5)

        client = ScreenStreamClient()
        client.target_ip = "127.0.0.1"
        client.target_port = 52349
        client.target_device_id = "test-device"
        client.use_tls = server.tls_enabled
        received_frames = []

        def on_frame(b):
            received_frames.append(b)

        import unittest.mock

        with unittest.mock.patch(
            "pardus_paylasim.screen.trust_store.get_trusted_fingerprint",
            return_value=server.cert_fingerprint,
        ):
            connected = client.connect_to_stream(
                "127.0.0.1", 52349, pin, on_frame, device_id="test-device"
            )
        self.assertTrue(connected)
        time.sleep(1)

        client.disconnect()
        server.stop_server()


if __name__ == "__main__":
    unittest.main()
