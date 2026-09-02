"""
Ekran paylaşımı için PIN kodu eşleştirme yöneticisi (AirPlay/Sidecar tarzı
yetkilendirme).

Güvenlik notları:
- PIN karşılaştırması sabit-zamanlı (`hmac.compare_digest`) yapılır; PIN'in
  kaç hanesinin doğru olduğunu sızdıran zamanlama yan-kanalını kapatır.
- IP başına kaba-kuvvet (brute-force) koruması: ardışık yanlış PIN denemeleri
  eşiği aşınca ilgili IP geçici olarak kilitlenir.
"""

import hmac
import logging
import secrets
import threading
import time
from typing import Dict

logger = logging.getLogger(__name__)

# --- Ayarlanabilir güvenlik/zamanlama sabitleri (sihirli sayı yok) ---
# Bekleyen bir PIN talebinin geçerlilik süresi (saniye).
_PIN_TTL_SECONDS = 180
# Bu sayıda ardışık yanlış denemeden sonra IP kilitlenir.
_MAX_FAILED_ATTEMPTS = 5
# Kilit süresi (saniye).
_LOCKOUT_SECONDS = 60
# Üretilen PIN aralığı (6 haneli).
_PIN_MIN = 100_000
_PIN_MAX = 999_999


class ScreenPairingManager:
    """6 haneli PIN üretimi ve eşleştirme taleplerini yönetir. Thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # target_ip -> {pin, name, timestamp, verified}
        self.pending_pairs: Dict[str, dict] = {}
        self._fail_counts: Dict[str, int] = {}
        self._blocked_until: Dict[str, float] = {}

    def _cleanup_expired(self) -> None:
        """Süresi dolan PIN taleplerini ve biten kilitleri temizler.

        Kilit yöneticisiyle (lock) çağrılmalıdır. Süresi biten kilitlerin
        proaktif temizlenmesi, hiç geri dönmeyen IP'ler için sözlüklerin
        sınırsız büyümesini engeller (davranış-koruyucu: biten kilit zaten
        `verify_pin` içinde tembel olarak kaldırılıyordu)."""
        now = time.time()

        expired_pairs = [
            ip
            for ip, req in self.pending_pairs.items()
            if now - req["timestamp"] > _PIN_TTL_SECONDS
        ]
        for ip in expired_pairs:
            del self.pending_pairs[ip]

        # Süresi biten kilitleri ve onlara ait deneme sayaçlarını temizle.
        expired_blocks = [ip for ip, until in self._blocked_until.items() if now >= until]
        for ip in expired_blocks:
            del self._blocked_until[ip]
            self._fail_counts.pop(ip, None)

    def generate_pin_for_request(self, client_ip: str, client_name: str) -> str:
        """İstemci IP'si için yeni 6 haneli PIN üretir ve bekleyen talebe yazar."""
        pin = f"{_PIN_MIN + secrets.randbelow(_PIN_MAX - _PIN_MIN + 1)}"
        with self._lock:
            self._cleanup_expired()
            self.pending_pairs[client_ip] = {
                "pin": pin,
                "name": client_name,
                "timestamp": time.time(),
                "verified": False,
            }
        return pin

    def verify_pin(self, client_ip: str, entered_pin: str) -> bool:
        """Girilen PIN'i doğrular; kaba-kuvvet kilidi ve TTL uygular.

        Doğru PIN -> True (talep silinir, yetki token ile devam etmeli).
        Yanlış PIN -> False; eşik aşılırsa IP `_LOCKOUT_SECONDS` boyunca kilitlenir.
        """
        with self._lock:
            # Kaba-kuvvet nedeniyle kilitli mi?
            if client_ip in self._blocked_until:
                if time.time() < self._blocked_until[client_ip]:
                    return False  # Hâlâ kilitli
                # Kilit süresi bitti: kilidi ve sayacı düşür.
                del self._blocked_until[client_ip]
                self._fail_counts.pop(client_ip, None)

            self._cleanup_expired()
            if client_ip not in self.pending_pairs:
                return False

            req = self.pending_pairs[client_ip]
            # TTL kontrolü (yarış durumuna karşı ikinci kez bakılır).
            if time.time() - req["timestamp"] > _PIN_TTL_SECONDS:
                del self.pending_pairs[client_ip]
                return False

            # Sabit-zamanlı karşılaştırma: zamanlama yan-kanalını kapatır.
            if hmac.compare_digest(req["pin"], entered_pin.strip()):
                del self.pending_pairs[client_ip]  # Faz 2: Talep silinir, IP-based trust YOK
                self._fail_counts.pop(client_ip, None)
                return True

            # Yanlış PIN: deneme sayacını artır, eşikte kilitle.
            fails = self._fail_counts.get(client_ip, 0) + 1
            self._fail_counts[client_ip] = fails
            if fails >= _MAX_FAILED_ATTEMPTS:
                self._blocked_until[client_ip] = time.time() + _LOCKOUT_SECONDS
                # Bekleyen talebi düşür; yeni PIN talebi gerekecek.
                del self.pending_pairs[client_ip]
                logger.warning(
                    "PIN kaba-kuvvet: %s IP'si %d başarısız denemeden sonra %d sn kilitlendi.",
                    client_ip,
                    fails,
                    _LOCKOUT_SECONDS,
                )
            return False

    def revoke_pin(self, client_ip: str) -> None:
        """Güvenlik ihlali durumunda PIN talebini düşürür."""
        with self._lock:
            self.pending_pairs.pop(client_ip, None)


class SessionManager:
    """Faz 2: IP-bağımsız, cryptographically random, kısa ömürlü oturum token'ları."""

    def __init__(self):
        self._lock = threading.Lock()
        self.sessions: Dict[str, dict] = {}
        self._SESSION_TTL = 3600  # 1 saat

    def create_session(self, capabilities=None) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self.sessions[token] = {
                "created_at": time.time(),
                "capabilities": capabilities or ["stream", "control"],
            }
        return token

    def verify_token(self, token: str) -> bool:
        if not token:
            return False
        with self._lock:
            if token in self.sessions:
                # TTL Kontrolü
                if time.time() - self.sessions[token]["created_at"] < self._SESSION_TTL:
                    return True
                else:
                    del self.sessions[token]
            return False

    def revoke_token(self, token: str) -> None:
        with self._lock:
            self.sessions.pop(token, None)

    def get_session_details(self, token: str) -> dict:
        """Tokena ait oturum detaylarını döndürür, yoksa None döner."""
        if self.verify_token(token):
            with self._lock:
                return self.sessions.get(token)
        return None
