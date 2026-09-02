"""
QR eşleştirme URI kodlama/ayrıştırma ve görsel üretim testleri.
"""

import os
import tempfile
import unittest

from pardus_paylasim.discovery import qr_pairing


class TestPairingURI(unittest.TestCase):
    def test_round_trip(self):
        uri = qr_pairing.build_pairing_uri(
            "Ahmet Pardus",
            ip="192.168.1.42",
            file_port=8900,
            clip_port=8901,
            capabilities=["file", "clipboard"],
        )
        info = qr_pairing.parse_pairing_uri(uri)
        self.assertIsNotNone(info)
        self.assertEqual(info["name"], "Ahmet Pardus")
        self.assertEqual(info["ip"], "192.168.1.42")
        self.assertEqual(info["file_port"], 8900)
        self.assertEqual(info["clip_port"], 8901)
        self.assertEqual(info["capabilities"], ["file", "clipboard"])

    def test_scheme_prefix(self):
        uri = qr_pairing.build_pairing_uri("X", ip="10.0.0.1")
        self.assertTrue(uri.startswith("pardus://pair?"))

    def test_special_chars_in_name(self):
        # Türkçe + boşluk + '&' gibi karakterler URI-kodlanıp geri çözülmeli.
        name = "Zeynep'in Pardus & Laptop'ı"
        uri = qr_pairing.build_pairing_uri(name, ip="10.0.0.5")
        info = qr_pairing.parse_pairing_uri(uri)
        self.assertEqual(info["name"], name)

    def test_default_ports_when_missing(self):
        # Yalnız zorunlu alanlar → portlar varsayılana düşmeli.
        uri = "pardus://pair?name=Test&ip=10.0.0.9"
        info = qr_pairing.parse_pairing_uri(uri)
        self.assertEqual(info["file_port"], 8900)
        self.assertEqual(info["clip_port"], 8901)
        self.assertEqual(info["capabilities"], [])

    def test_invalid_scheme_returns_none(self):
        self.assertIsNone(qr_pairing.parse_pairing_uri("http://pair?name=x&ip=y"))

    def test_missing_required_fields_returns_none(self):
        # ip yok → None.
        self.assertIsNone(qr_pairing.parse_pairing_uri("pardus://pair?name=x"))

    def test_garbage_returns_none(self):
        self.assertIsNone(qr_pairing.parse_pairing_uri("bu bir uri degil"))

    def test_get_local_ip_returns_string(self):
        ip = qr_pairing.get_local_ip()
        self.assertIsInstance(ip, str)
        self.assertTrue(len(ip.split(".")) == 4)


@unittest.skipUnless(qr_pairing.HAS_QRCODE, "qrcode kütüphanesi kurulu değil")
class TestQRGeneration(unittest.TestCase):
    def test_generate_png(self):
        uri = qr_pairing.build_pairing_uri("Test", ip="10.0.0.1")
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "qr.png")
            ok = qr_pairing.generate_qr_png(uri, path)
            self.assertTrue(ok)
            self.assertTrue(os.path.exists(path))
            self.assertGreater(os.path.getsize(path), 0)

    def test_generate_ascii(self):
        uri = qr_pairing.build_pairing_uri("Test", ip="10.0.0.1")
        ascii_qr = qr_pairing.generate_qr_ascii(uri)
        self.assertIsInstance(ascii_qr, str)
        self.assertGreater(len(ascii_qr), 0)


class TestQRGracefulFallback(unittest.TestCase):
    def test_png_returns_false_without_lib(self):
        # qrcode yoksa generate_qr_png False dönmeli (istisna atmamalı).
        if qr_pairing.HAS_QRCODE:
            self.skipTest("qrcode kurulu; fallback yolu test edilemez")
        uri = qr_pairing.build_pairing_uri("Test", ip="10.0.0.1")
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "qr.png")
            self.assertFalse(qr_pairing.generate_qr_png(uri, path))


if __name__ == "__main__":
    unittest.main()
