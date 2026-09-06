"""
Yeni özellikler için testler:
- Mesh Ağı (parça-parça transfer)
- Yerel AI hassas veri tespiti
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
#  Yerel AI Hassas Veri Tespiti Testleri
# ──────────────────────────────────────────────────────────

class TestLocalSensitiveDetector:
    """LocalSensitiveDetector kuralları ve entegrasyonu."""

    def test_tckn_detection_valid(self):
        """Geçerli TCKN tespit edilmeli."""
        from pardus_paylasim.clipboard.ai.local_detector import (
            LocalSensitiveDetector,
        )
        det = LocalSensitiveDetector()
        result = det.detect("TCKN: 10000000146")
        tckn = [d for d in result.detections if d.label == "tckn"]
        assert len(tckn) >= 1
        assert tckn[0].method == "rule"
        assert tckn[0].severity == "KRİTİK"

    def test_tckn_invalid_not_detected(self):
        """Geçersiz TCKN tespit edilmemeli."""
        from pardus_paylasim.clipboard.ai.local_detector import (
            LocalSensitiveDetector,
        )
        det = LocalSensitiveDetector()
        result = det.detect("TCKN: 00000000000")
        tckn = [d for d in result.detections if d.label == "tckn"]
        assert len(tckn) == 0

    def test_credit_card_luhn(self):
        """Luhn geçerli kart numarası tespit edilmeli."""
        from pardus_paylasim.clipboard.ai.local_detector import (
            LocalSensitiveDetector,
        )
        det = LocalSensitiveDetector()
        result = det.detect("Kart: 4532015112830366")
        cards = [d for d in result.detections if d.label == "credit_card"]
        assert len(cards) >= 1

    def test_iban_validation(self):
        """Geçerli TR IBAN tespit edilmeli."""
        from pardus_paylasim.clipboard.ai.local_detector import (
            LocalSensitiveDetector,
        )
        det = LocalSensitiveDetector()
        result = det.detect("IBAN: TR96 3456 7890 1234 5678 9012 34")
        ibans = [d for d in result.detections if d.label == "iban_tr"]
        assert len(ibans) >= 1

    def test_email_detection(self):
        from pardus_paylasim.clipboard.ai.local_detector import (
            LocalSensitiveDetector,
        )
        det = LocalSensitiveDetector()
        result = det.detect("İletişim: ahmet@example.com")
        emails = [d for d in result.detections if d.label == "email"]
        assert len(emails) == 1

    def test_jwt_detection(self):
        """JWT token tespit edilmeli."""
        from pardus_paylasim.clipboard.ai.local_detector import (
            LocalSensitiveDetector,
        )
        det = LocalSensitiveDetector()
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        result = det.detect(f"Token: {jwt}")
        jwts = [d for d in result.detections if d.label == "jwt"]
        assert len(jwts) >= 1

    def test_api_key_detection(self):
        from pardus_paylasim.clipboard.ai.local_detector import (
            LocalSensitiveDetector,
        )
        det = LocalSensitiveDetector()
        result = det.detect("Key: sk-1234567890abcdef1234567890abcdef")
        keys = [d for d in result.detections if d.label == "api_key"]
        assert len(keys) >= 1

    def test_private_key_detection(self):
        from pardus_paylasim.clipboard.ai.local_detector import (
            LocalSensitiveDetector,
        )
        det = LocalSensitiveDetector()
        result = det.detect("Key block:\n-----BEGIN PRIVATE KEY-----")
        keys = [d for d in result.detections if d.label == "private_key"]
        assert len(keys) == 1

    def test_ssh_key_detection(self):
        from pardus_paylasim.clipboard.ai.local_detector import (
            LocalSensitiveDetector,
        )
        det = LocalSensitiveDetector()
        result = det.detect("ssh-rsa AAAAB3NzaC1yc2EAAAA user@host")
        keys = [d for d in result.detections if d.label == "ssh_key"]
        assert len(keys) >= 1

    def test_max_severity_kritik(self):
        from pardus_paylasim.clipboard.ai.local_detector import (
            LocalSensitiveDetector,
        )
        det = LocalSensitiveDetector()
        result = det.detect("TCKN: 10000000146 ve email: a@b.com")
        assert result.max_severity == "KRİTİK"

    def test_no_false_positive_for_clean_text(self):
        from pardus_paylasim.clipboard.ai.local_detector import (
            LocalSensitiveDetector,
        )
        det = LocalSensitiveDetector()
        result = det.detect("Bugün hava çok güzel, yarın da yağmur yağabilir.")
        assert not result.has_sensitive or all(
            d.severity in ("DÜŞÜK",) for d in result.detections
        )

    def test_mask_with_ai_works(self):
        from pardus_paylasim.clipboard.ai.local_detector import (
            LocalSensitiveDetector,
        )
        det = LocalSensitiveDetector()
        original = "Mail: ahmet@example.com"
        masked = det.mask_with_ai(original)
        assert "ahmet@example.com" not in masked
        assert "@example.com" in masked

    def test_inference_time_measured(self):
        from pardus_paylasim.clipboard.ai.local_detector import (
            LocalSensitiveDetector,
        )
        det = LocalSensitiveDetector()
        result = det.detect("TCKN: 10000000146")
        assert result.inference_time_ms >= 0

    def test_ai_handles_empty_input(self):
        from pardus_paylasim.clipboard.ai.local_detector import (
            LocalSensitiveDetector,
        )
        det = LocalSensitiveDetector()
        result = det.detect("")
        assert not result.has_sensitive
        assert result.detections == []


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


class TestDataChannelProtocol:
    """DataChannel kare gönderme/alma (entegrasyon)."""

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


class TestMaskWithAI:
    """mask_with_ai yönteminin maskeleme doğruluğu."""

    def test_mask_iban(self):
        from pardus_paylasim.clipboard.ai.local_detector import LocalSensitiveDetector
        det = LocalSensitiveDetector()
        masked = det.mask_with_ai("TR96 3456 7890 1234 5678 9012 34")
        assert masked != "TR96 3456 7890 1234 5678 9012 34"
        assert "TR96" in masked
        assert masked.endswith("34")

    def test_mask_email(self):
        from pardus_paylasim.clipboard.ai.local_detector import LocalSensitiveDetector
        det = LocalSensitiveDetector()
        masked = det.mask_with_ai("user@example.com")
        assert masked != "user@example.com"
        assert "@" in masked

    def test_mask_tckn(self):
        from pardus_paylasim.clipboard.ai.local_detector import LocalSensitiveDetector
        det = LocalSensitiveDetector()
        masked = det.mask_with_ai("TCKN: 10000000146")
        assert masked != "TCKN: 10000000146"

    def test_mask_credit_card(self):
        from pardus_paylasim.clipboard.ai.local_detector import LocalSensitiveDetector
        det = LocalSensitiveDetector()
        masked = det.mask_with_ai("Kart: 4532015112830366")
        assert masked != "Kart: 4532015112830366"

    def test_mask_multiple_types(self):
        from pardus_paylasim.clipboard.ai.local_detector import LocalSensitiveDetector
        det = LocalSensitiveDetector()
        text = "TCKN: 10000000146, IBAN: TR96 3456 7890 1234 5678 9012 34, mail: a@b.com"
        masked = det.mask_with_ai(text)
        assert text != masked
        assert "10000000146" not in masked
        assert "TR96" not in masked or "****" in masked

    def test_mask_no_sensitive(self):
        from pardus_paylasim.clipboard.ai.local_detector import LocalSensitiveDetector
        det = LocalSensitiveDetector()
        text = "Bu sadece sıradan bir metin."
        masked = det.mask_with_ai(text)
        assert masked == text


class TestAIResultFields:
    """AIResult veri yapısının alan doğruluğu."""

    def test_result_metadata(self):
        from pardus_paylasim.clipboard.ai.local_detector import LocalSensitiveDetector
        det = LocalSensitiveDetector()
        result = det.detect("TCKN: 10000000146")
        assert result.has_sensitive is True
        assert result.max_severity == "KRİTİK"
        assert result.inference_time_ms >= 0
        assert result.model_loaded is False
        assert len(result.detections) >= 1

    def test_detection_fields(self):
        from pardus_paylasim.clipboard.ai.local_detector import LocalSensitiveDetector
        det = LocalSensitiveDetector()
        result = det.detect("user@test.com")
        d = result.detections[0]
        assert d.text == "user@test.com"
        assert d.label == "email"
        assert d.confidence == 1.0
        assert d.method == "rule"
        assert d.severity == "ORTA"


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


class TestLocalDetectorAllLabels:
    """Tüm AI detector label'larının tespiti."""

    def test_all_builtin_labels(self):
        from pardus_paylasim.clipboard.ai.local_detector import LocalSensitiveDetector
        det = LocalSensitiveDetector()
        cases = [
            ("tckn", "10000000146"),
            ("credit_card", "4532015112830366"),
            ("iban_tr", "TR963456789012345678901234"),
            ("email", "user@example.com"),
            ("jwt", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHk0"),
        ]
        for label, value in cases:
            r = det.detect(value)
            found = [d for d in r.detections if d.label == label]
            assert len(found) >= 1, f"label '{label}' not detected for value '{value}'"

    def test_ip_severity_düşük(self):
        from pardus_paylasim.clipboard.ai.local_detector import LocalSensitiveDetector
        det = LocalSensitiveDetector()
        r = det.detect("192.168.1.1")
        if r.has_sensitive:
            ips = [d for d in r.detections if d.label == "ipv4"]
            if ips:
                assert ips[0].severity == "DÜŞÜK"


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
