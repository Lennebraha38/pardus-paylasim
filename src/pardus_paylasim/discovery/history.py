"""
Transfer geçmişi / denetim (audit) günlüğü.

Gönderilen ve alınan dosyaları JSONL (satır-başı-bir-JSON) biçiminde kalıcı
saklar. Her kayıt tek satır → eşzamanlı ekleme güvenli, kısmi yazımda yalnız
son satır bozulur (dosyanın tamamı değil).

Konum: ~/.config/pardus-paylasim/transfer_history.jsonl (config.py ile aynı
XDG tabanı). Thread-safe: alıcı ve gönderici iş parçacıkları aynı anda
ekleyebilir.
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Geçmiş dosyası, config.json ile aynı dizinde tutulur.
_HISTORY_PATH = os.path.expanduser("~/.config/pardus-paylasim/transfer_history.jsonl")

# Geçerli yön (direction) değerleri.
DIRECTION_SENT = "sent"
DIRECTION_RECEIVED = "received"
# Uzaktan kontrol oturumu denetimi (audit): dosya değil, kontrol yetkisinin
# başlangıç/bitişini kaydeder (C4 — kontrol asla sessiz kalmaz).
DIRECTION_CONTROL = "control"

# Geçerli durum (status) değerleri.
STATUS_OK = "ok"
STATUS_REJECTED = "rejected"
STATUS_ERROR = "error"
# Kontrol oturumu durumları (direction="control" kayıtları için).
STATUS_CONTROL_START = "start"
STATUS_CONTROL_STOP = "stop"

# UI okuması için üst sınır (sınırsız dosya okumasını önler).
_DEFAULT_READ_LIMIT = 200


class TransferHistory:
    """Thread-safe JSONL transfer geçmişi deposu."""

    def __init__(self, path: Optional[str] = None) -> None:
        self._path = path or _HISTORY_PATH
        self._lock = threading.Lock()

    def _record(
        self,
        direction: str,
        file_name: str,
        size_bytes: int,
        peer: str,
        status: str,
        secret: bool,
    ) -> Dict:
        """Tek bir geçmiş kaydını (dict) oluşturup dosyaya ekler."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "direction": direction,
            "file_name": file_name,
            "size_bytes": int(size_bytes),
            "peer": peer or "",
            "status": status,
            "secret": bool(secret),
        }
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self._path), exist_ok=True)
                with open(self._path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except OSError as e:
                # Geçmiş yazımı başarısızlığı transferi bozmamalı; yalnız logla.
                logger.error("Transfer geçmişi yazılamadı: %s", e)
        return entry

    def add_sent(
        self,
        file_name: str,
        size_bytes: int,
        peer: str,
        status: str = STATUS_OK,
        secret: bool = False,
    ) -> Dict:
        """Gönderilen bir dosyayı geçmişe ekler."""
        return self._record(DIRECTION_SENT, file_name, size_bytes, peer, status, secret)

    def add_received(
        self,
        file_name: str,
        size_bytes: int,
        peer: str,
        status: str = STATUS_OK,
        secret: bool = False,
    ) -> Dict:
        """Alınan bir dosyayı geçmişe ekler."""
        return self._record(DIRECTION_RECEIVED, file_name, size_bytes, peer, status, secret)

    def add_control(
        self,
        peer: str,
        status: str,
        detail: str = "",
    ) -> Dict:
        """Uzaktan kontrol oturumu denetim kaydı ekler.

        `status` = STATUS_CONTROL_START (yetki verildi) ya da
        STATUS_CONTROL_STOP (yetki bitti/iptal). `detail` isteğe bağlı sebep
        (ör. "revoked", "disabled", "no_backend"). Dosya alanı, kontrolde dosya
        aktarımı olmadığı için sabit "-" ve boyut 0 tutulur.
        """
        return self._record(DIRECTION_CONTROL, detail or "-", 0, peer, status, False)

    def read_all(self, limit: int = _DEFAULT_READ_LIMIT) -> List[Dict]:
        """En yeni kayıtları (en fazla `limit` adet) yeni→eski döndürür.

        Bozuk satırlar sessizce atlanır (kısmi yazım toleransı).
        """
        with self._lock:
            if not os.path.exists(self._path):
                return []
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except OSError as e:
                logger.error("Transfer geçmişi okunamadı: %s", e)
                return []

        entries: List[Dict] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # Bozuk/kısmi satır: atla.

        entries.reverse()  # En yeni önce.
        return entries[:limit]

    def clear(self) -> None:
        """Tüm geçmişi siler (dosyayı kaldırır)."""
        with self._lock:
            try:
                if os.path.exists(self._path):
                    os.remove(self._path)
            except OSError as e:
                logger.error("Transfer geçmişi silinemedi: %s", e)
