import logging
import os
import socket
import ssl
import struct
import threading
import tempfile
from typing import Optional

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

    def send_file(self, file_path, secret_pin=None, progress_callback=None, rel_name=None):
        """Tek dosya gönderir.

        rel_name verilirse tel-üzeri ad olarak kullanılır (klasör transferinde
        göreli yol; örn. 'belgeler/alt/a.txt'). None ise taban ad kullanılır —
        mevcut çağıranlar için davranış aynen korunur.
        """
        if not os.path.exists(file_path):
            raise FileTransferError("Dosya bulunamadı.")

        file_size = os.path.getsize(file_path)
        file_name = rel_name if rel_name else os.path.basename(file_path)

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(10)
            if self.ssl_context:
                conn = self.ssl_context.wrap_socket(s, server_hostname=self.target_ip)
            else:
                conn = s
            conn.connect((self.target_ip, self.target_port))

            # 1. Byte: Mode (0: Normal, 1: Secret)
            mode_byte = b"\x01" if secret_pin else b"\x00"
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
                        if progress_callback:
                            progress_callback(sent / file_size if file_size else 1.0)
                if progress_callback:
                    progress_callback(1.0)
            else:
                # Normal mode: chunked
                if file_size > MAX_PAYLOAD_SIZE:
                    raise FileTransferError("Dosya boyutu aktarım sınırını aşıyor.")
                conn.sendall(struct.pack("!Q", file_size))
                sent = 0
                with open(file_path, "rb") as f:
                    while True:
                        chunk = f.read(65536)
                        if not chunk:
                            break
                        conn.sendall(chunk)
                        sent += len(chunk)
                        if progress_callback:
                            progress_callback(sent / file_size)

            # Wait for ACK
            ack = conn.recv(1)
            if ack != b"\x01":
                raise FileTransferError("Alıcı cihaz dosyayı kabul etmedi veya hata oluştu.")

    def send_files(self, file_paths, secret_pin=None, progress_callback=None):
        """Birden çok dosyayı sırayla gönderir (her biri ayrı bağlantı).

        progress_callback(oran, gonderilen_index, toplam) — genel ilerleme.
        Bir dosya reddedilir/başarısız olursa istisna yükseltilir; kalanlar
        gönderilmez (çağıran istediğini yeniden deneyebilir).
        """
        total = len(file_paths)
        for idx, path in enumerate(file_paths):
            self.send_file(path, secret_pin)
            if progress_callback:
                progress_callback((idx + 1) / total, idx + 1, total)

    def send_folder(self, folder_path, secret_pin=None, progress_callback=None):
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
            self.send_file(path, secret_pin, rel_name=rel)
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
            is_secret = mode_byte == b"\x01"

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
            peer_ip = ""
            try:
                peer_ip = conn.getpeername()[0]
            except OSError:
                pass

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
        except Exception:
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
        except Exception:
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
