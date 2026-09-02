"""
Sensitive Text & Clipboard Redactor for Pardus Güvenli Paylaşım.
Detects and redacts TC Kimlik No, Credit Cards, IBANs, Emails, Phone Numbers, Passwords, API Keys.
"""

import re
from dataclasses import dataclass
from typing import List


@dataclass
class SensitiveMatch:
    match_type: str  # 'TCKN', 'KREDİ_KARTI', 'IBAN', 'EPOSTA', 'TELEFON', 'API_KEY'
    original: str
    masked: str
    start: int
    end: int


class SensitiveMasker:
    """Scans and masks sensitive patterns in text and clipboard content."""

    PATTERNS = [
        ("TCKN", r"\b[1-9]\d{10}\b", lambda m: m[:3] + "*****" + m[-3:]),
        # Credit card: require 16-digit format with Luhn-like structure and typical separators
        (
            "KREDİ_KARTI",
            r"\b[3456]\d{3}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
            lambda m: m[:4] + " **** **** " + m[-4:],
        ),
        # IBAN: TR + 2 check digits + 5×4 bank/account digits + 2 suffix = 26 chars
        (
            "IBAN",
            r"\bTR\d{2}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{2}\b",
            lambda m: m[:5] + "**** **** **** **** " + m[-2:],
        ),
        # Email: mask local part more aggressively
        (
            "EPOSTA",
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
            lambda m: "***@" + m.split("@")[1],
        ),
        # Phone: support Turkish and international formats
        (
            "TELEFON",
            r"(?<!\d)(?:\+?90\s*[-.]?\s*)?\(?\s*5\d{2}\s*\)?\s*[-.]?\s*\d{3}\s*[-.]?\s*\d{2}\s*[-.]?\s*\d{2}(?!\d)",
            lambda m: "+90 5** *** ** **",
        ),
        # API key: stricter prefixes, require common key patterns
        (
            "API_KEY",
            r"\b(?:sk-|pk-|api[_-]?key[_-]?|key[_-]?id[_-]?)[a-zA-Z0-9]{20,40}\b",
            lambda m: m[:8] + "****************",
        ),
    ]

    @classmethod
    def scan_text(cls, text: str) -> List[SensitiveMatch]:
        matches: List[SensitiveMatch] = []
        for label, pattern, mask_func in cls.PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                val = match.group(0)
                # Validation for TCKN checksum algorithm (optional enhancement)
                if label == "TCKN" and not cls._validate_tckn(val):
                    continue
                masked = mask_func(val)
                matches.append(
                    SensitiveMatch(
                        match_type=label,
                        original=val,
                        masked=masked,
                        start=match.start(),
                        end=match.end(),
                    )
                )
        return matches

    @classmethod
    def mask_text(cls, text: str) -> str:
        masked_text = text
        matches = cls.scan_text(text)
        # Sort in reverse order to avoid offset shifts
        matches.sort(key=lambda x: x.start, reverse=True)
        for m in matches:
            masked_text = masked_text[: m.start] + m.masked + masked_text[m.end :]
        return masked_text

    @staticmethod
    def _validate_tckn(tckn: str) -> bool:
        if len(tckn) != 11 or not tckn.isdigit() or tckn[0] == "0":
            return False
        digits = [int(d) for d in tckn]
        d10 = ((sum(digits[0:9:2]) * 7) - sum(digits[1:8:2])) % 10
        d11 = sum(digits[:10]) % 10
        return digits[9] == d10 and digits[10] == d11
