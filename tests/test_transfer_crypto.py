"""
Round-trip + tamper tests for the encrypted transfer KDF/AEAD layer.
Regression guard after the PBKDF2 hardening (salt|nonce|ciphertext wire format).
"""

import unittest

from pardus_paylasim.discovery import transfer


@unittest.skipUnless(transfer.HAS_CRYPTO, "cryptography not installed")
class TestTransferCrypto(unittest.TestCase):
    def test_encrypt_decrypt_round_trip(self):
        pin = "123456"
        data = b"Gizli belge icerigi \x00\x01\xff pardus"
        blob = transfer.encrypt_data(pin, data)
        self.assertEqual(transfer.decrypt_data(pin, blob), data)

    def test_wire_format_has_salt_and_nonce(self):
        blob = transfer.encrypt_data("000000", b"x")
        # salt(16) + nonce(12) + ciphertext(>=1 + 16 GCM tag)
        self.assertGreater(len(blob), transfer.SALT_LEN + transfer.NONCE_LEN)

    def test_salt_is_random_per_message(self):
        d = b"same payload"
        a = transfer.encrypt_data("111111", d)
        b = transfer.encrypt_data("111111", d)
        self.assertNotEqual(a[: transfer.SALT_LEN], b[: transfer.SALT_LEN])

    def test_wrong_pin_fails(self):
        blob = transfer.encrypt_data("222222", b"secret")
        with self.assertRaises(Exception):
            transfer.decrypt_data("999999", blob)

    def test_tampered_ciphertext_fails(self):
        blob = bytearray(transfer.encrypt_data("333333", b"secret"))
        blob[-1] ^= 0x01  # flip a tag/ciphertext bit
        with self.assertRaises(Exception):
            transfer.decrypt_data("333333", bytes(blob))


if __name__ == "__main__":
    unittest.main()
