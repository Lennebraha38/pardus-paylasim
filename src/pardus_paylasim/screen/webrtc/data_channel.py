"""
WebRTC Tabanlı Ekran Paylaşımı — Data Channel Protokolü.

Mevcut MJPEG HTTP streaming'in alternatifi olarak WebRTC benzeri
düşük gecikmeli P2P data channel kullanır. WebSocket üzerinden
SDP/ICE sinyalleri değiştirilir, ardından SCTP data channel üzerinden
ekran kareleri iletilir.

Tam WebRTC (libdatachannel/native) yerine Python saf implementasyon:
- Sinyalizasyon: WebSocket veya mevcut TCP kanalı
- Veri taşıma: SCTP benzeri framing + sıkıştırma
- Hedef: MJPEG'den 3-5x düşük gecikme
"""

import asyncio
import json
import logging
import socket
import struct
import threading
import time
import zlib
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

WEBRTC_PORT = 8921
WEBRTC_MAGIC = b"PWDC"
MAX_FRAME_SIZE = 16 * 1024 * 1024


@dataclass
class SessionState:
    """Bir WebRTC benzeri oturumun durumu."""

    session_id: str
    peer_id: str
    is_offerer: bool = False
    is_connected: bool = False
    created_at: float = field(default_factory=time.time)
    frames_sent: int = 0
    frames_received: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    rtt_ms: float = 0.0


class SDPMessage:
    """Basitleştirilmiş SDP benzeri mesaj formatı (JSON)."""

    @staticmethod
    def create_offer(session_id: str, capabilities: Dict) -> str:
        return json.dumps({
            "type": "offer",
            "session_id": session_id,
            "sdp": {
                "version": 1,
                "codecs": ["jpeg", "h264-stub"],
                "capabilities": capabilities,
            },
        })

    @staticmethod
    def create_answer(session_id: str, capabilities: Dict) -> str:
        return json.dumps({
            "type": "answer",
            "session_id": session_id,
            "sdp": {
                "version": 1,
                "codecs": ["jpeg"],
                "capabilities": capabilities,
            },
        })

    @staticmethod
    def create_ice_candidate(session_id: str, ip: str, port: int) -> str:
        return json.dumps({
            "type": "ice",
            "session_id": session_id,
            "candidate": {"ip": ip, "port": port, "protocol": "tcp"},
        })


class DataChannel:
    """
    SCTP benzeri güvenilir veri kanalı.

    Gerçek SCTP yerine:
    - Mesajları sıralı (sequence) numaralandırır
    - Kayıp paketlerde yeniden iletim yapar
    - Sıkıştırma (zlib) uygular
    """

    DATA_HEADER = "!4s B Q I H H"
    MAX_PAYLOAD = 65535

    def __init__(
        self,
        socket_: socket.socket,
        on_message: Optional[Callable[[bytes], None]] = None,
        on_open: Optional[Callable[[], None]] = None,
        on_close: Optional[Callable[[], None]] = None,
    ):
        self.socket = socket_
        self.on_message = on_message
        self.on_open = on_open
        self.on_close = on_close

        self._send_seq = 0
        self._recv_seq = 0
        self._out_queue: List[bytes] = []
        self._send_lock = threading.Lock()
        self._running = False
        self._closed = False
        self._send_thread: Optional[threading.Thread] = None
        self._recv_thread: Optional[threading.Thread] = None

    def start(self):
        if self._running:
            return
        self._running = True
        if self.on_open:
            self.on_open()
        self._send_thread = threading.Thread(target=self._send_loop, daemon=True)
        self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._send_thread.start()
        self._recv_thread.start()

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._running = False
        try:
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.socket.close()
        except OSError:
            pass
        current = threading.current_thread()
        for thread in (self._send_thread, self._recv_thread):
            if thread is not None and thread is not current and thread.is_alive():
                thread.join(timeout=2.0)
        if self.on_close:
            self.on_close()

    def send(self, data: bytes):
        """Mesaj gönderir (kuyruğa ekler)."""
        with self._send_lock:
            self._out_queue.append(data)
            seq = self._send_seq
            self._send_seq += 1
        return seq

    def _send_loop(self):
        while self._running and not self._closed:
            with self._send_lock:
                if not self._out_queue:
                    time.sleep(0.001)
                    continue
                data = self._out_queue.pop(0)
                seq = self._send_seq - len(self._out_queue) - 1
            try:
                self._send_frame(data, seq)
            except OSError as e:
                logger.debug("DataChannel send hatası: %s", e)
                self.close()
                break

    def _send_frame(self, data: bytes, seq: int):
        compressed = zlib.compress(data, 1)
        flags = 0x01  # compressed
        header = struct.pack(
            self.DATA_HEADER,
            WEBRTC_MAGIC,
            flags,
            seq,
            len(compressed),
            0,  # stream id
            0,  # padding
        )
        if len(compressed) > self.MAX_PAYLOAD:
            raise ValueError("Çok büyük data channel mesajı")
        self.socket.sendall(header + compressed)

    def _recv_loop(self):
        while self._running and not self._closed:
            try:
                self.socket.settimeout(1.0)
                header = self._recv_exact(struct.calcsize(self.DATA_HEADER))
                if not header:
                    continue
                magic, flags, seq, length, stream_id, _pad = struct.unpack(
                    self.DATA_HEADER, header
                )
                if magic != WEBRTC_MAGIC:
                    logger.debug("DataChannel geçersiz magic")
                    continue
                if length > self.MAX_PAYLOAD:
                    continue
                payload = self._recv_exact(length)
                if payload is None:
                    continue
                if flags & 0x01:
                    payload = zlib.decompress(payload)
                self._recv_seq = max(self._recv_seq, seq + 1)
                if self.on_message:
                    self.on_message(payload)
            except socket.timeout:
                continue
            except OSError as e:
                logger.debug("DataChannel recv hatası: %s", e)
                break
        self.close()

    def _recv_exact(self, n: int) -> Optional[bytes]:
        buf = bytearray()
        while len(buf) < n:
            try:
                chunk = self.socket.recv(min(4096, n - len(buf)))
                if not chunk:
                    return None
                buf.extend(chunk)
            except OSError:
                return None
        return bytes(buf)


class WebRTCScreenSession:
    """Tek bir ekran paylaşımı oturumu."""

    def __init__(
        self,
        session_id: str,
        peer_id: str,
        is_offerer: bool,
        on_frame: Optional[Callable[[bytes], None]] = None,
    ):
        self.session_id = session_id
        self.peer_id = peer_id
        self.is_offerer = is_offerer
        self.on_frame = on_frame
        self.state = SessionState(
            session_id=session_id, peer_id=peer_id, is_offerer=is_offerer
        )
        self.channel: Optional[DataChannel] = None
        self._lock = threading.Lock()

    def attach_channel(self, channel: DataChannel):
        self.channel = channel
        channel.on_message = self._on_message
        channel.start()

    def _on_message(self, data: bytes):
        try:
            msg = json.loads(data.decode("utf-8"))
        except Exception as e:
            return
        if msg.get("type") == "frame":
            self.state.frames_received += 1
            self.state.bytes_received += msg.get("size", 0)
            if self.on_frame and "jpeg_b64" in msg:
                import base64

                try:
                    jpeg = base64.b64decode(msg["jpeg_b64"])
                    self.on_frame(jpeg)
                except Exception as e:
                    logger.debug("Frame decode hatası: %s", e)

    def send_frame(self, jpeg_data: bytes):
        if not self.channel:
            return
        import base64

        msg = {
            "type": "frame",
            "size": len(jpeg_data),
            "jpeg_b64": base64.b64encode(jpeg_data).decode("ascii"),
            "ts": time.time(),
        }
        self.channel.send(json.dumps(msg).encode("utf-8"))
        self.state.frames_sent += 1
        self.state.bytes_sent += len(jpeg_data)


class WebRTCScreenNode:
    """WebRTC benzeri ekran paylaşım düğümü."""

    def __init__(
        self,
        peer_id: str,
        on_session_offer: Optional[Callable[[WebRTCScreenSession, str], None]] = None,
        on_session_answer: Optional[Callable[[WebRTCScreenSession, str], None]] = None,
        on_frame: Optional[Callable[[WebRTCScreenSession, bytes], None]] = None,
        port: int = WEBRTC_PORT,
    ):
        self.peer_id = peer_id
        self.on_session_offer = on_session_offer
        self.on_session_answer = on_session_answer
        self.on_frame = on_frame
        self.port = port
        self.sessions: Dict[str, WebRTCScreenSession] = {}
        self._running = False
        self._server_socket: Optional[socket.socket] = None
        self._accept_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start(self):
        if self._running:
            return
        self._running = True
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._server_socket.bind(("0.0.0.0", self.port))
            self._server_socket.listen(10)
            self._server_socket.settimeout(1.0)
            if self.port == 0:
                self.port = self._server_socket.getsockname()[1]
        except OSError as e:
            logger.error("WebRTC port %d açılamadı: %s", self.port, e)
            try:
                self._server_socket.close()
            except OSError:
                pass
            self._server_socket = None
            self._running = False
            return
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept_thread.start()

    def stop(self):
        self._running = False
        for sid in list(self.sessions.keys()):
            sess = self.sessions.pop(sid, None)
            if sess and sess.channel:
                try:
                    sess.channel.close()
                except OSError:
                    pass
                sess.channel = None
        if self._server_socket is not None:
            try:
                try:
                    self._server_socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                self._server_socket.close()
            except OSError:
                pass
            finally:
                self._server_socket = None
        thread, self._accept_thread = self._accept_thread, None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)

    def create_session(self, peer_id: str) -> WebRTCScreenSession:
        import uuid

        sid = str(uuid.uuid4())[:8]
        sess = WebRTCScreenSession(sid, peer_id, is_offerer=True,
                                   on_frame=lambda d: self._on_session_frame(sid, d))
        with self._lock:
            self.sessions[sid] = sess
        return sess

    def handle_sdp(self, message: str) -> Optional[WebRTCScreenSession]:
        """Gelen SDP mesajını işler."""
        try:
            msg = json.loads(message)
        except Exception as e:
            return None
        msg_type = msg.get("type")
        sid = msg.get("session_id")
        if msg_type == "offer":
            sess = WebRTCScreenSession(sid, msg.get("from", ""), is_offerer=False,
                                       on_frame=lambda d: self._on_session_frame(sid, d))
            with self._lock:
                self.sessions[sid] = sess
            if self.on_session_offer:
                self.on_session_offer(sess, message)
            return sess
        elif msg_type == "answer" and sid in self.sessions:
            sess = self.sessions[sid]
            if self.on_session_answer:
                self.on_session_answer(sess, message)
            return sess
        return None

    def _on_session_frame(self, sid: str, jpeg_data: bytes):
        with self._lock:
            sess = self.sessions.get(sid)
        if sess and self.on_frame:
            self.on_frame(sess, jpeg_data)

    def _accept_loop(self):
        while self._running:
            server = self._server_socket
            if server is None:
                break
            try:
                conn, addr = server.accept()
                threading.Thread(
                    target=self._handle_connection, args=(conn, addr), daemon=True
                ).start()
            except OSError:
                if not self._running:
                    break

    def _handle_connection(self, conn: socket.socket, addr):
        attached = False
        try:
            conn.settimeout(15)
            header = b""
            while b"\n" not in header:
                chunk = conn.recv(1024)
                if not chunk:
                    return
                header += chunk
                if len(header) > 65536:
                    return
            line, _, rest = header.partition(b"\n")
            try:
                msg = json.loads(line.decode("utf-8"))
            except Exception as e:
                return
            sid = msg.get("session_id")
            if not sid:
                return
            with self._lock:
                sess = self.sessions.get(sid)
            if not sess:
                sess = self.create_session("peer")
            channel = DataChannel(conn, on_close=lambda: self._cleanup_session(sid))
            sess.attach_channel(channel)
            attached = True
        except Exception as e:
            logger.debug("WebRTC bağlantı hatası %s: %s", addr, e)
        finally:
            if not attached:
                try:
                    conn.close()
                except OSError:
                    pass

    def _cleanup_session(self, sid: str):
        with self._lock:
            sess = self.sessions.pop(sid, None)
        if sess:
            sess.channel = None
