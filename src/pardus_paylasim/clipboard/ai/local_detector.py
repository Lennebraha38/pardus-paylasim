"""
Yerel Yapay Zeka ile Hassas Veri Tespit.

Regex tabanlı tespitin ötesine geçerek, eğitilmiş bir ONNX modeli
kullanır. Çevrimdışı çalışır; veri hiçbir yere gönderilmez.

Yaklaşım:
- Bilinen tipler (TCKN, kredi kartı, IBAN) için kural tabanlı hızlı yol
- Belirsiz / yeni tipler için (API key, token, secret) ONNX inference
- Yüksek recall için ensemble: kural + model
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import onnxruntime as ort

    HAS_ONNX = True
except ImportError:
    HAS_ONNX = False


@dataclass
class AIDetection:
    """Bir yapay zeka tespit sonucu."""

    text: str
    start: int
    end: int
    label: str
    confidence: float
    method: str  # "rule" veya "model"
    severity: str = "YÜKSEK"  # KRİTİK, YÜKSEK, ORTA, DÜŞÜK


@dataclass
class AIResult:
    """Tüm tespitlerin birleşik sonucu."""

    detections: List[AIDetection] = field(default_factory=list)
    has_sensitive: bool = False
    max_severity: str = "DÜŞÜK"
    model_loaded: bool = False
    inference_time_ms: float = 0.0


class LocalSensitiveDetector:
    """
    Yerel yapay zeka hassas veri tespitçisi.

    Çevrimdışı çalışır. ONNX modeli isteğe bağlıdır; yoksa yalnız regex
    fallback kullanılır.
    """

    SEVERITY_ORDER = {"KRİTİK": 4, "YÜKSEK": 3, "ORTA": 2, "DÜŞÜK": 1}

    BUILTIN_RULES = {
        "tckn": {
            "pattern": r"\b[1-9]\d{9}[02468]\b",
            "validator": "_validate_tckn",
            "severity": "KRİTİK",
        },
        "credit_card": {
            "pattern": r"\b(?:\d[ -]*?){13,19}\b",
            "validator": "_validate_luhn",
            "severity": "KRİTİK",
        },
        "iban_tr": {
            "pattern": r"TR\d{2}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4}[\s]?\d{2}",
            "validator": "_validate_iban",
            "severity": "KRİTİK",
        },
        "email": {
            "pattern": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
            "validator": None,
            "severity": "ORTA",
        },
        "phone_tr": {
            "pattern": r"\b(?:\+90|0)?[ ]?(5\d{2})[ ]?(\d{3})[ ]?(\d{2})[ ]?(\d{2})\b",
            "validator": None,
            "severity": "ORTA",
        },
        "api_key": {
            "pattern": r"\b(?:sk|pk|api|key|token)[-_]?[A-Za-z0-9]{20,}\b",
            "validator": None,
            "severity": "YÜKSEK",
        },
        "private_key": {
            "pattern": r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----",
            "validator": None,
            "severity": "KRİTİK",
        },
        "jwt": {
            "pattern": r"\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b",
            "validator": None,
            "severity": "YÜKSEK",
        },
        "ipv4": {
            "pattern": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
            "validator": "_validate_ipv4",
            "severity": "DÜŞÜK",
        },
        "ssh_key": {
            "pattern": r"\bssh-(?:rsa|dss|ed25519|ecdsa) AAAA[A-Za-z0-9+/=]+\b",
            "validator": None,
            "severity": "KRİTİK",
        },
    }

    def __init__(self, model_path: Optional[str] = None, threshold: float = 0.85):
        self.threshold = threshold
        self.session: Optional["ort.InferenceSession"] = None
        self.tokenizer = None
        self.model_loaded = False

        if model_path and os.path.exists(model_path) and HAS_ONNX:
            try:
                self.session = ort.InferenceSession(
                    model_path, providers=["CPUExecutionProvider"]
                )
                self.model_loaded = True
                logger.info("Yerel AI modeli yüklendi: %s", model_path)
            except Exception as e:
                logger.error("Model yükleme hatası: %s", e)

    def detect(self, text: str) -> AIResult:
        """Metindeki tüm hassas verileri tespit eder."""
        import time

        start = time.time()
        result = AIResult(model_loaded=self.model_loaded)

        for match in self._rule_based_scan(text):
            result.detections.append(match)

        if self.model_loaded:
            try:
                for match in self._model_based_scan(text):
                    existing = self._find_overlap(result.detections, match)
                    if existing and existing.confidence >= match.confidence:
                        continue
                    result.detections.append(match)
            except Exception as e:
                logger.debug("Model inference hatası: %s", e)

        result.has_sensitive = len(result.detections) > 0
        if result.has_sensitive:
            result.max_severity = max(
                (d.severity for d in result.detections),
                key=lambda s: self.SEVERITY_ORDER.get(s, 0),
                default="DÜŞÜK",
            )

        result.inference_time_ms = (time.time() - start) * 1000
        return result

    def _rule_based_scan(self, text: str) -> List[AIDetection]:
        """Yerleşik kurallarla tespit yapar."""
        detections = []
        for label, rule in self.BUILTIN_RULES.items():
            try:
                for m in re.finditer(rule["pattern"], text):
                    matched = m.group(0)
                    if rule["validator"]:
                        valid = getattr(self, rule["validator"])(matched)
                        if not valid:
                            continue
                    detections.append(
                        AIDetection(
                            text=matched,
                            start=m.start(),
                            end=m.end(),
                            label=label,
                            confidence=1.0,
                            method="rule",
                            severity=rule["severity"],
                        )
                    )
            except re.error as e:
                logger.debug("Regex hatası %s: %s", label, e)
        return detections

    def _model_based_scan(self, text: str) -> List[AIDetection]:
        """ONNX modeli ile tespit yapar (placeholder, eğitilmiş model beklenir)."""
        if not self.session:
            return []

        detections = []
        try:
            chunks = self._chunk_text(text, max_len=128)
            for chunk_start, chunk in chunks:
                input_ids, attention_mask = self._tokenize(chunk)
                if input_ids is None:
                    continue
                outputs = self.session.run(
                    None,
                    {"input_ids": input_ids, "attention_mask": attention_mask},
                )
                for token_idx, score in self._extract_spans(outputs, chunk):
                    if score < self.threshold:
                        continue
                    abs_start = chunk_start + token_idx[0]
                    abs_end = chunk_start + token_idx[1]
                    detections.append(
                        AIDetection(
                            text=text[abs_start:abs_end],
                            start=abs_start,
                            end=abs_end,
                            label="model_guess",
                            confidence=float(score),
                            method="model",
                            severity="YÜKSEK",
                        )
                    )
        except Exception as e:
            logger.debug("Model çıkarım hatası: %s", e)
        return detections

    def _chunk_text(self, text: str, max_len: int = 128) -> List[Tuple[int, str]]:
        """Metni model için parçalara böler."""
        chunks = []
        i = 0
        while i < len(text):
            end = min(i + max_len, len(text))
            chunks.append((i, text[i:end]))
            i = end
        return chunks

    def _tokenize(self, text: str) -> Tuple[Optional[list], Optional[list]]:
        """Basit karakter düzeyinde tokenizasyon (model gerektirmez)."""
        if not text:
            return None, None
        ids = [min(ord(c), 32000) for c in text[:128]]
        mask = [1] * len(ids)
        return [ids], [mask]

    def _extract_spans(self, outputs, chunk: str) -> List[Tuple[Tuple[int, int], float]]:
        """Model çıktısından varlık aralıklarını çıkarır (placeholder)."""
        return []

    def _find_overlap(
        self, existing: List[AIDetection], candidate: AIDetection
    ) -> Optional[AIDetection]:
        """Mevcut tespitlerle örtüşme kontrol eder."""
        for d in existing:
            if d.label == candidate.label and d.start < candidate.end and candidate.start < d.end:
                return d
        return None

    @staticmethod
    def _validate_tckn(tckn: str) -> bool:
        if len(tckn) != 11 or not tckn.isdigit():
            return False
        if tckn[0] == "0":
            return False
        digits = [int(d) for d in tckn]
        d10 = (
            (digits[0] + digits[2] + digits[4] + digits[6] + digits[8]) * 7
            - (digits[1] + digits[3] + digits[5] + digits[7])
        ) % 10
        d11 = sum(digits[:10]) % 10
        return digits[9] == d10 and digits[10] == d11

    @staticmethod
    def _validate_luhn(card: str) -> bool:
        s = re.sub(r"[^\d]", "", card)
        if not (13 <= len(s) <= 19):
            return False
        total = 0
        parity = len(s) % 2
        for i, d in enumerate(s):
            n = int(d)
            if i % 2 == parity:
                n *= 2
                if n > 9:
                    n -= 9
            total += n
        return total % 10 == 0

    @staticmethod
    def _validate_iban(iban: str) -> bool:
        s = re.sub(r"\s+", "", iban).upper()
        if not s.startswith("TR") or len(s) != 26:
            return False
        rearranged = s[4:] + s[:4]
        numeric = ""
        for c in rearranged:
            if c.isdigit():
                numeric += c
            elif c.isalpha():
                numeric += str(ord(c) - 55)
            else:
                return False
        try:
            return int(numeric) % 97 == 1
        except ValueError:
            return False

    @staticmethod
    def _validate_ipv4(ip: str) -> bool:
        parts = ip.split(".")
        if len(parts) != 4:
            return False
        for p in parts:
            try:
                v = int(p)
                if not (0 <= v <= 255):
                    return False
            except ValueError:
                return False
        return True

    def mask_with_ai(self, text: str) -> str:
        """Tespit edilen tüm hassas verileri maskeler."""
        result = self.detect(text)
        if not result.detections:
            return text
        sorted_d = sorted(result.detections, key=lambda d: -d.start)
        masked = text
        for d in sorted_d:
            label = d.label
            visible = ""
            if label == "iban_tr":
                visible = masked[d.start:d.start + 5] + " **** " + masked[d.end - 2:d.end]
            elif label == "credit_card":
                visible = "**** **** **** " + masked[d.end - 4:d.end]
            elif label == "email":
                if "@" in d.text:
                    user, domain = d.text.split("@", 1)
                    visible = user[0] + "***@" + domain
                else:
                    visible = "***"
            elif label == "tckn":
                visible = masked[d.start:d.start + 3] + "*** **" + masked[d.end - 2:d.end]
            else:
                visible = "*" * min(8, d.end - d.start)
            masked = masked[:d.start] + visible + masked[d.end:]
        return masked
