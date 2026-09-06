"""
P2P Mesh Ağı — Parça-Parça (Fragmented) Dosya Transferi.

Bir cihaz çevrimdışıysa veya doğrudan erişilemiyorsa, dosya parçaları
mesh ağındaki ara (relay) cihazlar üzerinden yönlendirilir.

Her cihaz hem istemci hem sunucu hem de röle olarak çalışır.
"""

import hashlib
import json
import logging
import os
import socket
import struct
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set

from pardus_paylasim.discovery import net_util

logger = logging.getLogger(__name__)

MESH_PORT = 8920
CHUNK_SIZE = 64 * 1024  # 64 KB
MAX_RELAY_HOPS = 3

FRAG_MAGIC = b"PMSH"
FRAG_REQUEST = 0x01
FRAG_OFFER = 0x02
FRAG_DATA = 0x03
FRAG_ACK = 0x04
FRAG_COMPLETE = 0x05
FRAG_RELAY = 0x06
FRAG_PEER_LIST = 0x07
FRAG_CANCEL = 0x08


@dataclass
class MeshPeer:
    id: str
    ip: str
    port: int
    is_online: bool = True
    last_seen: float = field(default_factory=time.time)
    capabilities: Set[str] = field(default_factory=set)
    relayed_through: Optional[str] = None


@dataclass
class TransferJob:
    transfer_id: str
    file_name: str
    file_size: int
    total_chunks: int
    file_hash: str
    received_chunks: Dict[int, bytes] = field(default_factory=dict)
    pending_requests: Set[int] = field(default_factory=set)
    status: str = "pending"
    source_peer_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    is_sender: bool = False
    file_path: Optional[str] = None


class MeshProtocol:
    """Mesh protokolü paketleme/çözme."""

    @staticmethod
    def pack_fragment(
        frag_type: int,
        transfer_id: str,
        chunk_index: int,
        total_chunks: int,
        data: bytes,
        source_peer_id: str,
        hop_count: int,
        file_hash: str,
    ) -> bytes:
        tid = transfer_id.encode("utf-8")[:8].ljust(8, b"\x00")
        fh = file_hash.encode("utf-8")[:32].ljust(32, b"\x00")
        src = source_peer_id.encode("utf-8")[:32].ljust(32, b"\x00")
        header = struct.pack(
            "!BB8s III 32s 32s I",
            frag_type,
            len(transfer_id),
            tid,
            chunk_index,
            total_chunks,
            len(data),
            fh,
            src,
            hop_count,
        )
        return FRAG_MAGIC + header + data

    @staticmethod
    def unpack_fragment(raw: bytes) -> Optional[Dict]:
        if len(raw) < 4 + 90 or raw[:4] != FRAG_MAGIC:
            return None
        try:
            hdr = struct.unpack("!BB8s III 32s 32s I", raw[4 : 4 + 90])
            ftype, nlen, tid, cidx, total, dlen, fh, src, hop = hdr
            tid_str = tid.rstrip(b"\x00").decode("utf-8")
            fh_str = fh.rstrip(b"\x00").decode("utf-8")
            src_str = src.rstrip(b"\x00").decode("utf-8")
            data = raw[4 + 90 : 4 + 90 + dlen]
            return {
                "type": ftype,
                "transfer_id": tid_str,
                "chunk_index": cidx,
                "total_chunks": total,
                "data": data,
                "file_hash": fh_str,
                "source_peer_id": src_str,
                "hop_count": hop,
            }
        except Exception as e:
            return None


class MeshNode:
    def __init__(
        self,
        peer_id: str,
        local_ip: str,
        mesh_port: int = MESH_PORT,
        on_transfer_complete: Optional[Callable] = None,
        on_peer_discovered: Optional[Callable] = None,
    ):
        self.peer_id = peer_id
        self.local_ip = local_ip
        self.mesh_port = mesh_port
        self.on_transfer_complete = on_transfer_complete
        self.on_peer_discovered = on_peer_discovered
        self.on_peer_lost = None  # Callback(peer_id) — keşif kaybında UI tazeler.
        self.peers: Dict[str, MeshPeer] = {}
        self.transfers: Dict[str, TransferJob] = {}
        self._lock = threading.RLock()
        self._running = False
        self._server: Optional[socket.socket] = None
        self._accept_thread: Optional[threading.Thread] = None
        self._discovery = None
        self.protocol = MeshProtocol()

    def start(self):
        if self._running:
            return
        self._running = True
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._server.bind(("0.0.0.0", self.mesh_port))
            self._server.listen(15)
            self._server.settimeout(1.0)
            if self.mesh_port == 0:
                self.mesh_port = self._server.getsockname()[1]
        except OSError:
            try:
                self._server.close()
            except OSError:
                pass
            self._server = None
            self._running = False
            return
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept_thread.start()

    def start_discovery(self) -> bool:
        """mDNS ile mesh eşlerini otomatik bul (node çalışıyor olmalı).

        zeroconf yoksa False döner; manuel `add_peer` her zaman çalışır.
        Bulunan eşler otomatik eklenir + `on_peer_discovered` çağrılır.
        """
        if not self._running:
            return False
        if self._discovery is not None and self._discovery.running:
            return True
        from pardus_paylasim.discovery.mesh.mdns import MeshDiscovery

        def _on_peer(ip: str, port: int, pid: str):
            self.add_peer(MeshPeer(id=pid, ip=ip, port=port))
            if self.on_peer_discovered:
                try:
                    self.on_peer_discovered(pid)
                except Exception as e:
                    logger.debug("on_peer_discovered hatası: %s", e)

        def _on_lost(pid: str):
            self.remove_peer(pid)
            if self.on_peer_lost:
                try:
                    self.on_peer_lost(pid)
                except Exception as e:
                    logger.debug("on_peer_lost hatası: %s", e)

        disc = MeshDiscovery(
            peer_id=self.peer_id, local_ip=self.local_ip,
            mesh_port=self.mesh_port, on_peer=_on_peer, on_peer_lost=_on_lost,
        )
        ok = disc.start()
        if ok:
            self._discovery = disc
        return ok

    def stop_discovery(self):
        disc, self._discovery = self._discovery, None
        if disc is not None:
            try:
                disc.stop()
            except Exception as e:
                logger.debug("keşif durdurma hatası: %s", e)

    @property
    def discovery_running(self) -> bool:
        return self._discovery is not None and self._discovery.running

    def stop(self):
        self.stop_discovery()
        self._running = False
        if self._server is not None:
            try:
                try:
                    self._server.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                self._server.close()
            except OSError:
                pass
            finally:
                self._server = None
        thread, self._accept_thread = self._accept_thread, None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)

    def add_peer(self, peer: MeshPeer):
        with self._lock:
            self.peers[peer.id] = peer

    def remove_peer(self, pid: str):
        with self._lock:
            self.peers.pop(pid, None)

    def offer_file_mesh(
        self, transfer_id: str, file_name: str,
        file_size: int, file_path: str, target: str
    ):
        chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE
        digest = hashlib.sha256()
        with open(file_path, "rb") as hf:
            for piece in iter(lambda: hf.read(1024 * 1024), b""):
                digest.update(piece)
        file_hash = digest.hexdigest()[:32]
        job = TransferJob(
            transfer_id=transfer_id,
            file_name=file_name,
            file_size=file_size,
            total_chunks=chunks,
            file_hash=file_hash,
            is_sender=True,
            file_path=file_path,
        )
        with self._lock:
            self.transfers[transfer_id] = job
        with open(file_path, "rb") as f:
            for i in range(chunks):
                chunk = f.read(CHUNK_SIZE)
                chash = hashlib.sha256(chunk).hexdigest()[:32]
                self._send_data_chunk(
                    transfer_id, i, chunks, chunk, chash, target, 0
                )

    def _send_data_chunk(
        self, tid: str, idx: int, total: int,
        data: bytes, chash: str, target: str, hop: int
    ):
        packed = self.protocol.pack_fragment(
            FRAG_DATA, tid, idx, total, data, self.peer_id, hop, chash
        )
        with self._lock:
            if target not in self.peers:
                return
            peer = self.peers[target]
        self._send_raw(peer.ip, peer.port, packed)

    def _send_raw(self, ip: str, port: int, data: bytes):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5.0)
                s.connect((ip, port))
                s.sendall(struct.pack("!I", len(data)))
                s.sendall(data)
        except OSError:
            pass

    def _accept_loop(self):
        while self._running:
            server = self._server
            if server is None:
                break
            try:
                conn, addr = server.accept()
                threading.Thread(
                    target=self._handle, args=(conn, addr), daemon=True
                ).start()
            except OSError:
                if not self._running:
                    break

    def _handle(self, conn: socket.socket, addr):
        try:
            conn.settimeout(15)
            size_data = net_util.recv_exact(conn, 4)
            if not size_data:
                return
            size = struct.unpack("!I", size_data)[0]
            if size > 10 * 1024 * 1024:
                return
            raw = net_util.recv_exact(conn, size)
            if not raw:
                return
            frag = self.protocol.unpack_fragment(raw)
            if frag:
                self._process(frag)
            else:
                try:
                    msg = json.loads(raw.decode("utf-8"))
                    if msg.get("type") == "presence":
                        p = MeshPeer(
                            id=msg["peer_id"],
                            ip=msg["ip"],
                            port=msg.get("port", self.mesh_port),
                        )
                        self.add_peer(p)
                except Exception as e:
                    pass
        except Exception as e:
            pass
        finally:
            conn.close()

    def _process(self, frag: Dict):
        t = frag["type"]
        tid = frag["transfer_id"]
        if t == FRAG_DATA:
            self._handle_data(frag)
        elif t == FRAG_ACK:
            logger.debug("ACK: %s chunk %d", tid, frag["chunk_index"])

    def _handle_data(self, frag: Dict):
        tid = frag["transfer_id"]
        idx = frag["chunk_index"]
        data = frag["data"]
        with self._lock:
            if tid not in self.transfers:
                return
            job = self.transfers[tid]
        chunk_hash = hashlib.sha256(data).hexdigest()[:32]
        if chunk_hash != frag["file_hash"]:
            logger.warning("Hash mismatch chunk %d", idx)
            return
        with self._lock:
            job.received_chunks[idx] = data
            if len(job.received_chunks) == job.total_chunks:
                job.status = "complete"
                all_data = b"".join(
                    job.received_chunks[k] for k in sorted(job.received_chunks)
                )
                if self.on_transfer_complete:
                    self.on_transfer_complete(tid, job.file_name, all_data)
