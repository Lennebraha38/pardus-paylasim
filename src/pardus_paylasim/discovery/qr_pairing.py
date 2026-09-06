"""
QR ile cihaz eşleştirme.

Yerel cihazın bağlantı bilgilerini (ad, IP, dosya/pano portları, yetenekler)
tek bir `pardus://pair?...` URI'sinde kodlar. Bu URI QR koda dönüştürülüp
karşı cihazın kamerasıyla okunarak manuel IP/port girişi ortadan kalkar.

QR görseli için `qrcode` kütüphanesi kullanılır; kurulu değilse (asgari kurulum)
görsel üretilmez ama URI metni yine de gösterilebilir/paylaşılabilir — proje
genelindeki zarif-düşüş (graceful degradation) kalıbıyla tutarlı.
"""

import logging
import socket
from typing import Dict, List, Optional
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse

logger = logging.getLogger(__name__)

# URI şeması: pardus://pair?name=...&ip=...&file_port=...&clip_port=...&caps=...&fp=...
# fp: cihaz sertifikasının SHA-256 parmak izi (hex, 64). Opsiyonel; eski
# istemciler bilmediği alanı görmezden gelir (geriye uyum).
PAIR_SCHEME = "pardus"
PAIR_HOST = "pair"

try:
    import qrcode  # type: ignore

    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False


def get_local_ip() -> str:
    """Yerel (loopback olmayan) IP adresini döndürür.

    Harici bir adrese UDP 'connect' ederek işletim sisteminin seçtiği çıkış
    arayüzünün IP'sini okur (paket göndermez). Başarısızsa 127.0.0.1.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.settimeout(1)
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        try:
            s.close()
        except OSError:
            pass


def build_pairing_uri(
    name: str,
    ip: Optional[str] = None,
    file_port: int = 8900,
    clip_port: int = 8901,
    capabilities: Optional[List[str]] = None,
    fingerprint: str = "",
) -> str:
    """Yerel cihaz için eşleştirme URI'si üretir."""
    if ip is None:
        ip = get_local_ip()
    params = {
        "name": name,
        "ip": ip,
        "file_port": str(file_port),
        "clip_port": str(clip_port),
    }
    if capabilities:
        # Yetenekleri virgülle birleştir (URI-kodlaması urlencode'da yapılır).
        params["caps"] = ",".join(capabilities)
    if fingerprint:
        params["fp"] = fingerprint.lower()
    query = urlencode(params, quote_via=quote)
    return f"{PAIR_SCHEME}://{PAIR_HOST}?{query}"


def parse_pairing_uri(uri: str) -> Optional[Dict]:
    """Eşleştirme URI'sini ayrıştırır. Geçersizse None döner.

    Returns:
        {name, ip, file_port(int), clip_port(int), capabilities(list),
         fingerprint(str, yoksa "")} veya None.
    """
    try:
        parsed = urlparse(uri)
    except (ValueError, TypeError):
        return None

    if parsed.scheme != PAIR_SCHEME or parsed.netloc != PAIR_HOST:
        return None

    q = parse_qs(parsed.query)

    def _first(key: str, default: str = "") -> str:
        vals = q.get(key)
        return unquote(vals[0]) if vals else default

    ip = _first("ip")
    name = _first("name")
    if not ip or not name:
        return None  # Zorunlu alanlar eksik.

    def _port(key: str, default: int) -> int:
        try:
            return int(_first(key, str(default)))
        except ValueError:
            return default

    caps_raw = _first("caps")
    capabilities = [c for c in caps_raw.split(",") if c] if caps_raw else []

    fp = _first("fp").lower()
    if fp and (len(fp) != 64 or any(c not in "0123456789abcdef" for c in fp)):
        fp = ""  # bozuk parmak izi yok sayılır

    return {
        "name": name,
        "ip": ip,
        "file_port": _port("file_port", 8900),
        "clip_port": _port("clip_port", 8901),
        "capabilities": capabilities,
        "fingerprint": fp,
    }


def generate_qr_png(uri: str, path: str, box_size: int = 8, border: int = 2) -> bool:
    """URI'yi QR PNG dosyasına yazar. qrcode yoksa False döner.

    Returns:
        True: dosya yazıldı. False: qrcode kütüphanesi yok veya yazım hatası.
    """
    if not HAS_QRCODE:
        return False
    try:
        qr = qrcode.QRCode(box_size=box_size, border=border)
        qr.add_data(uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(path)
        return True
    except Exception as e:
        logger.error("QR görseli üretilemedi: %s", e)
        return False


def generate_qr_ascii(uri: str) -> Optional[str]:
    """URI'yi ASCII QR metnine çevirir (terminal/etiket). qrcode yoksa None."""
    if not HAS_QRCODE:
        return None
    try:
        import io

        qr = qrcode.QRCode(border=1)
        qr.add_data(uri)
        qr.make(fit=True)
        buf = io.StringIO()
        qr.print_ascii(out=buf)
        return buf.getvalue()
    except Exception as e:
        logger.error("ASCII QR üretilemedi: %s", e)
        return None
