"""
Asenkron Transfer ve Geçmiş Senkronizasyonu.

Cihaz çevrimdışıyken gönderim yapılabilir. Karşı taraf çevrimiçi
olduğunda dosyalar otomatik olarak teslim edilir. Tüm asenkron
transferler bir SQLite veritabanında saklanır.
"""

import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

DB_PATH = os.path.expanduser("~/.local/share/pardus-paylasim/async_transfers.db")


@dataclass
class AsyncTransfer:
    """Bir asenkron transfer kaydı."""

    id: str
    file_name: str
    file_size: int
    file_hash: str
    sender_id: str
    sender_name: str
    receiver_id: str
    status: str  # pending, delivered, failed, cancelled
    file_path: str
    created_at: float = field(default_factory=time.time)
    delivered_at: Optional[float] = None
    attempts: int = 0
    last_attempt: Optional[float] = None


class AsyncTransferStore:
    """Asenkron transferleri SQLite'da saklar."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.Error:
            pass
        self._init_db()

    def close(self):
        """Veritabanı bağlantısını kapatır."""
        with self._lock:
            try:
                self._conn.commit()
                self._conn.close()
            except sqlite3.Error:
                pass

    def _init_db(self):
        with self._lock:
            conn = self._conn
            conn.execute("""
                CREATE TABLE IF NOT EXISTS async_transfers (
                    id TEXT PRIMARY KEY,
                    file_name TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    file_hash TEXT NOT NULL,
                    sender_id TEXT NOT NULL,
                    sender_name TEXT,
                    receiver_id TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    file_path TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    delivered_at REAL,
                    attempts INTEGER DEFAULT 0,
                    last_attempt REAL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS transfer_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transfer_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    event_data TEXT,
                    timestamp REAL NOT NULL,
                    peer_id TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_pending
                ON async_transfers(status, receiver_id)
            """)
            conn.commit()

    def queue_transfer(self, transfer: AsyncTransfer) -> bool:
        """Yeni bir asenkron transfer kuyruğa ekler."""
        with self._lock:
            try:
                conn = self._conn
                conn.execute(
                    """
                    INSERT OR REPLACE INTO async_transfers
                    (id, file_name, file_size, file_hash, sender_id,
                     sender_name, receiver_id, status, file_path,
                     created_at, attempts, last_attempt)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        transfer.id,
                        transfer.file_name,
                        transfer.file_size,
                        transfer.file_hash,
                        transfer.sender_id,
                        transfer.sender_name,
                        transfer.receiver_id,
                        transfer.status,
                        transfer.file_path,
                        transfer.created_at,
                        transfer.attempts,
                        transfer.last_attempt,
                    ),
                )
                conn.commit()
                self._log_event(transfer.id, "queued", {"file_name": transfer.file_name})
                return True
            except Exception as e:
                logger.error("Transfer kuyruğa eklenemedi: %s", e)
                return False

    def get_pending_for_receiver(self, receiver_id: str) -> List[AsyncTransfer]:
        """Bir alıcı için bekleyen transferleri döndürür."""
        with self._lock:
            conn = self._conn
            rows = conn.execute(
                """
                SELECT id, file_name, file_size, file_hash, sender_id,
                       sender_name, receiver_id, status, file_path,
                       created_at, delivered_at, attempts, last_attempt
                FROM async_transfers
                WHERE receiver_id = ? AND status = 'pending'
                ORDER BY created_at ASC
                """,
                (receiver_id,),
            ).fetchall()
            return [self._row_to_transfer(r) for r in rows]

    def get_pending_for_sender(self, sender_id: str) -> List[AsyncTransfer]:
        """Bir gönderici tarafından yapılan bekleyen transferleri döndürür."""
        with self._lock:
            conn = self._conn
            rows = conn.execute(
                """
                SELECT id, file_name, file_size, file_hash, sender_id,
                       sender_name, receiver_id, status, file_path,
                       created_at, delivered_at, attempts, last_attempt
                FROM async_transfers
                WHERE sender_id = ? AND status = 'pending'
                ORDER BY created_at ASC
                """,
                (sender_id,),
            ).fetchall()
            return [self._row_to_transfer(r) for r in rows]

    def mark_delivered(self, transfer_id: str):
        """Transfer'i teslim edildi olarak işaretler."""
        with self._lock:
            conn = self._conn
            conn.execute(
                """
                UPDATE async_transfers
                SET status = 'delivered', delivered_at = ?
                WHERE id = ?
                """,
                (time.time(), transfer_id),
            )
            conn.commit()
            self._log_event(transfer_id, "delivered", {})

    def mark_failed(self, transfer_id: str):
        with self._lock:
            conn = self._conn
            conn.execute(
                """
                UPDATE async_transfers
                SET status = 'failed', attempts = attempts + 1,
                    last_attempt = ?
                WHERE id = ?
                """,
                (time.time(), transfer_id),
            )
            conn.commit()
            self._log_event(transfer_id, "failed", {})

    def cancel_transfer(self, transfer_id: str):
        with self._lock:
            conn = self._conn
            conn.execute(
                "UPDATE async_transfers SET status = 'cancelled' WHERE id = ?",
                (transfer_id,),
            )
            conn.commit()
            self._log_event(transfer_id, "cancelled", {})

    def get_transfer_by_hash(self, file_hash: str) -> Optional[AsyncTransfer]:
        """Belirli bir hash'e sahip transferi bulur (dedup için)."""
        with self._lock:
            conn = self._conn
            row = conn.execute(
                """
                SELECT id, file_name, file_size, file_hash, sender_id,
                       sender_name, receiver_id, status, file_path,
                       created_at, delivered_at, attempts, last_attempt
                FROM async_transfers WHERE file_hash = ?
                """,
                (file_hash,),
            ).fetchone()
            return self._row_to_transfer(row) if row else None

    def get_history(
        self, transfer_id: str, limit: int = 50
    ) -> List[Dict]:
        """Bir transferin olay geçmişini döndürür."""
        with self._lock:
            conn = self._conn
            rows = conn.execute(
                """
                SELECT event_type, event_data, timestamp, peer_id
                FROM transfer_history
                WHERE transfer_id = ?
                ORDER BY timestamp DESC LIMIT ?
                """,
                (transfer_id, limit),
            ).fetchall()
            return [
                {
                    "type": r[0],
                    "data": json.loads(r[1]) if r[1] else {},
                    "timestamp": r[2],
                    "peer_id": r[3],
                }
                for r in rows
            ]

    def _row_to_transfer(self, row) -> AsyncTransfer:
        return AsyncTransfer(
            id=row[0],
            file_name=row[1],
            file_size=row[2],
            file_hash=row[3],
            sender_id=row[4],
            sender_name=row[5],
            receiver_id=row[6],
            status=row[7],
            file_path=row[8],
            created_at=row[9],
            delivered_at=row[10],
            attempts=row[11] or 0,
            last_attempt=row[12],
        )

    def _log_event(self, transfer_id: str, event_type: str, data: dict):
        try:
            conn = self._conn
            conn.execute(
                """
                INSERT INTO transfer_history
                (transfer_id, event_type, event_data, timestamp)
                VALUES (?, ?, ?, ?)
                """,
                (transfer_id, event_type, json.dumps(data), time.time()),
            )
            conn.commit()
        except Exception as e:
            logger.debug("Olay günlüğü hatası: %s", e)


class AsyncTransferManager:
    """Asenkron transfer iş akışını yönetir."""

    def __init__(
        self,
        device_id: str,
        device_name: str,
        store: Optional[AsyncTransferStore] = None,
        on_transfer_ready: Optional[Callable[[AsyncTransfer], None]] = None,
    ):
        self.device_id = device_id
        self.device_name = device_name
        self.store = store or AsyncTransferStore()
        self.on_transfer_ready = on_transfer_ready
        self._pending_lock = threading.Lock()
        self._pending_devices: Dict[str, threading.Event] = {}

    def queue_offline(
        self,
        file_path: str,
        receiver_id: str,
        receiver_name: str,
    ) -> Optional[str]:
        """Dosyayı alıcı çevrimdışıysa kuyruğa ekler."""
        if not os.path.exists(file_path):
            logger.error("Dosya bulunamadı: %s", file_path)
            return None

        file_size = os.path.getsize(file_path)
        digest = hashlib.sha256()
        with open(file_path, "rb") as hf:
            for piece in iter(lambda: hf.read(1024 * 1024), b""):
                digest.update(piece)
        file_hash = digest.hexdigest()

        existing = self.store.get_transfer_by_hash(file_hash)
        if existing and existing.status == "delivered":
            logger.info("Bu dosya zaten teslim edilmiş: %s", existing.id)
            return None

        import uuid

        tid = str(uuid.uuid4())
        transfer = AsyncTransfer(
            id=tid,
            file_name=os.path.basename(file_path),
            file_size=file_size,
            file_hash=file_hash,
            sender_id=self.device_id,
            sender_name=self.device_name,
            receiver_id=receiver_id,
            status="pending",
            file_path=file_path,
        )
        self.store.queue_transfer(transfer)
        logger.info(
            "Asenkron transfer kuyruğa eklendi: %s -> %s (%s)",
            self.device_id, receiver_id, transfer.file_name,
        )
        return tid

    def check_pending_for(self, peer_id: str) -> List[AsyncTransfer]:
        """Bir eş çevrimiçi olduğunda bekleyen transferlerini döndürür."""
        pending = self.store.get_pending_for_receiver(peer_id)
        for t in pending:
            self.store.mark_delivered(t.id)
            if self.on_transfer_ready:
                self.on_transfer_ready(t)
        return pending

    def sync_to_peer(self, peer_id: str) -> List[AsyncTransfer]:
        """Bir eşe gönderilmesi gereken bekleyen transferleri döndürür."""
        return self.store.get_pending_for_sender(peer_id)

    def cancel(self, transfer_id: str):
        self.store.cancel_transfer(transfer_id)
