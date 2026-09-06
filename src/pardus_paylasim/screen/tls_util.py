"""
TLS yardımcıları: ekran paylaşımı MJPEG akışını self-signed sertifika ile
şifreler. Düz HTTP dinleme (passive eavesdrop) açığını kapatır.

`cryptography` mevcut değilse HAS_TLS False olur ve çağıran taraf düz HTTP'ye
düşer (yalnız geliştirme/asgari kurulum için — üretimde cryptography zorunlu
bağımlılıktır). Fingerprint, PIN eşleşmesi sırasında öğrenilip akıştan önce
yeniden doğrulanarak oturum-ortası sertifika değişimine (MITM) karşı koyar.
"""

import datetime
import hashlib
import logging
import os
import socket
import ssl
import tempfile
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    HAS_TLS = True
except ImportError:
    HAS_TLS = False

# Sertifika geçerlilik penceresi. Uzun ömürlü değil; her sunucu başlangıcında
# yeni ephemeral sertifika üretilir.
_CERT_VALID_DAYS = 365
_TLS_PROBE_TIMEOUT = 5.0


def fingerprint_from_der(der_bytes: bytes) -> str:
    """DER kodlu sertifikanın SHA-256 parmak izini onaltılık döndürür."""
    return hashlib.sha256(der_bytes).hexdigest()


DEVICE_ID_DIR = os.path.expanduser("~/.local/share/pardus-paylasim")
DEVICE_CERT_PATH = os.path.join(DEVICE_ID_DIR, "device_cert.pem")
DEVICE_KEY_PATH = os.path.join(DEVICE_ID_DIR, "device_key.pem")


def get_or_create_device_cert() -> Tuple[str, str, str]:
    """Kalıcı cihaz kimliği: ilk çalışta üretilir, sonra yeniden kullanılır.

    Returns:
        (cert_path, key_path, fingerprint_hex). Dosyalar 0600 izinlidir.

    Ephemeral `generate_self_signed_cert` her çağrıda değişir; parmak izinin
    cihaz kimliği olması için bu kalıcı kopya kullanılır.
    """
    if not HAS_TLS:
        raise RuntimeError("cryptography kütüphanesi TLS için gerekli.")
    from cryptography import x509 as _x509
    from cryptography.hazmat.primitives import serialization as _serial

    try:
        if os.path.exists(DEVICE_CERT_PATH) and os.path.exists(DEVICE_KEY_PATH):
            with open(DEVICE_CERT_PATH, "rb") as f:
                cert_pem = f.read()
            cert = _x509.load_pem_x509_certificate(cert_pem)
            fp = fingerprint_from_der(
                cert.public_bytes(_serial.Encoding.DER)
            )
            os.chmod(DEVICE_CERT_PATH, 0o600)
            os.chmod(DEVICE_KEY_PATH, 0o600)
            return DEVICE_CERT_PATH, DEVICE_KEY_PATH, fp
    except Exception as e:
        logger.debug("Kayıtlı cihaz sertifikası okunamadı, yenisi üretilecek: %s", e)

    cert_path, key_path, fp = generate_self_signed_cert()
    try:
        os.makedirs(DEVICE_ID_DIR, exist_ok=True)
        import shutil

        shutil.copyfile(cert_path, DEVICE_CERT_PATH)
        shutil.copyfile(key_path, DEVICE_KEY_PATH)
        os.chmod(DEVICE_CERT_PATH, 0o600)
        os.chmod(DEVICE_KEY_PATH, 0o600)
    finally:
        for p in (cert_path, key_path):
            try:
                os.unlink(p)
            except OSError:
                pass
    return DEVICE_CERT_PATH, DEVICE_KEY_PATH, fp


def generate_self_signed_cert() -> Tuple[str, str, str]:
    """Ephemeral self-signed sertifika + anahtar üretir.

    Returns:
        (cert_path, key_path, fingerprint_hex) — cert/key 0600 izinli geçici
        dosyalar; çağıran SSLContext'e yükledikten sonra silmelidir.

    Raises:
        RuntimeError: cryptography yoksa.
    """
    if not HAS_TLS:
        raise RuntimeError("cryptography kütüphanesi TLS için gerekli.")

    key = ec.generate_private_key(ec.SECP256R1())
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, "pardus-paylasim"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Pardus"),
        ]
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=_CERT_VALID_DAYS))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("pardus-paylasim")]),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )

    cert_der = cert.public_bytes(serialization.Encoding.DER)
    fingerprint = fingerprint_from_der(cert_der)

    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    cert_path = _write_secure_temp(cert_pem, suffix=".crt")
    key_path = _write_secure_temp(key_pem, suffix=".key")
    return cert_path, key_path, fingerprint


def _write_secure_temp(data: bytes, suffix: str) -> str:
    """Veriyi yalnız geçerli kullanıcıya erişilebilir geçici dosyaya yazar.

    Özel anahtar diske yazılır; başka kullanıcılar okuyamamalı. POSIX'te
    `chmod 0600`. Windows'ta `os.chmod` izin bitlerini yok sayar → bunun
    yerine `icacls` ile miras alınan ACE'ler kaldırılıp dosyaya yalnız
    geçerli kullanıcıya tam yetki verilir. `%TEMP%` zaten kullanıcıya özel
    olsa da bu derinlemesine savunma sağlar (paylaşılan/atipik TEMP veya
    gevşetilmiş dizin ACL'leri için). Yolu döndürür; çağıran silmelidir.
    """
    fd, path = tempfile.mkstemp(prefix="pardus_tls_", suffix=suffix)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
    _lock_temp_permissions(path)
    return path


def _lock_temp_permissions(path: str) -> bool:
    """Geçici dosyayı yalnız geçerli kullanıcıya kilitler (best-effort).

    Returns:
        İzinler daraltıldıysa True; platform/araç sınırı nedeniyle best-effort
        başarısızsa False (dosya yine kullanılabilir kalır, çağıran patlamaz).
    """
    if os.name == "nt":
        return _restrict_windows_acl(path)
    try:
        os.chmod(path, 0o600)
        return True
    except OSError:
        return False


def _restrict_windows_acl(path: str) -> bool:
    """Windows: `icacls` ile miras ACE'leri kaldırıp yalnız geçerli kullanıcıya
    tam yetki verir. `icacls` yok / hata verirse False döner (yutulur)."""
    import getpass
    import subprocess

    try:
        user = getpass.getuser()
    except Exception as e:  # kullanıcı adı çözülemedi
        return False
    if not user:
        return False
    try:
        result = subprocess.run(
            [
                "icacls",
                path,
                "/inheritance:r",  # miras alınan tüm ACE'leri kaldır
                "/grant:r",  # yerini yalnız geçerli kullanıcıya ver
                f"{user}:F",
            ],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if result.returncode != 0:
        logger.debug(
            "icacls özel anahtar ACL kilidi başarısız (rc=%s): %s",
            result.returncode,
            result.stderr.decode(errors="replace").strip(),
        )
        return False
    return True


def build_server_context(cert_path: str, key_path: str) -> "ssl.SSLContext":
    """Sunucu tarafı SSLContext oluşturur (self-signed cert yüklü)."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=cert_path, keyfile=key_path)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


def build_client_context(server_cert_path: Optional[str] = None) -> "ssl.SSLContext":
    """İstemci tarafı SSLContext: CERT_REQUIRED ile güvenli doğrulamayı zorunlu kılar."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_REQUIRED
    if server_cert_path:
        context.load_verify_locations(cafile=server_cert_path)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


def get_peer_fingerprint(
    host: str, port: int, timeout: float = _TLS_PROBE_TIMEOUT
) -> Optional[str]:
    """Uzak TLS sunucusunun sunduğu sertifikanın SHA-256 parmak izini alır.

    Fingerprint pinning için canlı el sıkışmadan sertifikayı çeker. Bağlantı
    kurulamazsa None döner.
    """
    # Sadece fingerprint okumak için özel, verify yapmayan bağlam (geçici olarak)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=host) as tls_sock:
                der = tls_sock.getpeercert(binary_form=True)
        if not der:
            return None
        return fingerprint_from_der(der)
    except (OSError, ssl.SSLError):
        return None


def fetch_server_cert_to_tempfile(host: str, port: int, expected_fingerprint: str) -> Optional[str]:
    """Sunucudan sertifikayı indirip fingerprint kontrolü yapar.

    Yalnızca sertifikanın DER SHA-256 parmak izi `expected_fingerprint` ile
    eşleşirse geçici bir PEM dosyasına yazar ve yolunu döner. Eşleşmezse
    veya bağlanılamazsa MITM şüphesiyle None döner (Fail-closed).
    Çağıran taraf işi bitince dosyayı silmelidir."""
    try:
        import os
        import ssl
        import tempfile

        cert_pem = ssl.get_server_certificate((host, port))
        der = ssl.PEM_cert_to_DER_cert(cert_pem)
        live_fp = fingerprint_from_der(der)

        if live_fp != expected_fingerprint:
            logger.error(
                "MITM Koruması: Sertifika parmak izi uyuşmuyor! Beklenen: %s, Gelen: %s",
                expected_fingerprint,
                live_fp,
            )
            return None

        fd, path = tempfile.mkstemp(prefix="pardus_peer_", suffix=".pem")
        with os.fdopen(fd, "w") as f:
            f.write(cert_pem)
        return path
    except Exception as exc:
        logger.debug("Sunucu sertifikası çekilemedi: %s", exc)
        return None
