"""
Mesh, WebRTC ve Asenkron Transfer modülleri için basit testler.
pytest gerekmez, doğrudan python3 ile çalıştırılabilir.
"""

import os
import sys
import time
import threading
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def test_mesh():
    print("\n--- MESH NETWORK ---")
    from pardus_paylasim.discovery.mesh.mesh_network import (
        MeshProtocol, MeshNode, MeshPeer,
        CHUNK_SIZE, MAX_RELAY_HOPS, FRAG_DATA,
    )

    packed = MeshProtocol.pack_fragment(
        FRAG_DATA, "abc12345", 5, 10, b"hello", "peer1", 2, "h" * 32
    )
    parsed = MeshProtocol.unpack_fragment(packed)
    assert parsed is not None
    assert parsed["data"] == b"hello"
    assert parsed["chunk_index"] == 5
    assert parsed["hop_count"] == 2
    print("  pack/unpack: PASS")

    assert MeshProtocol.unpack_fragment(b"NOPE" + b"\x00" * 200) is None
    print("  invalid magic rejected: PASS")

    assert MeshProtocol.unpack_fragment(b"\x00" * 10) is None
    print("  truncated rejected: PASS")

    node = MeshNode("test", "127.0.0.1", mesh_port=18920)
    try:
        node.start()
        time.sleep(0.1)
        assert node._running
    finally:
        node.stop()
    assert node._running is False
    assert node._server is None
    print("  node start/stop: PASS")

    node2 = MeshNode("n2", "127.0.0.1", mesh_port=18921)
    p = MeshPeer(id="p1", ip="127.0.0.1", port=18921)
    node2.add_peer(p)
    assert "p1" in node2.peers
    node2.remove_peer("p1")
    assert "p1" not in node2.peers
    print("  peer add/remove: PASS")

    assert 32 * 1024 <= CHUNK_SIZE <= 1024 * 1024
    assert 1 <= MAX_RELAY_HOPS <= 5
    print("  constants valid: PASS")


def test_webrtc():
    print("\n--- WEBRTC DATA CHANNEL ---")
    import json as _json
    from pardus_paylasim.screen.webrtc.data_channel import (
        SDPMessage, DataChannel, WebRTCScreenNode, WebRTCScreenSession,
    )

    offer = _json.loads(SDPMessage.create_offer("sid1", {"codecs": ["jpeg"]}))
    assert offer["type"] == "offer"
    assert offer["session_id"] == "sid1"
    print("  SDP offer: PASS")

    answer = _json.loads(SDPMessage.create_answer("sid2", {}))
    assert answer["type"] == "answer"
    print("  SDP answer: PASS")

    ice = _json.loads(SDPMessage.create_ice_candidate("s3", "192.168.1.1", 8921))
    assert ice["type"] == "ice"
    assert ice["candidate"]["ip"] == "192.168.1.1"
    print("  ICE candidate: PASS")

    sess = WebRTCScreenSession("s1", "p1", is_offerer=True)
    assert sess.session_id == "s1"
    assert sess.is_offerer is True
    print("  session creation: PASS")

    sess.state.frames_sent = 10
    sess.state.bytes_sent = 5000
    assert sess.state.frames_sent == 10
    print("  state tracking: PASS")

    node = WebRTCScreenNode("test_peer", port=18922)
    try:
        node.start()
        time.sleep(0.1)
        assert node._running
    finally:
        node.stop()
    assert node._running is False
    assert node._server_socket is None
    print("  node lifecycle: PASS")

    node2 = WebRTCScreenNode("p1", port=18923)
    sess2 = node2.create_session("remote")
    assert sess2.peer_id == "remote"
    assert sess2.is_offerer is True
    print("  create session: PASS")

    node3 = WebRTCScreenNode("p1", port=18924)
    offer = SDPMessage.create_offer("test_sid", {"codecs": ["jpeg"]})
    sess3 = node3.handle_sdp(offer)
    assert sess3 is not None
    assert sess3.session_id == "test_sid"
    print("  handle SDP offer: PASS")


def test_async_transfer():
    print("\n--- ASYNC TRANSFER ---")
    from pardus_paylasim.discovery.async_transfer.manager import (
        AsyncTransfer, AsyncTransferStore, AsyncTransferManager,
    )

    tmp = tempfile.mkdtemp()
    store = AsyncTransferStore(db_path=os.path.join(tmp, "test.db"))

    t1 = AsyncTransfer(
        id="t1", file_name="a.txt", file_size=100, file_hash="h1",
        sender_id="s1", sender_name="Ahmet", receiver_id="r1",
        status="pending", file_path="/tmp/a.txt",
    )
    assert store.queue_transfer(t1) is True
    print("  queue transfer: PASS")

    pending = store.get_pending_for_receiver("r1")
    assert len(pending) == 1
    assert pending[0].id == "t1"
    print("  get pending: PASS")

    store.mark_delivered("t1")
    assert len(store.get_pending_for_receiver("r1")) == 0
    print("  mark delivered: PASS")

    t2 = AsyncTransfer(
        id="t2", file_name="b.txt", file_size=200, file_hash="h2",
        sender_id="s1", sender_name="Ahmet", receiver_id="r1",
        status="pending", file_path="/tmp/b.txt",
    )
    store.queue_transfer(t2)
    store.cancel_transfer("t2")
    assert len(store.get_pending_for_receiver("r1")) == 0
    print("  cancel: PASS")

    t3 = AsyncTransfer(
        id="t3", file_name="c.txt", file_size=300, file_hash="samehash",
        sender_id="s1", sender_name="A", receiver_id="r2",
        status="pending", file_path="/tmp/c.txt",
    )
    store.queue_transfer(t3)
    found = store.get_transfer_by_hash("samehash")
    assert found is not None
    print("  dedup by hash: PASS")

    history = store.get_history("t1")
    assert len(history) > 0
    assert history[0]["type"] in ("queued", "delivered")
    print("  history logging: PASS")

    store2 = AsyncTransferStore(db_path=os.path.join(tmp, "mgr.db"))
    mgr = AsyncTransferManager(
        device_id="local", device_name="Test",
        store=store2, on_transfer_ready=None,
    )
    fpath = os.path.join(tmp, "test.txt")
    with open(fpath, "w") as f:
        f.write("hello world")

    tid = mgr.queue_offline(fpath, "remote1", "Remote")
    assert tid is not None
    assert len(store2.get_pending_for_receiver("remote1")) == 1
    print("  manager queue: PASS")

    delivered = mgr.check_pending_for("remote1")
    assert len(delivered) == 1
    assert delivered[0].file_name == "test.txt"
    print("  manager check pending: PASS")


if __name__ == "__main__":
    test_mesh()
    test_webrtc()
    test_async_transfer()
    print("\n" + "=" * 40)
    print("ALL MODULE TESTS: PASS")
    print("=" * 40)
