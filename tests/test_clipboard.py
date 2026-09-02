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
        sample = "TR33 0006 1005 1234 5678 9012 34 IBAN numarası"
        masked = SensitiveMasker.mask_text(sample)
        self.assertIn("TR33 **** **** **** **** 34", masked)


if __name__ == "__main__":
    unittest.main()
