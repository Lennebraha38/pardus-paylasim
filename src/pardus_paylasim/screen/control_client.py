"""
Uzaktan kontrol kanalı istemcisi (`control_client`).

`control_server`'ın karşı tarafı: TLS-pinlenmiş MJPEG sunucusunun (port 52345)
`/control` uç noktasına RFC6455 WebSocket el sıkışması yapar, sonra yakalanan
girdi olaylarını (fare/klavye) tel protokolüyle (`control_protocol`) gönderir.

Görüntüleme istemcisiyle (`stream_client`) aynı güven kurulumunu yeniden
kullanır: `tls_util` self-signed sertifika + fingerprint pinning (TOFU) +
`X-Pardus-PIN` header. Böylece izleme ve kontrol tek eşleşmeyle kurulur.

Faz 1 katı consent akışı (`control_server` C4 ile eşleşir):
- El sıkışma sonrası sunucu tek bir `GrantEvent` gönderir. `allow=False` ise
  (host toggle kapalı / backend yok) kanal reddedilmiştir → istemci token
  alamaz, olay gönderemez.
- `allow=True` ise `session` token saklanır ve **her** giden olaya `sid` olarak
  iliştirilir; sunucu her mesajda doğrular → revoke sonrası ele geçirilmiş soket
  bile enjekte edemez.

Saf / headless-test edilebilir parçalar (soket/GTK gerektirmez):
- `map_widget_to_normalized(...)`: letterbox (aspect-fit) piksel → normalize
  0..1 koordinat eşlemesi. Widget/görüntü boyutlarından çizilen dikdörtgeni
  hesaplar, harf-kutusu (letterbox) ofsetini çıkarır, çizilen boyuta böler.
- `build_handshake_request(...)` / `parse_handshake_response(...)`: el sıkışma
  HTTP metninin saf kur/çöz'ü (BytesIO ile test).
- Çerçeve kur/oku (`control_server.build_client_frame` / `read_server_frame`)
  ve accept-key doğrulaması (`control_server.compute_accept_key`) yeniden
  kullanılır.
"""

from __future__ import annotations

import base64
import dataclasses
import logging
import secrets
import socket
import ssl
import struct
import threading
from typing import Optional, Tuple

from pardus_paylasim.screen import control_protocol as cp
from pardus_paylasim.screen import tls_util
from pardus_paylasim.screen.control_server import (
    CLOSE_NORMAL,
    OP_CLOSE,
    OP_PING,
    OP_PONG,
    OP_TEXT,
    FrameError,
    build_client_frame,
    compute_accept_key,
    encode_client_text_frame,
    read_server_frame,
)
from pardus_paylasim.screen.stream_config import DEFAULT_PORT

logger = logging.getLogger(__name__)

# WebSocket sürümü (RFC6455 §4.1 — sabit).
_WS_VERSION = "13"


# --- Saf koordinat eşleme (GTK'sız test edilebilir) --------------------------


def _clamp01(value: float) -> float:
    """Değeri [0.0, 1.0]'a kırp (fail-safe)."""
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def map_widget_to_normalized(
    widget_w: float,
    widget_h: float,
    image_w: float,
    image_h: float,
    px: float,
    py: float,
) -> Tuple[float, float]:
    """Widget piksel konumunu normalize 0..1 görüntü koordinatına eşle.

    Görüntü, en-boy oranı korunarak widget'a sığdırılır (aspect-fit): fazlalık
    kenarda harf-kutusu (letterbox/pillarbox) boşluğu kalır. Fare, çizilen
    görüntü dikdörtgeni içindeyken 0..1'e; dışındaysa (boşluğa taşınca) kenara
    kırpılır. Host bu 0..1 değeri gerçek ekran çözünürlüğüyle çarpar; böylece
    istemci host çözünürlüğünü bilmeden, akış-ortası çözünürlük değişse bile
    doğru konumu sürer.

    Saf fonksiyon: GTK/soket bağı yok → birim test edilebilir. Geçersiz
    (sıfır/negatif) boyutlarda güvenli (0.0, 0.0) döner.
    """
    if widget_w <= 0 or widget_h <= 0 or image_w <= 0 or image_h <= 0:
        return (0.0, 0.0)

    # Aspect-fit ölçek: her iki eksende sığacak en küçük ölçek.
    scale = min(widget_w / image_w, widget_h / image_h)
    drawn_w = image_w * scale
    drawn_h = image_h * scale

    # Çizilen dikdörtgen widget içinde ortalanır → harf-kutusu ofseti.
    offset_x = (widget_w - drawn_w) / 2.0
    offset_y = (widget_h - drawn_h) / 2.0

    if drawn_w <= 0 or drawn_h <= 0:
        return (0.0, 0.0)

    norm_x = (px - offset_x) / drawn_w
    norm_y = (py - offset_y) / drawn_h
    return (_clamp01(norm_x), _clamp01(norm_y))


# --- Saf el sıkışma metni (GTK'sız test edilebilir) --------------------------


def generate_ws_key() -> str:
    """Rastgele `Sec-WebSocket-Key` üret (16 bayt → base64, RFC6455 §4.1)."""
    return base64.b64encode(secrets.token_bytes(16)).decode("ascii")


def build_handshake_request(host: str, port: int, ws_key: str, pin: str = "") -> bytes:
    """`/control` WebSocket upgrade GET isteğini kur (istemci→sunucu).

    PIN URL'e değil `X-Pardus-PIN` header'ına konur (access-log/proxy sızıntısı
    yok — görüntüleme yoluyla aynı). Saf: soket gerektirmez → test edilebilir.
    """
    lines = [
        "GET /control HTTP/1.1",
        f"Host: {host}:{port}",
        "Upgrade: websocket",
        "Connection: Upgrade",
        f"Sec-WebSocket-Key: {ws_key}",
        f"Sec-WebSocket-Version: {_WS_VERSION}",
    ]
    if pin:
        lines.append(f"X-Pardus-PIN: {pin}")
    lines.append("")  # başlık bloğu sonu
    lines.append("")  # boş satır (CRLFCRLF)
    return "\r\n".join(lines).encode("ascii")


def parse_handshake_response(raw: bytes) -> Tuple[int, dict]:
    """El sıkışma yanıt başlıklarını çöz → (status_code, headers).

    `headers` küçük-harfli anahtarlı sözlük. Yalnız başlık bloğu beklenir
    (gövde WebSocket upgrade'de yok). Saf: test edilebilir.
    """
    text = raw.decode("iso-8859-1")
    head = text.split("\r\n\r\n", 1)[0]
    lines = head.split("\r\n")
    status_line = lines[0] if lines else ""
    # "HTTP/1.1 101 Switching Protocols"
    parts = status_line.split(" ", 2)
    try:
        status = int(parts[1]) if len(parts) >= 2 else 0
    except ValueError:
        status = 0
    headers: dict = {}
    for line in lines[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()
    return status, headers


def verify_accept(ws_key: str, accept_header: str) -> bool:
    """Sunucunun `Sec-WebSocket-Accept` değerini doğrula (RFC6455 §4.2.2).

    İstemci kendi ürettiği anahtardan beklenen accept'i hesaplar ve sabit-zaman
    karşılaştırır. Uyuşmazlık → sunucu WebSocket konuşmuyor / MITM → red.
    """
    expected = compute_accept_key(ws_key)
    return secrets.compare_digest(expected, accept_header or "")


# --- Saf GDK keyval / modifier eşleme (GTK'sız test edilebilir) ---------------
#
# GDK keyval değerleri X11 keysym tamsayılarıyla birebir aynıdır (kararlı,
# sürümden bağımsız). Aşağıdaki tablo bunları layout-bağımsız `KEY_*` enum'a
# çevirir. FİZİKSEL tuş temel alınır: bir tuşun düz ve shift'li varyantı (US
# düzeni) aynı `KEY_`'e eşlenir; değiştiriciler ayrıca kendi `KEY_*` olaylarıyla
# gönderildiğinden host doğru karakteri üretir (`input_inject` tuşu çıplak
# enjekte eder, `mods`'u yalnız sunucunun tehlikeli-tuş filtresi kullanır).


def _build_keyval_map() -> dict:
    """keysym(int) → `KEY_*` enum tablosu kur (US temelli fiziksel-tuş eşlemesi).

    Yalnız `control_protocol.KEY_CODES` içindeki adlar hayatta kalır → protokol
    söz dağarcığı değişse bile geçersiz kod üretilmez (sunucu reddine düşmez).
    """
    m: dict = {}
    # Harfler: küçük (0x61-0x7A) ve büyük (0x41-0x5A) keysym → aynı KEY_A..KEY_Z.
    for i in range(26):
        letter = chr(ord("A") + i)
        m[0x41 + i] = f"KEY_{letter}"
        m[0x61 + i] = f"KEY_{letter}"
    # Rakamlar: 0x30-0x39 → KEY_0..KEY_9.
    for d in range(10):
        m[0x30 + d] = f"KEY_{d}"
    # Fonksiyon tuşları: XK_F1=0xFFBE ardışık → KEY_F1..KEY_F12.
    for n in range(12):
        m[0xFFBE + n] = f"KEY_F{n + 1}"
    # Özel / navigasyon / değiştirici tuşlar (XK_* keysym → KEY_*).
    m.update(
        {
            0xFF0D: "KEY_ENTER",
            0xFF8D: "KEY_ENTER",  # Return, KP_Enter
            0xFF1B: "KEY_ESC",
            0xFF08: "KEY_BACKSPACE",
            0xFF09: "KEY_TAB",
            0x0020: "KEY_SPACE",
            0xFF51: "KEY_LEFT",
            0xFF52: "KEY_UP",
            0xFF53: "KEY_RIGHT",
            0xFF54: "KEY_DOWN",
            0xFF50: "KEY_HOME",
            0xFF57: "KEY_END",
            0xFF55: "KEY_PAGEUP",
            0xFF56: "KEY_PAGEDOWN",
            0xFF63: "KEY_INSERT",
            0xFFFF: "KEY_DELETE",
            0xFFE5: "KEY_CAPSLOCK",
            0xFFE3: "KEY_LEFTCTRL",
            0xFFE4: "KEY_RIGHTCTRL",
            0xFFE1: "KEY_LEFTSHIFT",
            0xFFE2: "KEY_RIGHTSHIFT",
            0xFFE9: "KEY_LEFTALT",
            0xFFEA: "KEY_RIGHTALT",
            0xFFE7: "KEY_LEFTMETA",
            0xFFE8: "KEY_RIGHTMETA",  # Meta_L/R
            0xFFEB: "KEY_LEFTMETA",
            0xFFEC: "KEY_RIGHTMETA",  # Super_L/R
        }
    )
    # Noktalama: temel + shift'li varyant (US) → aynı fiziksel KEY_.
    punct = {
        "KEY_MINUS": (0x02D, 0x05F),  # - _
        "KEY_EQUAL": (0x03D, 0x02B),  # = +
        "KEY_LEFTBRACE": (0x05B, 0x07B),  # [ {
        "KEY_RIGHTBRACE": (0x05D, 0x07D),  # ] }
        "KEY_SEMICOLON": (0x03B, 0x03A),  # ; :
        "KEY_APOSTROPHE": (0x027, 0x022),  # ' "
        "KEY_GRAVE": (0x060, 0x07E),  # ` ~
        "KEY_BACKSLASH": (0x05C, 0x07C),  # \ |
        "KEY_COMMA": (0x02C, 0x03C),  # , <
        "KEY_DOT": (0x02E, 0x03E),  # . >
        "KEY_SLASH": (0x02F, 0x03F),  # / ?
    }
    for code, syms in punct.items():
        for s in syms:
            m[s] = code
    # Shift'li rakamlar (US): sembol keysym → fiziksel rakam tuşu.
    m.update(
        {
            0x021: "KEY_1",
            0x040: "KEY_2",
            0x023: "KEY_3",
            0x024: "KEY_4",
            0x025: "KEY_5",
            0x05E: "KEY_6",
            0x026: "KEY_7",
            0x02A: "KEY_8",
            0x028: "KEY_9",
            0x029: "KEY_0",
        }
    )
    # Savunma: yalnız protokolün tanıdığı adlar kalsın.
    return {k: v for k, v in m.items() if v in cp.KEY_CODES}


_KEYVAL_MAP = _build_keyval_map()

# GDK modifier bit maskeleri (Gdk.ModifierType — kararlı tamsayı değerleri).
# GTK enum yerine sabit tutulur → helper GTK'sız test edilebilir.
_GDK_SHIFT_MASK = 1 << 0  # 1
_GDK_CONTROL_MASK = 1 << 2  # 4
_GDK_ALT_MASK = 1 << 3  # 8   (Mod1 / GTK4 ALT_MASK)
_GDK_SUPER_MASK = 1 << 26  # 67108864
_GDK_META_MASK = 1 << 28  # 268435456


def keyval_to_key_code(keyval: int) -> Optional[str]:
    """GDK keyval (X11 keysym) → layout-bağımsız `KEY_*` enum; bilinmeyen → None.

    Saf: GDK keyval'leri X11 keysym'leriyle aynı olduğundan tablo derleme-zamanı
    sabittir (GTK gerektirmez). Dönen ad daima `control_protocol.KEY_CODES`
    içindedir; eşlenmemiş tuş `None` döner (çağıran yerel akışa bırakır).
    """
    return _KEYVAL_MAP.get(int(keyval))


def gdk_state_to_mods(state: int) -> Tuple[str, ...]:
    """GDK modifier durum bit maskesini nötr mod adları demetine çevir.

    Dönen demet `control_protocol.MODIFIERS` adlarını (`ctrl/shift/alt/meta`)
    sabit sırayla içerir. Saf: GTK enum yerine sabit bit değerleri kullanır →
    headless test edilebilir. Sunucunun tehlikeli-tuş filtresi bu `mods`'u
    kullanır; değiştiriciler ayrıca kendi `KEY_*` olaylarıyla da gönderilir.
    """
    s = int(state)
    mods = []
    if s & _GDK_CONTROL_MASK:
        mods.append("ctrl")
    if s & _GDK_SHIFT_MASK:
        mods.append("shift")
    if s & _GDK_ALT_MASK:
        mods.append("alt")
    if s & (_GDK_SUPER_MASK | _GDK_META_MASK):
        mods.append("meta")
    return tuple(mods)


# --- Kontrol kanalı istemcisi -------------------------------------------------


class ControlChannelClient:
    """`/control` WebSocket kanalını açar ve girdi olaylarını gönderir.

    Yaşam döngüsü: `connect()` (TLS + fingerprint pin + el sıkışma + grant oku)
    → `send_move/send_button/send_scroll/send_key` (maskeli olay, `sid` iliştirir)
    → `read_message()` (host→istemci revoke/ping oku) → `close()`.
    """

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        pin: str = "",
        pinned_fingerprint: Optional[str] = None,
        use_tls: Optional[bool] = None,
        require_tls: Optional[bool] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.device_id = None  # Ekstra device_id, ileride atanabilir
        self._pin = pin
        self.pinned_fingerprint = pinned_fingerprint
        # use_tls None iken TLS önce denenir, başarısızsa (require_tls kapalıysa)
        # düz TCP'ye düşülür. Görüntüleme istemcisi zaten şemayı çözmüşse onu
        # geçirir (tek deneme).
        self.use_tls = use_tls
        self.require_tls: bool = tls_util.HAS_TLS if require_tls is None else require_tls

        self._sock: Optional[socket.socket] = None
        self._rfile = None  # sock.makefile("rb") — çerçeve okuması için
        self._session_token: Optional[str] = None
        self._send_lock = threading.Lock()  # gönderimleri sırala (thread-safe)
        self.is_connected = False

    # --- Bağlantı ----------------------------------------------------------

    @property
    def session_token(self) -> Optional[str]:
        """Grant edilen oturum token'ı (`sid`). None → henüz izin yok."""
        return self._session_token

    def connect(self, timeout: float = 10.0) -> bool:
        """Kanalı aç: TCP/TLS → fingerprint pin → el sıkışma → grant.

        Dönüş: True yalnız sunucu `GrantEvent(allow=True)` gönderdiğinde
        (kontrol izni verildi). Aksi halde (host kapalı, backend yok, PIN
        yanlış, MITM) False ve soket kapatılır.
        """
        try:
            self._sock = self._open_socket(timeout)
        except OSError as exc:
            logger.warning("Kontrol kanalı bağlanamadı %s:%s — %s", self.host, self.port, exc)
            return False

        try:
            self._rfile = self._sock.makefile("rb")
            if not self._do_handshake():
                self.close()
                return False
            if not self._read_grant():
                self.close()
                return False
        except (OSError, FrameError, cp.ProtocolError) as exc:
            logger.warning("Kontrol el sıkışması başarısız: %s", exc)
            self.close()
            return False

        self.is_connected = True
        return True

    def _open_socket(self, timeout: float) -> socket.socket:
        """TCP bağlan, gerekiyorsa TLS-wrap et ve fingerprint'i doğrula."""
        raw = socket.create_connection((self.host, self.port), timeout)

        want_tls = self.use_tls if self.use_tls is not None else tls_util.HAS_TLS
        if not want_tls:
            if self.require_tls:
                raw.close()
                raise OSError("require_tls açık ama TLS'siz bağlantı istendi")
            return raw

        try:
            from pardus_paylasim.screen import trust_store

            # device_id varsa ondan, yoksa fallback olarak host (ip) ile alıyoruz
            store_key = self.device_id or self.host
            expected_fp = self.pinned_fingerprint or trust_store.get_trusted_fingerprint(store_key)
            if not expected_fp:
                raw.close()
                raise OSError(
                    "Güvenli bağlantı için fingerprint (parmak izi) zorunludur. (Sessiz TOFU engellendi)"
                )

            cert_path = tls_util.fetch_server_cert_to_tempfile(self.host, self.port, expected_fp)
            if cert_path is None:
                raw.close()
                raise OSError(
                    "Sunucu sertifikası doğrulanamadı veya MITM tespit edildi (Fail-closed)."
                )
            try:
                ctx = tls_util.build_client_context(cert_path)
                # check_hostname=False + CERT_REQUIRED (kimlik fingerprint pinning ile).
                tls_sock = ctx.wrap_socket(raw, server_hostname=None)
            finally:
                import os

                if cert_path and os.path.exists(cert_path):
                    try:
                        os.remove(cert_path)
                    except OSError:
                        pass
        except (ssl.SSLError, OSError) as exc:
            raw.close()
            if self.require_tls or self.use_tls is True:
                raise
            # TLS başarısız ve zorunlu değil → düz TCP'ye düş (şema çözülmemişti).
            logger.debug("TLS başarısız, düz TCP deneniyor: %s", exc)
            self.use_tls = False
            return socket.create_connection((self.host, self.port), timeout)

        if not self._verify_live_fingerprint(tls_sock):
            tls_sock.close()
            raise OSError("sertifika parmak izi doğrulanamadı (MITM koruması)")
        self.use_tls = True
        return tls_sock

    def _verify_live_fingerprint(self, tls_sock: ssl.SSLSocket) -> bool:
        """Canlı sertifikayı pinlenmiş parmak izine karşı doğrula.

        Görüntüleme istemcisiyle aynı TOFU modeli: pin yoksa şifreli-ama-
            kimliksiz akış kabul edilmez (kontrol daha hassas → katı). Ayrı bağlantı
        açmaz; ele geçirilmiş soketin kendisini doğrular.
        """
        try:
            der = tls_sock.getpeercert(binary_form=True)
        except (ssl.SSLError, OSError):
            return False
        live = tls_util.fingerprint_from_der(der)

        from pardus_paylasim.screen import trust_store

        store_key = self.device_id or self.host
        trusted_fp = trust_store.get_trusted_fingerprint(store_key)

        expected_fp = self.pinned_fingerprint or trusted_fp

        if not expected_fp:
            logger.error(
                "Sertifika parmak izi pinlenmedi ve trust store'da bulunamadı; "
                "MITM doğrulaması yapılamıyor (Sessiz TOFU engellendi)."
            )
            return False

        if not secrets.compare_digest(live, expected_fp):
            logger.error(
                "Sertifika parmak izi UYUŞMUYOR (MITM?). Beklenen %s, gelen %s.",
                expected_fp[:16],
                live[:16],
            )
            return False

        if live != trusted_fp:
            logger.info("Yeni fingerprint kontrol bağlantısı için kaydediliyor.")
            trust_store.add_trusted_fingerprint(self.host, live)

        self.pinned_fingerprint = live
        return True

    def _do_handshake(self) -> bool:
        """RFC6455 istemci el sıkışması: GET yaz → 101 + accept doğrula."""
        ws_key = generate_ws_key()
        self._sock.sendall(build_handshake_request(self.host, self.port, ws_key, self._pin))

        # Yanıt başlıklarını CRLFCRLF'e dek satır satır oku.
        header_bytes = b""
        while b"\r\n\r\n" not in header_bytes:
            line = self._rfile.readline()
            if not line:
                logger.warning("El sıkışma sırasında bağlantı kapandı.")
                return False
            header_bytes += line
            if len(header_bytes) > 8192:  # kötü/dev başlık savunması
                logger.warning("El sıkışma başlığı çok büyük.")
                return False

        status, headers = parse_handshake_response(header_bytes)
        if status != 101:
            logger.warning("Kontrol upgrade reddedildi: HTTP %s", status)
            return False
        if headers.get("upgrade", "").lower() != "websocket":
            logger.warning("Upgrade başlığı 'websocket' değil.")
            return False
        if not verify_accept(ws_key, headers.get("sec-websocket-accept", "")):
            logger.warning("Sec-WebSocket-Accept doğrulanamadı (MITM?).")
            return False
        return True

    def _read_grant(self) -> bool:
        """El sıkışma sonrası tek `GrantEvent` çerçevesini oku ve token sakla.

        `allow=True` → token saklanır, True döner. `allow=False`/başka mesaj →
        False (kontrol reddedildi).
        """
        opcode, payload = read_server_frame(self._rfile)
        if opcode == OP_CLOSE:
            logger.info("Sunucu kontrol kanalını kapattı (grant öncesi).")
            return False
        if opcode != OP_TEXT:
            logger.warning("Grant beklenirken beklenmeyen opcode: %s", opcode)
            return False

        msg = cp.decode(payload)
        if not isinstance(msg, cp.GrantEvent):
            logger.warning("Grant beklenirken farklı mesaj: %s", type(msg).__name__)
            return False
        if not msg.allow or not msg.session:
            logger.info("Kontrol reddedildi (host toggle kapalı/backend yok).")
            return False
        self._session_token = msg.session
        logger.info("Kontrol izni alındı (oturum token'ı saklandı).")
        return True

    # --- Olay gönderimi ----------------------------------------------------

    def _send_event(self, event: cp.ControlEvent) -> bool:
        """Olayı `sid` iliştirerek kodla ve maskeli çerçeve olarak gönder.

        `sid` alanı olan olaylara (move/btn/scroll/key) grant token'ı iliştirilir;
        token yoksa (izin alınmamış) gönderim reddedilir → sessiz kaybolmaz.
        """
        if not self.is_connected or self._sock is None:
            return False
        # sid taşıyabilen olaya token iliştir; taşımayan (ping/pong) olduğu gibi.
        if dataclasses.fields(event) and any(f.name == "sid" for f in dataclasses.fields(event)):
            if self._session_token is None:
                logger.warning("Oturum token'ı yok; kontrol olayı gönderilmedi.")
                return False
            event = dataclasses.replace(event, sid=self._session_token)
        try:
            frame = encode_client_text_frame(cp.encode(event))
            with self._send_lock:
                self._sock.sendall(frame)
            return True
        except (OSError, cp.ProtocolError) as exc:
            logger.debug("Kontrol olayı gönderilemedi: %s", exc)
            self.is_connected = False
            return False

    def send_move(self, x: float, y: float) -> bool:
        """Fare hareketi gönder (normalize 0..1 koordinat)."""
        return self._send_event(cp.MoveEvent(x=x, y=y))

    def send_button(self, button: str, down: bool, x: float, y: float) -> bool:
        """Fare düğmesi bas/bırak gönder."""
        return self._send_event(cp.ButtonEvent(button=button, down=down, x=x, y=y))

    def send_scroll(self, dx: float, dy: float) -> bool:
        """Kaydırma gönder (göreli adım)."""
        return self._send_event(cp.ScrollEvent(dx=dx, dy=dy))

    def send_key(self, code: str, down: bool, mods: Tuple[str, ...] = ()) -> bool:
        """Klavye tuşu bas/bırak gönder (layout-bağımsız `KEY_*` enum)."""
        return self._send_event(cp.KeyEvent(code=code, down=down, mods=mods))

    def send_ping(self) -> bool:
        """Canlılık yoklaması gönder (token taşımaz)."""
        return self._send_event(cp.PingEvent())

    # --- Host→istemci okuma ------------------------------------------------

    def read_message(self) -> Optional[cp.ControlEvent]:
        """Sunucudan tek bir kontrol mesajı oku (revoke/pong/ping).

        Kontrol/PING çerçeveleri işlenir (PING→otomatik PONG); metin çerçeveleri
        `control_protocol` ile çözülür. Kapanış/kopma → None (kanal bitti).
        Çağıran döngü None görünce durmalı. Bloklar (soket timeout'una tabi).
        """
        if self._rfile is None:
            return None
        try:
            opcode, payload = read_server_frame(self._rfile)
        except (OSError, FrameError) as exc:
            logger.debug("Kontrol mesajı okunamadı: %s", exc)
            self.is_connected = False
            return None

        if opcode == OP_CLOSE:
            self.is_connected = False
            return None
        if opcode == OP_PING:
            # Sunucu ping → maskeli pong ile yanıtla (payload'u aynala).
            try:
                with self._send_lock:
                    self._sock.sendall(build_client_frame(OP_PONG, payload))
            except OSError:
                self.is_connected = False
            return self.read_message()
        if opcode == OP_PONG:
            return cp.PongEvent()
        if opcode != OP_TEXT:
            # İkili/bilinmeyen çerçeve kontrolde beklenmez → atla.
            return self.read_message()

        try:
            return cp.decode(payload)
        except cp.ProtocolError as exc:
            logger.debug("Sunucu mesajı çözülemedi: %s", exc)
            return None

    # --- Kapatma -----------------------------------------------------------

    def close(self) -> None:
        """Kanalı kapat: maskeli close çerçevesi gönder, soketi kapat."""
        self.is_connected = False
        if self._sock is not None:
            try:
                with self._send_lock:
                    self._sock.sendall(
                        build_client_frame(OP_CLOSE, struct.pack("!H", CLOSE_NORMAL))
                    )
            except OSError:
                pass
            try:
                self._sock.close()
            except OSError:
                pass
        if self._rfile is not None:
            try:
                self._rfile.close()
            except OSError:
                pass
        self._sock = None
        self._rfile = None
        self._session_token = None
