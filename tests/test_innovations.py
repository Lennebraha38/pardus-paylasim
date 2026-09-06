"""
Modül testleri:
- Mesh Ağı (parça-parça transfer)
- WebRTC Data Channel
- Asenkron Transfer Yönetimi
"""

import os
import sys
import time
import threading

import pytest

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")


# ──────────────────────────────────────────────────────────
#  Mesh Ağı Testleri
# ──────────────────────────────────────────────────────────

class TestMeshProtocol:
    """Mesh protokolü paketleme/çözme."""

    def test_pack_unpack_data(self):
        """Parça paketlenip geri açılabilmeli."""
        from pardus_paylasim.discovery.mesh.mesh_network import (
            MeshProtocol, FRAG_DATA,
        )
        packed = MeshProtocol.pack_fragment(
            FRAG_DATA, "abc12345", 0, 3, b"hello world",
            "peer_xyz", hop_count=1, file_hash="a" * 32,
        )
        parsed = MeshProtocol.unpack_fragment(packed)
        assert parsed is not None
        assert parsed["transfer_id"] == "abc12345"
        assert parsed["chunk_index"] == 0
        assert parsed["total_chunks"] == 3
        assert parsed["data"] == b"hello world"
        assert parsed["hop_count"] == 1

    def test_invalid_magic_returns_none(self):
        from pardus_paylasim.discovery.mesh.mesh_network import MeshProtocol
        assert MeshProtocol.unpack_fragment(b"NOPE" + b"\x00" * 200) is None

    def test_truncation_returns_none(self):
        from pardus_paylasim.discovery.mesh.mesh_network import MeshProtocol
        assert MeshProtocol.unpack_fragment(b"\x00\x00\x00") is None


class TestMeshNode:
    """MeshNode yaşam döngüsü."""

    def test_node_starts_and_stops(self):
        """Node başlatılıp durdurulabilmeli."""
        from pardus_paylasim.discovery.mesh.mesh_network import MeshNode
        node = MeshNode("test_node_1", "127.0.0.1", mesh_port=18920)
        try:
            node.start()
            time.sleep(0.2)
            assert node._running is True
        finally:
            node.stop()
            time.sleep(0.1)
        assert node._running is False
        assert node._server is None

    def test_add_and_remove_peer(self):
        from pardus_paylasim.discovery.mesh.mesh_network import MeshNode, MeshPeer
        node = MeshNode("n1", "127.0.0.1", mesh_port=18921)
        peer = MeshPeer(id="p1", ip="127.0.0.1", port=18921)
        node.add_peer(peer)
        assert "p1" in node.peers
        node.remove_peer("p1")
        assert "p1" not in node.peers

    def test_chunk_size_reasonable(self):
        """CHUNK_SIZE makul olmalı (32KB-1MB arası)."""
        from pardus_paylasim.discovery.mesh.mesh_network import CHUNK_SIZE
        assert 32 * 1024 <= CHUNK_SIZE <= 1024 * 1024

    def test_max_relay_hops_limited(self):
        """MAX_RELAY_HOPS sonsuz döngüyü engellemeli."""
        from pardus_paylasim.discovery.mesh.mesh_network import MAX_RELAY_HOPS
        assert 1 <= MAX_RELAY_HOPS <= 5

    def test_frag_types_distinct(self):
        from pardus_paylasim.discovery.mesh.mesh_network import (
            FRAG_REQUEST, FRAG_OFFER, FRAG_DATA, FRAG_ACK,
            FRAG_COMPLETE, FRAG_RELAY, FRAG_PEER_LIST, FRAG_CANCEL,
        )
        types = {FRAG_REQUEST, FRAG_OFFER, FRAG_DATA, FRAG_ACK,
                 FRAG_COMPLETE, FRAG_RELAY, FRAG_PEER_LIST, FRAG_CANCEL}
        assert len(types) == 8


# ──────────────────────────────────────────────────────────
#  WebRTC Data Channel Testleri
# ──────────────────────────────────────────────────────────

class TestSDPMessage:
    """SDP mesaj oluşturma."""

    def test_offer_format(self):
        from pardus_paylasim.screen.webrtc.data_channel import SDPMessage
        offer = SDPMessage.create_offer("abc12345", {"codecs": ["jpeg"]})
        import json
        msg = json.loads(offer)
        assert msg["type"] == "offer"
        assert msg["session_id"] == "abc12345"
        assert "jpeg" in msg["sdp"]["codecs"]

    def test_answer_format(self):
        from pardus_paylasim.screen.webrtc.data_channel import SDPMessage
        answer = SDPMessage.create_answer("xyz98765", {})
        import json
        msg = json.loads(answer)
        assert msg["type"] == "answer"
        assert msg["session_id"] == "xyz98765"

    def test_ice_candidate_format(self):
        from pardus_paylasim.screen.webrtc.data_channel import SDPMessage
        ice = SDPMessage.create_ice_candidate("sid", "192.168.1.5", 8921)
        import json
        msg = json.loads(ice)
        assert msg["type"] == "ice"
        assert msg["candidate"]["ip"] == "192.168.1.5"
        assert msg["candidate"]["port"] == 8921


class TestWebRTCSession:
    """WebRTCScreenSession yaşam döngüsü."""

    def test_session_creation(self):
        from pardus_paylasim.screen.webrtc.data_channel import WebRTCScreenSession
        sess = WebRTCScreenSession("sid1", "peer1", is_offerer=True)
        assert sess.session_id == "sid1"
        assert sess.peer_id == "peer1"
        assert sess.is_offerer is True
        assert sess.state.frames_sent == 0
        assert sess.state.frames_received == 0

    def test_session_state_tracking(self):
        from pardus_paylasim.screen.webrtc.data_channel import WebRTCScreenSession
        sess = WebRTCScreenSession("s2", "p2", is_offerer=False)
        sess.state.frames_sent = 5
        sess.state.bytes_sent = 1024
        assert sess.state.frames_sent == 5
        assert sess.state.bytes_sent == 1024


class TestWebRTCNode:
    """WebRTC düğümü."""

    def test_node_lifecycle(self):
        from pardus_paylasim.screen.webrtc.data_channel import WebRTCScreenNode
        node = WebRTCScreenNode("test_peer", port=18922)
        try:
            node.start()
            time.sleep(0.2)
            assert node._running is True
        finally:
            node.stop()
            time.sleep(0.1)
        assert node._running is False
        assert node._server_socket is None

    def test_create_session(self):
        from pardus_paylasim.screen.webrtc.data_channel import WebRTCScreenNode
        node = WebRTCScreenNode("p1", port=18923)
        sess = node.create_session("remote_peer")
        assert sess.peer_id == "remote_peer"
        assert sess.is_offerer is True
        assert sess.session_id in node.sessions

    def test_handle_sdp_offer(self):
        from pardus_paylasim.screen.webrtc.data_channel import (
            WebRTCScreenNode, SDPMessage,
        )
        node = WebRTCScreenNode("p1", port=18924)
        offer = SDPMessage.create_offer("test_sid", {"codecs": ["jpeg"]})
        sess = node.handle_sdp(offer)
        assert sess is not None
        assert sess.session_id == "test_sid"


# ──────────────────────────────────────────────────────────
#  Asenkron Transfer Testleri
# ──────────────────────────────────────────────────────────

class TestAsyncTransferStore:
    """SQLite-backed asenkron transfer."""

    @pytest.fixture
    def temp_store(self, tmp_path):
        from pardus_paylasim.discovery.async_transfer.manager import (
            AsyncTransferStore,
        )
        return AsyncTransferStore(db_path=str(tmp_path / "test.db"))

    def test_queue_transfer(self, temp_store):
        from pardus_paylasim.discovery.async_transfer.manager import (
            AsyncTransfer, AsyncTransferStore,
        )
        t = AsyncTransfer(
            id="t1", file_name="a.txt", file_size=10, file_hash="abc",
            sender_id="s1", sender_name="Ahmet", receiver_id="r1",
            status="pending", file_path="/tmp/a.txt",
        )
        assert temp_store.queue_transfer(t) is True

    def test_get_pending_for_receiver(self, temp_store):
        from pardus_paylasim.discovery.async_transfer.manager import (
            AsyncTransfer, AsyncTransferStore,
        )
        t1 = AsyncTransfer(
            id="t1", file_name="a.txt", file_size=10, file_hash="abc",
            sender_id="s1", sender_name="Ahmet", receiver_id="r1",
            status="pending", file_path="/tmp/a.txt",
        )
        t2 = AsyncTransfer(
            id="t2", file_name="b.txt", file_size=20, file_hash="def",
            sender_id="s1", sender_name="Ahmet", receiver_id="r2",
            status="pending", file_path="/tmp/b.txt",
        )
        temp_store.queue_transfer(t1)
        temp_store.queue_transfer(t2)
        pending = temp_store.get_pending_for_receiver("r1")
        assert len(pending) == 1
        assert pending[0].id == "t1"

    def test_mark_delivered(self, temp_store):
        from pardus_paylasim.discovery.async_transfer.manager import (
            AsyncTransfer, AsyncTransferStore,
        )
        t = AsyncTransfer(
            id="t1", file_name="a.txt", file_size=10, file_hash="abc",
            sender_id="s1", sender_name="Ahmet", receiver_id="r1",
            status="pending", file_path="/tmp/a.txt",
        )
        temp_store.queue_transfer(t)
        temp_store.mark_delivered("t1")
        pending = temp_store.get_pending_for_receiver("r1")
        assert len(pending) == 0

    def test_cancel_transfer(self, temp_store):
        from pardus_paylasim.discovery.async_transfer.manager import (
            AsyncTransfer, AsyncTransferStore,
        )
        t = AsyncTransfer(
            id="t1", file_name="a.txt", file_size=10, file_hash="abc",
            sender_id="s1", sender_name="Ahmet", receiver_id="r1",
            status="pending", file_path="/tmp/a.txt",
        )
        temp_store.queue_transfer(t)
        temp_store.cancel_transfer("t1")
        pending = temp_store.get_pending_for_receiver("r1")
        assert len(pending) == 0

    def test_dedup_by_hash(self, temp_store):
        from pardus_paylasim.discovery.async_transfer.manager import (
            AsyncTransfer, AsyncTransferStore,
        )
        t = AsyncTransfer(
            id="t1", file_name="a.txt", file_size=10, file_hash="samehash",
            sender_id="s1", sender_name="Ahmet", receiver_id="r1",
            status="pending", file_path="/tmp/a.txt",
        )
        temp_store.queue_transfer(t)
        existing = temp_store.get_transfer_by_hash("samehash")
        assert existing is not None
        assert existing.file_hash == "samehash"

    def test_history_logging(self, temp_store):
        from pardus_paylasim.discovery.async_transfer.manager import (
            AsyncTransfer, AsyncTransferStore,
        )
        t = AsyncTransfer(
            id="t1", file_name="a.txt", file_size=10, file_hash="abc",
            sender_id="s1", sender_name="Ahmet", receiver_id="r1",
            status="pending", file_path="/tmp/a.txt",
        )
        temp_store.queue_transfer(t)
        history = temp_store.get_history("t1")
        assert any(h["type"] == "queued" for h in history)


class TestAsyncTransferManager:
    """Asenkron transfer yönetimi."""

    def test_queue_offline_file(self, tmp_path):
        from pardus_paylasim.discovery.async_transfer.manager import (
            AsyncTransferManager, AsyncTransferStore,
        )
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        store_path = str(tmp_path / "test.db")
        mgr = AsyncTransferManager(
            device_id="local",
            device_name="Test Device",
            store=AsyncTransferStore(db_path=store_path),
        )

        tid = mgr.queue_offline(
            str(f), receiver_id="remote1", receiver_name="Remote"
        )
        assert tid is not None
        pending = mgr.store.get_pending_for_receiver("remote1")
        assert len(pending) == 1
        assert pending[0].file_name == "test.txt"

    def test_check_pending_for_marks_delivered(self, tmp_path):
        from pardus_paylasim.discovery.async_transfer.manager import (
            AsyncTransferManager, AsyncTransferStore,
        )
        f = tmp_path / "test.txt"
        f.write_text("hello")
        store_path = str(tmp_path / "test.db")
        mgr = AsyncTransferManager(
            device_id="local",
            device_name="Test",
            store=AsyncTransferStore(db_path=store_path),
        )

        mgr.queue_offline(str(f), receiver_id="peer1", receiver_name="P1")
        delivered = mgr.check_pending_for("peer1")
        assert len(delivered) == 1
        # Tekrar kontrol: pending kalmadı
        again = mgr.check_pending_for("peer1")
        assert len(again) == 0


class TestWebRTCScreenNode:
    """WebRTCScreenNode yaşam döngüsü."""

    def test_node_lifecycle(self):
        from pardus_paylasim.screen.webrtc.data_channel import WebRTCScreenNode
        node = WebRTCScreenNode("test_peer", port=18922)
        try:
            node.start()
            time.sleep(0.2)
            assert node._running is True
        finally:
            node.stop()
            time.sleep(0.1)
        assert node._running is False
        assert node._server_socket is None

    def test_create_session(self):
        from pardus_paylasim.screen.webrtc.data_channel import WebRTCScreenNode
        node = WebRTCScreenNode("test_peer", port=18923)
        sess = node.create_session("peer_id")
        assert sess.session_id is not None
        assert sess.peer_id == "peer_id"
        assert sess.is_offerer is True
        assert len(node.sessions) == 1
        node.stop()

    def test_sdp_offer(self):
        from pardus_paylasim.screen.webrtc.data_channel import SDPMessage
        offer = SDPMessage.create_offer("sess123", {"codecs": ["jpeg"]})
        assert "offer" in offer
        assert "sess123" in offer
        assert "jpeg" in offer

    def test_sdp_answer(self):
        from pardus_paylasim.screen.webrtc.data_channel import SDPMessage
        ans = SDPMessage.create_answer("sess123", {"codecs": ["jpeg"]})
        assert "answer" in ans
        assert "sess123" in ans

    def test_sdp_ice_candidate(self):
        from pardus_paylasim.screen.webrtc.data_channel import SDPMessage
        ice = SDPMessage.create_ice_candidate("sess123", "192.168.1.1", 8921)
        assert "ice" in ice
        assert "192.168.1.1" in ice


class TestAsyncDedupEdgeCases:
    """Async dedup edge case testleri."""

    def test_delivered_not_queued_again(self, tmp_path):
        from pardus_paylasim.discovery.async_transfer.manager import (
            AsyncTransferManager, AsyncTransferStore,
        )
        f = tmp_path / "dup.txt"
        f.write_text("icerik")
        db = str(tmp_path / "t.db")
        mgr = AsyncTransferManager(
            "dev", "Dev", store=AsyncTransferStore(db_path=db)
        )
        tid1 = mgr.queue_offline(str(f), "peer1", "P1")
        assert tid1 is not None
        mgr.check_pending_for("peer1")
        tid2 = mgr.queue_offline(str(f), "peer1", "P1")
        assert tid2 is None

    def test_failed_transfer_not_deduped(self, tmp_path):
        from pardus_paylasim.discovery.async_transfer.manager import (
            AsyncTransferManager, AsyncTransferStore,
        )
        f = tmp_path / "failed.txt"
        f.write_text("icerik")
        db = str(tmp_path / "t.db")
        mgr = AsyncTransferManager(
            "dev", "Dev", store=AsyncTransferStore(db_path=db)
        )
        tid1 = mgr.queue_offline(str(f), "peer1", "P1")
        mgr.store.mark_failed(tid1)
        tid2 = mgr.queue_offline(str(f), "peer1", "P1")
        assert tid2 is not None

    def test_cancel_transfer(self, tmp_path):
        from pardus_paylasim.discovery.async_transfer.manager import (
            AsyncTransferManager, AsyncTransferStore,
        )
        f = tmp_path / "cancel.txt"
        f.write_text("icerik")
        db = str(tmp_path / "t.db")
        mgr = AsyncTransferManager(
            "dev", "Dev", store=AsyncTransferStore(db_path=db)
        )
        tid = mgr.queue_offline(str(f), "peer1", "P1")
        mgr.cancel(tid)
        pending = mgr.store.get_pending_for_receiver("peer1")
        assert len(pending) == 0


class TestDataChannelProtocol:
    """DataChannel protokol testleri."""

    def test_data_channel_send_receive(self):
        """İki soket üzerinden mesaj gönderip alabilmeli."""
        import socket
        import threading
        import time as _time
        from pardus_paylasim.screen.webrtc.data_channel import DataChannel

        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(("127.0.0.1", 0))
        server_sock.listen(1)
        server_sock.settimeout(5.0)
        port = server_sock.getsockname()[1]

        received = []
        server_dc_holder: list = []

        def serve():
            try:
                conn, _ = server_sock.accept()
                dc = DataChannel(conn)
                dc.on_message = lambda data: received.append(data)
                dc.start()
                server_dc_holder.append(dc)
            except OSError:
                pass

        t = threading.Thread(target=serve, daemon=True)
        t.start()

        client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_sock.settimeout(5.0)
        client_dc = DataChannel(client_sock)
        try:
            client_sock.connect(("127.0.0.1", port))
            client_dc.start()

            deadline = _time.time() + 5.0
            while not server_dc_holder and _time.time() < deadline:
                _time.sleep(0.05)
            assert server_dc_holder, "sunucu tarafı bağlanamadı"

            client_dc.send(b"hello webrtc")
            deadline = _time.time() + 5.0
            while b"hello webrtc" not in received and _time.time() < deadline:
                _time.sleep(0.05)
            assert b"hello webrtc" in received
        finally:
            client_dc.close()
            for dc in server_dc_holder:
                try:
                    dc.close()
                except OSError:
                    pass
            try:
                server_sock.close()
            except OSError:
                pass
            t.join(timeout=2.0)

    def test_close_idempotent(self):
        """close() birden fazla çağrılabilmeli."""
        import socket
        from pardus_paylasim.screen.webrtc.data_channel import DataChannel
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        dc = DataChannel(s)
        dc.close()
        dc.close()
        dc.close()
        assert dc._closed is True

    def test_large_frame_fragmented_and_reassembled(self):
        """64KB üstü kare parçalanıp alıcıda birebir birleşmeli."""
        import os
        import socket
        import threading
        import time as _time
        from pardus_paylasim.screen.webrtc.data_channel import DataChannel

        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(("127.0.0.1", 0))
        server_sock.listen(1)
        server_sock.settimeout(10.0)
        port = server_sock.getsockname()[1]

        received = []
        holder: list = []

        def serve():
            try:
                conn, _ = server_sock.accept()
                dc = DataChannel(conn)
                dc.on_message = lambda data: received.append(data)
                dc.start()
                holder.append(dc)
            except OSError:
                pass

        t = threading.Thread(target=serve, daemon=True)
        t.start()

        client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_sock.settimeout(10.0)
        client_dc = DataChannel(client_sock)
        try:
            client_sock.connect(("127.0.0.1", port))
            client_dc.start()
            deadline = _time.time() + 5.0
            while not holder and _time.time() < deadline:
                _time.sleep(0.05)
            assert holder, "sunucu tarafı bağlanamadı"

            big = os.urandom(200 * 1024)
            assert len(big) > 65535
            client_dc.send(big)
            deadline = _time.time() + 10.0
            while not received and _time.time() < deadline:
                _time.sleep(0.05)
            assert len(received) == 1
            assert received[0] == big
        finally:
            client_dc.close()
            for dc in holder:
                try:
                    dc.close()
                except OSError:
                    pass
            try:
                server_sock.close()
            except OSError:
                pass
            t.join(timeout=2.0)
