"""
Unit tests for SensitiveMasker (TCKN, Credit Cards, IBAN, Email, Phone numbers).
"""

import unittest

from pardus_paylasim.clipboard.sensitive_masker import SensitiveMasker


class TestClipboardMasker(unittest.TestCase):
    def test_tckn_masking(self):
        sample = "Müşterinin T.C. Kimlik No: 10000000146."
        masked = SensitiveMasker.mask_text(sample)
        self.assertIn("100*****146", masked)
        self.assertNotIn("10000000146", masked)

    def test_email_masking(self):
        sample = "İletişim için tevfik@example.com adresi."
        masked = SensitiveMasker.mask_text(sample)
        self.assertIn("***@example.com", masked)
        self.assertNotIn("tevfik@example.com", masked)

    def test_iban_masking(self):
        sample = "TR33 0006 1005 1978 6457 8413 26 IBAN numarası"
        masked = SensitiveMasker.mask_text(sample)
        self.assertIn("TR33 **** **** **** **** 26", masked)

    def test_invalid_iban_not_masked(self):
        """Mod-97 başarısız IBAN maskelemeye tökezlememeli (doğrulama gerçek)."""
        sample = "TR33 0006 1005 1234 5678 9012 34 (hatalı çek hanesi)"
        masked = SensitiveMasker.mask_text(sample)
        self.assertIn("TR33 0006 1005 1234 5678 9012 34", masked)

    def test_valid_card_masked_with_luhn(self):
        sample = "Kart: 4111-1111-1111-1111 son kullanma 12/29"
        masked = SensitiveMasker.mask_text(sample)
        self.assertIn("4111 **** **** 1111", masked)

    def test_invalid_card_not_masked(self):
        """Luhn başarısız kart numarası maskelenmemeli."""
        sample = "Kart: 1234 5678 9012 3456"
        masked = SensitiveMasker.mask_text(sample)
        self.assertIn("1234 5678 9012 3456", masked)

    def test_password_masked(self):
        sample = "Şifre: Sup3rGizli1234 giriş için."
        masked = SensitiveMasker.mask_text(sample)
        self.assertIn("Şifre: ********", masked)
        self.assertNotIn("Sup3rGizli1234", masked)


if __name__ == "__main__":
    unittest.main()
