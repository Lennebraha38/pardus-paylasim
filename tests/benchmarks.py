"""Performans benchmarkları — pytest-benchmark gerektirmez, saf time.perf_counter.

Çalıştırma:
    python3 tests/benchmarks.py

Çıktı: docs/BENCHMARKS.md tablosu için ham veriler.
"""

import os
import socket
import sys
import tempfile
import time

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))


def bench(fn, iterations=1000, warmup=50):
    for _ in range(warmup):
        fn()
    times = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    n = len(times)
    return {
        "min": times[0],
        "p50": times[n // 2],
        "p95": times[int(n * 0.95)],
        "max": times[-1],
        "mean": sum(times) / n,
        "ops": 1000.0 / (sum(times) / n) if sum(times) else 0,
    }


def main():
    from pardus_paylasim.discovery.mesh.mesh_network import FRAG_DATA, MeshProtocol
    from pardus_paylasim.clipboard.sensitive_masker import SensitiveMasker

    # Senaryo 1: pano maskeleme (tipik metin, ~150 karakter)
    sample = "Toplantı notu: Ahmet Yılmaz (a.yilmaz@ornek.com), TCKN 10000000146, tel 0532 123 45 67."

    # Senaryo 2: Mesh parça paketleme (64KB)
    chunk = os.urandom(64 * 1024)
    packed = MeshProtocol.pack_fragment(
        FRAG_DATA, "bench001", 0, 1, chunk, "peer_bench", hop_count=0,
        file_hash="b" * 32,
    )

    results = {}
    results["mask"] = bench(
        lambda: SensitiveMasker.mask_text(sample), iterations=2000)
    results["mesh_pack_64kb"] = bench(
        lambda: MeshProtocol.pack_fragment(
            FRAG_DATA, "bench001", 0, 1, chunk, "peer_bench",
            hop_count=0, file_hash="b" * 32),
        iterations=2000)
    results["mesh_unpack_64kb"] = bench(
        lambda: MeshProtocol.unpack_fragment(packed), iterations=2000)

    # Senaryo 3: SQLite kuyruk yazma (tmpfs)
    from pardus_paylasim.discovery.async_transfer.manager import (
        AsyncTransfer,
        AsyncTransferStore,
    )
    with tempfile.TemporaryDirectory() as tmp:
        store = AsyncTransferStore(db_path=os.path.join(tmp, "b.db"))
        counter = [0]

        def queue_one():
            counter[0] += 1
            store.queue_transfer(AsyncTransfer(
                id=f"b{counter[0]}", file_name="f.txt", file_size=10,
                file_hash=f"h{counter[0]}", sender_id="s", sender_name="S",
                receiver_id="r", status="pending", file_path="/tmp/f.txt"))

        results["sqlite_queue"] = bench(queue_one, iterations=500, warmup=20)

    # Senaryo 4: WebRTC frame gönderimi (30KB JPEG benzeri — kanal limiti 64KB)
    from pardus_paylasim.screen.webrtc.data_channel import DataChannel
    import threading
    frame = os.urandom(30 * 1024)

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    srv.settimeout(10.0)
    port = srv.getsockname()[1]

    def serve():
        try:
            conn, _ = srv.accept()
            dc = DataChannel(conn)
            dc.on_message = lambda d: None
            dc.start()
            time.sleep(1.5)
            dc.close()
        except OSError:
            pass
        finally:
            try:
                srv.close()
            except OSError:
                pass

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    cli = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    cli.connect(("127.0.0.1", port))
    cdc = DataChannel(cli)
    cdc.start()
    time.sleep(0.2)

    def send_frame():
        cdc.send(frame)

    results["webrtc_send_30kb"] = bench(send_frame, iterations=200, warmup=20)
    cdc.close()
    t.join(timeout=3.0)

    print(f"{'senaryo':<20} {'min':>9} {'p50':>9} {'p95':>9} {'mean':>9} {'ops/s':>10}")
    print("-" * 72)
    for name, r in results.items():
        print(f"{name:<20} {r['min']:>8.3f}m {r['p50']:>8.3f}m "
              f"{r['p95']:>8.3f}m {r['mean']:>8.3f}m {r['ops']:>9.0f}")

    with open(os.path.join(REPO_ROOT, "docs", "BENCH_RAW.txt"), "w") as f:
        for name, r in results.items():
            f.write(f"{name} min={r['min']:.3f} p50={r['p50']:.3f} "
                    f"p95={r['p95']:.3f} mean={r['mean']:.3f} ops={r['ops']:.0f}\n")
    print("\nHam veriler docs/BENCH_RAW.txt dosyasına yazıldı.")


if __name__ == "__main__":
    main()
