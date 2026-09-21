import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from pardus_paylasim.clipboard.sensitive_masker import SensitiveMasker

test_cases = [
    # Valid TCKN (Fake generated for test: 10000000146 -> (1+0+0+0+1)*7 = 14. Even = 0+0+0+0=0. (14-0)%10 = 4. Sum = 1+0+0+0+0+0+0+0+1+4 = 6. 10000000146.
    "Valid TCKN: 10000000146",
    # Invalid TCKN (Wrong checksum)
    "Invalid TCKN: 12345678901",
    # Valid Credit Card
    "Credit Card: 4111-1111-1111-1111",
    # Valid IBAN (Mod-97)
    "My IBAN is TR33 0006 1005 1978 6457 8413 26",
    # Email
    "Contact me at user@example.com",
    # Phone
    "Call me maybe +90 532 123 45 67",
    # API Key
    "Secret: sk-abcdefghijklmnopqrstuvwxyz123456",
]

for t in test_cases:
    masked = SensitiveMasker.mask_text(t)
    print(f"Original: {t}")
    print(f"Masked:   {masked}")
    print("-" * 40)
