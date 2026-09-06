"""Uçtan uca (E2E) mesh veri düzlemi testi — gerçek TCP soketleri.

Docker yoksa bile çalışır: iki MeshNode aynı makinede farklı
loopback portlarında gerçek dosya transferi yapar.
"""

import os
import sys
import threading
import time

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))


def test_mesh_e2e_multi_chunk_file(tmp_path=None):
    """Gönderici gerçek dosyayı parçalara bölüp alıcıya iletir;
    alıcı birebir aynı baytları birleştirir."""
    import tempfile
    from pardus_paylasim.discovery.mesh.mesh_network import (
        MeshNode,
        MeshPeer,
        TransferJob,
    )

    workdir = tempfile.mkdtemp() if tmp_path is None else str(tmp_path)
    payload = os.urandom(200 * 1024)  # 200 KB -> 4 parça (64 KB)
    src_file = os.path.join(workdir, "kaynak.bin")
    with open(src_file, "wb") as f:
        f.write(payload)

    done = threading.Event()
    received = {}

    node_b = MeshNode("node_b", "127.0.0.1", mesh_port=0)
    node_a = MeshNode("node_a", "127.0.0.1", mesh_port=0)
    try:
        node_b.start()
        node_a.start()
        time.sleep(0.2)
        assert node_b._running and node_a._running

        node_a.add_peer(MeshPeer(id="node_b", ip="127.0.0.1",
                                 port=node_b.mesh_port))

        tid = "e2e0001"
        total = (len(payload) + 64 * 1024 - 1) // (64 * 1024)
        node_b.transfers[tid] = TransferJob(
            transfer_id=tid, file_name="kaynak.bin",
            file_size=len(payload), total_chunks=total, file_hash="",
        )

        def on_complete(tid_, name, data):
            received["data"] = data
            done.set()

        node_b.on_transfer_complete = on_complete

        node_a.offer_file_mesh(tid, "kaynak.bin", len(payload),
                               src_file, target="node_b")

        assert done.wait(timeout=15.0), "alıcı transferi tamamlayamadı"
        assert received["data"] == payload, "birleştirilen baytlar farklı"
        assert node_b.transfers[tid].status == "complete"
        print(f"E2E mesh: {len(payload)} bayt, {total} parça — PASS")
    finally:
        node_a.stop()
        node_b.stop()


if __name__ == "__main__":
    test_mesh_e2e_multi_chunk_file()
