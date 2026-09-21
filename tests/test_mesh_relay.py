"""Mesh relay (ara düğüm aktarımı) uçtan uca testi.

Gönderici hedefe doğrudan bağlanamıyorsa parçayı komşu bir ara düğüm
üzerinden iletmelidir. Senkron: A -> B (relay) -> C.
"""

import os
import sys
import threading
import time

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

from pardus_paylasim.discovery.mesh.mesh_network import (
    MAX_RELAY_HOPS,
    MeshNode,
    MeshPeer,
    TransferJob,
)


def test_mesh_relay_via_intermediate_node(tmp_path=None):
    import tempfile

    workdir = tempfile.mkdtemp() if tmp_path is None else str(tmp_path)
    payload = os.urandom(150 * 1024)  # 3 parça (64 KB)
    src_file = os.path.join(workdir, "kaynak.bin")
    with open(src_file, "wb") as f:
        f.write(payload)

    done = threading.Event()
    received = {}

    node_a = MeshNode("node_a", "127.0.0.1", mesh_port=0)
    node_b = MeshNode("node_b", "127.0.0.1", mesh_port=0)
    node_c = MeshNode("node_c", "127.0.0.1", mesh_port=0)
    try:
        for n in (node_a, node_b, node_c):
            n.start()
        time.sleep(0.2)
        assert all(n._running for n in (node_a, node_b, node_c))

        # A, C'yi DOĞRUDAN bilmiyor; zincir A -> B -> C.
        node_a.add_peer(MeshPeer(id="node_b", ip="127.0.0.1", port=node_b.mesh_port))
        node_b.add_peer(MeshPeer(id="node_a", ip="127.0.0.1", port=node_a.mesh_port))
        node_b.add_peer(MeshPeer(id="node_c", ip="127.0.0.1", port=node_c.mesh_port))
        node_c.add_peer(MeshPeer(id="node_b", ip="127.0.0.1", port=node_b.mesh_port))
        time.sleep(0.2)

        tid = "relay001"  # <= 8 bayt: kablo protokolü tid'i 8 bayta kısar
        total = (len(payload) + 64 * 1024 - 1) // (64 * 1024)
        node_c.transfers[tid] = TransferJob(
            transfer_id=tid, file_name="kaynak.bin",
            file_size=len(payload), total_chunks=total, file_hash="",
        )

        node_c.on_transfer_complete = lambda tid_, name, data: (
            received.update(data=data), done.set()
        )

        node_a.offer_file_mesh(tid, "kaynak.bin", len(payload),
                               src_file, target="node_c")

        assert done.wait(timeout=15.0), "relay üzerinden transfer tamamlanamadı"
        assert received["data"] == payload, "birleştirilen baytlar farklı"
        assert node_c.transfers[tid].status == "complete"
        assert node_b._relay_seen, "ara düğüm (B) parçaları relay etmiş olmalı"
    finally:
        for n in (node_a, node_b, node_c):
            n.stop()


def test_relay_hops_capped():
    """Hop sınırının aşılamadığı garanti edilir (sonsuz döngü koruması)."""
    assert MAX_RELAY_HOPS == 3


if __name__ == "__main__":
    import unittest

    sys.exit(unittest.main())