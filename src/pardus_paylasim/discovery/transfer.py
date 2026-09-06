import hashlib
import hmac
import json
import logging
import os
import socket
import ssl
import struct
import threading
import tempfile
import time
from typing import Callable, Optional

from . import net_util

logger = logging.getLogger(__name__)

try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

# Wire format: salt(16) + nonce(12) + ciphertext.
SALT_LEN = 16
NONCE_LEN = 12
PBKDF2_ITERATIONS = 200_000
MAX_PAYLOAD_SIZE = 1024 * 1024 * 1024  # 1 GiB hard limit against memory DoS.
SECRET_MAGIC = b"PPS2"
SECRET_CHUNK_SIZE = 64 * 1024
SECRET_FRAME_OVERHEAD = 4 + 16
# Mod baytları: 0x00 normal, 0x01 secret, 0x03 resume, 0x04 normal+hash.
MODE_NORMAL = b"\x00"
MODE_SECRET = b"\x01"
MODE_RESUME = b"\x03"
MODE_HASHED = b"\x04"
HASH_LEN = 32  # SHA-256 digest
RESUME_IO_CHUNK = 65536
SIDECAR_SUFFIX = ".part.json"
PART_SUFFIX = ".part"


def _peer_ip(conn: socket.socket) -> str:
    """Eş IP'sini güvenli al (her socket türünde patlamaz).

    TCP'de (ip, port) tuple döner; socketpair/UNIX'te boş string veya
    farklı biçim gelebilir — hepsinde güvenli varsayılan "".
    """
    try:
        peer = conn.getpeername()
    except OSError:
        return ""
    if isinstance(peer, tuple) and peer and isinstance(peer[0], str):
        return peer[0]
    return ""


def safe_target_path(download_dir: str, wire_name: str) -> str:
    """Gönderenden gelen (güvenilmez) adı download_dir içinde güvenli hedef
    yola çevirir.

    Alt klasörlere izin verir (klasör transferi: 'klasor/alt/dosya.txt'), ancak
    '../', mutlak yollar ve sürücü öneklerini eleyip nihai yolun download_dir
    içinde kaldığını realpath ile doğrular. Aşım tespit edilirse taban ada düşer.
    """
    # Ayraçları normalize et, baştaki '/' ve sürücü kökünü at.
    normalized = wire_name.replace("\\", "/").lstrip("/")

    # Her bileşeni süz: '', '.', '..' at → dizin-aşımı imkânsız.
    parts = [p for p in normalized.split("/") if p not in ("", ".", "..")]
    if not parts:
        parts = ["alinan_dosya"]

    candidate = os.path.join(download_dir, *parts)

    # Kesin güvence: realpath download_dir kökünde mi? Değilse taban ada düş.
    root = os.path.realpath(download_dir)
    resolved = os.path.realpath(candidate)
    if resolved != root and not resolved.startswith(root + os.sep):
        return os.path.join(download_dir, parts[-1])
    return candidate


def derive_key(pin: str, salt: bytes) -> bytes:
    """Derive a 256-bit key from the PIN using salted PBKDF2-HMAC-SHA256."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return kdf.derive(pin.encode("utf-8"))


def encrypt_data(pin: str, data: bytes) -> bytes:
    if not HAS_CRYPTO:
        raise Exception("cryptography kütüphanesi kurulu değil!")
    salt = os.urandom(SALT_LEN)
    key = derive_key(pin, salt)
    aesgcm = AESGCM(key)
    nonce = os.urandom(NONCE_LEN)
    ct = aesgcm.encrypt(nonce, data, None)
    return salt + nonce + ct


def decrypt_data(pin: str, encrypted_data: bytes) -> bytes:
    if not HAS_CRYPTO:
        raise Exception("cryptography kütüphanesi kurulu değil!")
    salt = encrypted_data[:SALT_LEN]
    nonce = encrypted_data[SALT_LEN : SALT_LEN + NONCE_LEN]
    ct = encrypted_data[SALT_LEN + NONCE_LEN :]
    key = derive_key(pin, salt)
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, None)


def _secret_payload_size(file_size: int) -> int:
    """Return the framed encrypted payload size for a plaintext file."""
    chunks = max(1, (file_size + SECRET_CHUNK_SIZE - 1) // SECRET_CHUNK_SIZE)
    return len(SECRET_MAGIC) + SALT_LEN + 8 + chunks * SECRET_FRAME_OVERHEAD + file_size


def _secret_nonce(prefix: bytes, counter: int) -> bytes:
    return prefix + struct.pack("!I", counter)


class FileTransferError(Exception):
    pass


class FileSender:
    def __init__(self, target_ip, target_port=8900, ssl_context: Optional[ssl.SSLContext] = None):
        self.target_ip = target_ip
        self.target_port = target_port
        self.ssl_context = ssl_context

    def send_file(self, file_path, secret_pin=None, progress_callback=None, rel_name=None,
                  stats_callback: Optional[Callable[[int, int, float], None]] = None,
                  resume=False, verify_hash=False):
        """Tek dosya gönderir.

        rel_name verilirse tel-üzeri ad olarak kullanılır (klasör transferinde
        göreli yol; örn. 'belgeler/alt/a.txt'). None ise taban ad kullanılır —
        mevcut çağıranlar için davranış aynen korunur.

        stats_callback(sent_bytes, total_bytes, elapsed_s): hız/ETA için ham
        veri; progress_callback oranını bozmaz, ek olarak çağrılır.

        resume=True (yalnız normal mod): alıcıdaki yarım `.part` dosyasından
        devam eder; alıcıda kayıt yoksa sıfırdan gönderir.

        verify_hash=True (yalnız normal mod): gövde sonuna 32 baytlık SHA-256
        eklenir; alıcı doğrular, tutmazsa reddeder (0x04 modu).
        """
        if not os.path.exists(file_path):
            raise FileTransferError("Dosya bulunamadı.")
        if resume and secret_pin:
            raise FileTransferError("Resume yalnız normal modda desteklenir.")
        if verify_hash and secret_pin:
            raise FileTransferError("Secret mod zaten AEAD ile doğrulanır.")

        file_size = os.path.getsize(file_path)
        file_name = rel_name if rel_name else os.path.basename(file_path)

        if resume:
            self._send_resume(file_path, file_name, file_size,
                              progress_callback, stats_callback)
            return

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(10)
            if self.ssl_context:
                conn = self.ssl_context.wrap_socket(s, server_hostname=self.target_ip)
            else:
                conn = s
            conn.connect((self.target_ip, self.target_port))
            t0 = time.monotonic()

            def report(sent):
                if progress_callback:
                    progress_callback(sent / file_size if file_size else 1.0)
                if stats_callback:
                    stats_callback(sent, file_size, time.monotonic() - t0)

            # 1. Byte: Mode (0: Normal, 1: Secret, 4: Normal+Hash)
            mode_byte = MODE_SECRET if secret_pin else (MODE_HASHED if verify_hash else MODE_NORMAL)
            conn.sendall(mode_byte)

            # Send file name length + name
            name_bytes = file_name.encode("utf-8")
            conn.sendall(struct.pack("!I", len(name_bytes)))
            conn.sendall(name_bytes)

            if secret_pin:
                if not HAS_CRYPTO:
                    raise FileTransferError("cryptography kütüphanesi kurulu değil!")
                payload_size = _secret_payload_size(file_size)
                if payload_size > MAX_PAYLOAD_SIZE:
                    raise FileTransferError("Dosya boyutu aktarım sınırını aşıyor.")
                conn.sendall(struct.pack("!Q", payload_size))
                salt = os.urandom(SALT_LEN)
                nonce_prefix = os.urandom(8)
                key = derive_key(secret_pin, salt)
                aesgcm = AESGCM(key)
                conn.sendall(SECRET_MAGIC + salt + nonce_prefix)
                with open(file_path, "rb") as f:
                    sent = 0
                    counter = 0
                    while True:
                        chunk = f.read(SECRET_CHUNK_SIZE)
                        if not chunk:
                            if counter == 0:
                                encrypted = aesgcm.encrypt(
                                    _secret_nonce(nonce_prefix, counter), b"", None
                                )
                                conn.sendall(struct.pack("!I", len(encrypted)))
                            break
                        encrypted = aesgcm.encrypt(
                            _secret_nonce(nonce_prefix, counter), chunk, None
                        )
                        conn.sendall(struct.pack("!I", len(encrypted)))
                        conn.sendall(encrypted)
                        sent += len(chunk)
                        counter += 1
                        report(sent)
                report(file_size)
            else:
                # Normal mode: chunked (+ opsiyonel sondan SHA-256)
                if file_size > MAX_PAYLOAD_SIZE:
                    raise FileTransferError("Dosya boyutu aktarım sınırını aşıyor.")
                conn.sendall(struct.pack("!Q", file_size))
                digest = hashlib.sha256() if verify_hash else None
                sent = 0
                with open(file_path, "rb") as f:
                    while True:
                        chunk = f.read(65536)
                        if not chunk:
                            break
                        conn.sendall(chunk)
                        if digest is not None:
                            digest.update(chunk)
                        sent += len(chunk)
                        report(sent)
                if digest is not None:
                    conn.sendall(digest.digest())

            # Wait for ACK
            ack = conn.recv(1)
            if ack != b"\x01":
                raise FileTransferError("Alıcı cihaz dosyayı kabul etmedi veya hata oluştu.")

    def _send_resume(self, file_path, file_name, file_size,
                     progress_callback=None, stats_callback=None):
        """Kaldığı yerden devam: alıcıdaki offset'i öğrenip kalanı gönderir."""
        if file_size > MAX_PAYLOAD_SIZE:
            raise FileTransferError("Dosya boyutu aktarım sınırını aşıyor.")
        mtime_ns = os.stat(file_path).st_mtime_ns
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(10)
            if self.ssl_context:
                conn = self.ssl_context.wrap_socket(s, server_hostname=self.target_ip)
            else:
                conn = s
            conn.connect((self.target_ip, self.target_port))
            t0 = time.monotonic()

            def report(sent):
                if progress_callback:
                    progress_callback(sent / file_size if file_size else 1.0)
                if stats_callback:
                    stats_callback(sent, file_size, time.monotonic() - t0)

            conn.sendall(MODE_RESUME)
            name_bytes = file_name.encode("utf-8")
            conn.sendall(struct.pack("!I", len(name_bytes)))
            conn.sendall(name_bytes)
            conn.sendall(struct.pack("!Q", file_size))
            conn.sendall(struct.pack("!Q", mtime_ns))

            off_data = net_util.recv_exact(conn, 8)
            if off_data is None:
                raise FileTransferError("Resume offset alınamadı.")
            offset = struct.unpack("!Q", off_data)[0]
            if offset > file_size:
                raise FileTransferError("Alıcı offset'i dosya boyutunu aşıyor.")

            sent = offset
            report(sent)
            with open(file_path, "rb") as f:
                f.seek(offset)
                while True:
                    chunk = f.read(RESUME_IO_CHUNK)
                    if not chunk:
                        break
                    conn.sendall(chunk)
                    sent += len(chunk)
                    report(sent)

            ack = conn.recv(1)
            if ack != b"\x01":
                raise FileTransferError("Alıcı cihaz dosyayı kabul etmedi veya hata oluştu.")

    def send_files(self, file_paths, secret_pin=None, progress_callback=None,
                   stats_callback=None, resume=False, verify_hash=False):
        """Birden çok dosyayı sırayla gönderir (her biri ayrı bağlantı).

        progress_callback(oran, gonderilen_index, toplam) — genel ilerleme.
        stats_callback/resume/verify_hash her dosyaya aynen aktarılır.
        Bir dosya reddedilir/başarısız olursa istisna yükseltilir; kalanlar
        gönderilmez (çağıran istediğini yeniden deneyebilir).
        """
        total = len(file_paths)
        for idx, path in enumerate(file_paths):
            self.send_file(path, secret_pin, stats_callback=stats_callback,
                           resume=resume, verify_hash=verify_hash)
            if progress_callback:
                progress_callback((idx + 1) / total, idx + 1, total)

    def send_folder(self, folder_path, secret_pin=None, progress_callback=None,
                    stats_callback=None, resume=False, verify_hash=False):
        """Bir klasörü, iç yapısını koruyarak (göreli yollarla) gönderir.

        Klasörün üst dizini taban alınır; her dosya 'klasoradi/alt/dosya'
        biçiminde göreli adla gönderilir. Alıcı bu yapıyı yeniden kurar.
        """
        if not os.path.isdir(folder_path):
            raise FileTransferError("Klasör bulunamadı.")

        folder_path = os.path.abspath(folder_path)
        # Göreli yolların kökü: klasörün bir üstü → klasör adı korunur.
        base_dir = os.path.dirname(folder_path)

        files = []
        for root, _dirs, names in os.walk(folder_path):
            for name in names:
                files.append(os.path.join(root, name))

        if not files:
            raise FileTransferError("Klasör boş.")

        total = len(files)
        for idx, path in enumerate(files):
            # Tel-üzeri göreli ad; ayraçlar '/' olarak normalize edilir.
            rel = os.path.relpath(path, base_dir).replace(os.sep, "/")
            self.send_file(path, secret_pin, rel_name=rel,
                           stats_callback=stats_callback,
                           resume=resume, verify_hash=verify_hash)
            if progress_callback:
                progress_callback((idx + 1) / total, idx + 1, total)


class FileReceiverServer:
    def __init__(self, download_dir, port=8900, ssl_context: Optional[ssl.SSLContext] = None):
        self.download_dir = download_dir
        self.port = port
        self.ssl_context = ssl_context
        self.server_socket = None
        self._running = False
        self.on_file_received = None  # Callback(file_path)
        self.get_secret_pin_callback = None  # Callback(filename) -> pin
        # Kabul onayı: Callback(dosya_adi, boyut, gonderen_ip) -> bool.
        # None ise otomatik kabul edilir (geriye-dönük uyum: mevcut testler).
        self.on_file_request = None
        # Transfer geçmişi deposu (TransferHistory); None ise kayıt tutulmaz.
        self.history = None

    def start(self):
        # Faz 1: receiver yalnız secure session ile başlasın
        if not self.ssl_context:
            import logging

            logging.getLogger(__name__).warning(
                "TLS (ssl_context) eksik. Dosya alıcısı başlatılamadı (Fail-closed)."
            )
            return

        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir, exist_ok=True)

        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(("0.0.0.0", self.port))
        self.server_socket.listen(5)
        if self.ssl_context:
            self.server_socket = self.ssl_context.wrap_socket(self.server_socket, server_side=True)
        self._running = True
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def stop(self):
        self._running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except OSError:
                pass

    def _accept_loop(self):
        while self._running:
            try:
                conn, addr = self.server_socket.accept()
                threading.Thread(target=self._handle_client, args=(conn,), daemon=True).start()
            except OSError:
                # Socket closed during stop() -> exit loop; otherwise keep serving.
                if not self._running:
                    break

    def _handle_client(self, conn):
        temp_path = None
        try:
            conn.settimeout(30)
            mode_byte = net_util.recv_exact(conn, 1)
            if not mode_byte:
                return
            if mode_byte == MODE_RESUME:
                self._handle_resume(conn)
                return
            is_secret = mode_byte == MODE_SECRET
            hashed_mode = mode_byte == MODE_HASHED

            # Read filename length
            name_len_data = net_util.recv_exact(conn, 4)
            if name_len_data is None:
                return
            name_len = struct.unpack("!I", name_len_data)[0]

            # Read filename
            name_bytes = net_util.recv_exact(conn, name_len)
            if name_bytes is None:
                return
            file_name = name_bytes.decode("utf-8")

            # Read payload length
            size_data = net_util.recv_exact(conn, 8)
            if size_data is None:
                return
            payload_size = struct.unpack("!Q", size_data)[0]
            if payload_size > MAX_PAYLOAD_SIZE:
                logger.warning("Payload boyutu sınırı aşıldı: %s bayt", payload_size)
                conn.sendall(b"\x00")
                return

            # Gönderen IP'si (geçmiş kaydı + kabul onayı için).
            peer_ip = _peer_ip(conn)

            # Kabul onayı: kullanıcı reddederse gövdeyi hiç tamponlamadan
            # bağlantıyı kapat (saldırgan verisi diske/RAM'e alınmaz).
            # Faz 1: açık policy yoksa (None) veya False ise reddet (Fail-closed)
            if self.on_file_request is None or not self.on_file_request(
                file_name, payload_size, peer_ip
            ):
                conn.sendall(b"\x00")  # Reddedildi
                self._log_history(
                    file_name,
                    payload_size,
                    peer_ip,
                    "rejected",
                    is_secret,
                )
                return

            if is_secret:
                if not self.get_secret_pin_callback:
                    conn.sendall(b"\x00")
                    return
                # Get PIN from UI
                pin = self.get_secret_pin_callback(file_name)
                if not pin:
                    conn.sendall(b"\x00")
                    return
                try:
                    temp_path = self._receive_secret_payload(conn, payload_size, pin)
                    file_data = temp_path
                except Exception as e:
                    logger.error("Şifre çözme hatası: %s", e)
                    conn.sendall(b"\x00")
                    return
            else:
                # Streaming: dosyayı doğrudan diskte yaz, bellek kullanımı sabit.
                temp_path = self._receive_normal_payload(
                    conn, payload_size, file_name
                )
                if hashed_mode:
                    digest_data = net_util.recv_exact(conn, HASH_LEN)
                    if digest_data is None:
                        raise FileTransferError("Hash özeti alınamadı.")
                    self._verify_file_hash(temp_path, digest_data)
                file_data = temp_path

            # Güvenli hedef yol: alt klasörlere izin verir (klasör transferi),
            # ama '../' / mutlak yol ile download_dir dışına çıkışı engeller.
            save_path = safe_target_path(self.download_dir, file_name)

            # Alt klasör yapısını oluştur (klasör transferi için).
            parent = os.path.dirname(save_path)
            if parent and not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)

            # Avoid overwrite
            counter = 1
            base, ext = os.path.splitext(save_path)
            while os.path.exists(save_path):
                save_path = f"{base}_{counter}{ext}"
                counter += 1

            if temp_path is not None:
                os.replace(temp_path, save_path)
            else:
                raise FileTransferError("Dosya alınamadı.")

            conn.sendall(b"\x01")  # ACK success

            # Başarılı alım: geçmişe kaydet (kaydedilen taban ad ile).
            self._log_history(
                os.path.basename(save_path),
                payload_size,
                peer_ip,
                "ok",
                is_secret,
            )

            if self.on_file_received:
                self.on_file_received(save_path)

        except Exception as e:
            logger.error("Dosya alma hatası: %s", e)
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    logger.warning("Geçici aktarım dosyası silinemedi: %s", temp_path)
            try:
                conn.sendall(b"\x00")
            except OSError:
                pass
        finally:
            conn.close()

    def _verify_file_hash(self, path: str, expected: bytes):
        """Dosyanın SHA-256 özetini akışlı okuyarak doğrular."""
        digest = hashlib.sha256()
        with open(path, "rb") as f:
            for piece in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(piece)
        if not hmac.compare_digest(digest.digest(), expected):
            raise FileTransferError("Bütünlük doğrulaması başarısız (hash uyuşmazlığı).")

    def _resume_paths(self, file_name: str):
        """Yarım dosya + sidecar yolları (traversal-güvenli taban ad üzerinden)."""
        base = safe_target_path(self.download_dir, file_name)
        part_path = base + PART_SUFFIX
        return part_path, part_path + ".json"

    def _read_sidecar(self, sidecar: str, total_size: int, mtime_ns: int):
        """Geçerli sidecar varsa kaldığı baytı döner, yoksa 0."""
        try:
            with open(sidecar, "r", encoding="utf-8") as f:
                meta = json.load(f)
            if (meta.get("size") == total_size
                    and meta.get("mtime_ns") == mtime_ns
                    and isinstance(meta.get("received"), int)
                    and 0 <= meta["received"] <= total_size):
                return meta["received"]
        except (OSError, ValueError):
            pass
        return 0

    def _write_sidecar(self, sidecar: str, total_size: int, mtime_ns: int, received: int):
        try:
            parent = os.path.dirname(sidecar)
            if parent and not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)
            with open(sidecar, "w", encoding="utf-8") as f:
                json.dump({"size": total_size, "mtime_ns": mtime_ns,
                           "received": received}, f)
        except OSError as e:
            logger.warning("Sidecar yazılamadı: %s", e)

    def _handle_resume(self, conn: socket.socket):
        """0x03 modu: offset bildir → kalanı al → tamamlanınca taşı."""
        part_path = None
        sidecar = None
        try:
            conn.settimeout(30)
            name_len_data = net_util.recv_exact(conn, 4)
            if name_len_data is None:
                return
            name_len = struct.unpack("!I", name_len_data)[0]
            name_bytes = net_util.recv_exact(conn, name_len)
            if name_bytes is None:
                return
            file_name = name_bytes.decode("utf-8")
            size_data = net_util.recv_exact(conn, 8)
            mtime_data = net_util.recv_exact(conn, 8)
            if size_data is None or mtime_data is None:
                return
            total_size = struct.unpack("!Q", size_data)[0]
            mtime_ns = struct.unpack("!Q", mtime_data)[0]
            if total_size > MAX_PAYLOAD_SIZE:
                logger.warning("Resume boyutu sınırı aşıldı: %s", total_size)
                conn.sendall(b"\x00")
                return

            peer_ip = _peer_ip(conn)

            if self.on_file_request is None or not self.on_file_request(
                file_name, total_size, peer_ip
            ):
                conn.sendall(b"\x00")
                self._log_history(file_name, total_size, peer_ip, "rejected", False)
                return

            part_path, sidecar = self._resume_paths(file_name)
            parent = os.path.dirname(part_path)
            if parent and not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)

            claimed = 0
            if os.path.exists(sidecar):
                claimed = self._read_sidecar(sidecar, total_size, mtime_ns)
            # Dosyayı açıp GERÇEK boyutu öğren, offset'i ondan türet;
            # sidecar şişmiş/eksikse disk esas alınır.
            f = open(part_path, "ab")
            try:
                f.seek(0, os.SEEK_END)
                actual = f.tell()
                offset = min(claimed, actual, total_size)
                if actual > offset:
                    # Sidecar geride kalmış (yazım sonrası çökme): dosya
                    # zaten daha ileride, kaldığı yerden devam.
                    offset = min(actual, total_size)
                if offset >= total_size and total_size > 0:
                    f.close()
                    conn.sendall(struct.pack("!Q", total_size))
                    conn.sendall(b"\x01")
                    return
                conn.sendall(struct.pack("!Q", offset))

                received = offset
                self._write_sidecar(sidecar, total_size, mtime_ns, received)
                next_mark = ((offset // (1024 * 1024)) + 1) * (1024 * 1024)
                while received < total_size:
                    to_read = min(RESUME_IO_CHUNK, total_size - received)
                    chunk = net_util.recv_exact(conn, to_read)
                    if chunk is None:
                        raise FileTransferError("Resume aktarım erken sona erdi.")
                    f.write(chunk)
                    received += len(chunk)
                    if received >= next_mark:
                        self._write_sidecar(sidecar, total_size, mtime_ns, received)
                        next_mark += 1024 * 1024
            finally:
                try:
                    f.close()
                except OSError:
                    pass

            if received != total_size:
                raise FileTransferError("Resume boyutu tutarsız.")
            self._write_sidecar(sidecar, total_size, mtime_ns, received)

            save_path = safe_target_path(self.download_dir, file_name)
            final_parent = os.path.dirname(save_path)
            if final_parent and not os.path.exists(final_parent):
                os.makedirs(final_parent, exist_ok=True)
            counter = 1
            base, ext = os.path.splitext(save_path)
            while os.path.exists(save_path):
                save_path = f"{base}_{counter}{ext}"
                counter += 1
            os.replace(part_path, save_path)
            try:
                os.unlink(sidecar)
            except OSError:
                pass

            conn.sendall(b"\x01")
            self._log_history(os.path.basename(save_path), total_size,
                              peer_ip, "ok", False)
            if self.on_file_received:
                self.on_file_received(save_path)
        except Exception as e:
            logger.error("Resume alma hatası: %s", e)
            try:
                conn.sendall(b"\x00")
            except OSError:
                pass
        finally:
            conn.close()

    def _receive_normal_payload(self, conn: socket.socket, payload_size: int, file_name: str) -> str:
        """Receive an unencrypted payload into a temp file in streaming chunks.

        Reads `payload_size` bytes from `conn` and writes them directly to a
        temporary file inside `download_dir` so memory usage stays bounded
        regardless of the file size.
        """
        temp = tempfile.NamedTemporaryFile(
            mode="wb", dir=self.download_dir, prefix=".pardus-transfer-", delete=False
        )
        try:
            received = 0
            chunk_size = 65536
            while received < payload_size:
                to_read = min(chunk_size, payload_size - received)
                chunk = net_util.recv_exact(conn, to_read)
                if chunk is None:
                    raise FileTransferError("Normal aktarım erken sona erdi.")
                temp.write(chunk)
                received += len(chunk)
            return temp.name
        except Exception as e:
            try:
                os.unlink(temp.name)
            except OSError:
                pass
            raise
        finally:
            temp.close()

    def _receive_secret_payload(self, conn, payload_size: int, pin: str) -> str:
        """Decrypt framed secret data into a temporary file without buffering it."""
        if payload_size < len(SECRET_MAGIC) + SALT_LEN + 8:
            raise FileTransferError("Geçersiz şifreli aktarım başlığı.")
        header = net_util.recv_exact(conn, len(SECRET_MAGIC) + SALT_LEN + 8)
        if header is None or header[:4] != SECRET_MAGIC:
            raise FileTransferError("Desteklenmeyen şifreli aktarım biçimi.")
        salt = header[4 : 4 + SALT_LEN]
        nonce_prefix = header[4 + SALT_LEN :]
        aesgcm = AESGCM(derive_key(pin, salt))
        remaining = payload_size - len(header)
        counter = 0
        temp = tempfile.NamedTemporaryFile(
            mode="wb", dir=self.download_dir, prefix=".pardus-transfer-", delete=False
        )
        try:
            with temp:
                while remaining:
                    frame_len_data = net_util.recv_exact(conn, 4)
                    if frame_len_data is None:
                        raise FileTransferError("Şifreli aktarım erken sona erdi.")
                    frame_len = struct.unpack("!I", frame_len_data)[0]
                    if frame_len < 16 or frame_len > SECRET_CHUNK_SIZE + 16:
                        raise FileTransferError("Geçersiz şifreli aktarım parçası.")
                    remaining -= 4
                    if frame_len > remaining:
                        raise FileTransferError("Şifreli aktarım boyutu tutarsız.")
                    frame = net_util.recv_exact(conn, frame_len)
                    if frame is None:
                        raise FileTransferError("Şifreli aktarım erken sona erdi.")
                    remaining -= frame_len
                    temp.write(aesgcm.decrypt(_secret_nonce(nonce_prefix, counter), frame, None))
                    counter += 1
            if remaining != 0:
                raise FileTransferError("Şifreli aktarım boyutu tutarsız.")
            return temp.name
        except Exception as e:
            try:
                os.unlink(temp.name)
            except OSError:
                logger.warning("Geçici aktarım dosyası silinemedi: %s", temp.name)
            raise

    def _log_history(self, file_name, size_bytes, peer, status, secret):
        """Alım kaydını geçmişe ekler. history None ise sessizce atlar;
        geçmiş hatası transferi bozmamalı."""
        if self.history is None:
            return
        try:
            self.history.add_received(file_name, size_bytes, peer, status=status, secret=secret)
        except Exception as e:
            logger.error("Geçmiş kaydı eklenemedi: %s", e)
