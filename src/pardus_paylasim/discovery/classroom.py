"""Sınıf Modu: öğretmen orkestrasyonu için rol + toplu yayın mantığı.

Mimari not: merkezi sunucu YOKTUR (P2P). "Öğretmen" rolü bir yetkiden
çok kolaylaştırıcıdır: tahta listesi + tek tuşla yayın. Kimlik =
cihaz adı + parmak izi; merkezi hesap/kayıt yoktur (tasarım kararı).

Tahta tarafı ek iş gerektirmez: mesaj mevcut pano kanalından gelir,
dosya mevcut kabul akışından (güvenilirse otomatik), ekran mevcut
istemci kipiyle izlenir.
"""

import logging
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)

ROLE_NONE = ""
ROLE_TEACHER = "ogretmen"
ROLE_BOARD = "tahta"

ROLES = (ROLE_NONE, ROLE_TEACHER, ROLE_BOARD)

ROLE_LABELS = {
    ROLE_NONE: "Yok (bireysel kullanım)",
    ROLE_TEACHER: "Öğretmen (yayın yapar)",
    ROLE_BOARD: "Akıllı tahta (yayını alır)",
}


def broadcast_text(devices, text: str, timeout: float = 5.0,
                   progress_cb: Callable[[int, int], None] | None = None
                   ) -> dict[str, bool]:
    """Metni cihazlara paralel gönderir; {address: ok} döndürür.

    Her cihaz bağımsız iş parçacığında denenir; biri takılsa diğerleri
    etkilenmez. Boş metin gönderilmez (ValueError).
    """
    from pardus_paylasim.discovery.clipboard_sync import ClipboardSyncClient

    if not (text or "").strip():
        raise ValueError("Boş mesaj yayınlanamaz.")
    targets = [d for d in (devices or [])
               if getattr(d, "address", None)]
    results: dict[str, bool] = {}
    lock = threading.Lock()
    done = [0]

    def _one(dev):
        try:
            port = 8901
            try:
                service_ports = getattr(dev, "service_ports", None) or {}
                port = int(service_ports.get("clip_port", 8901))
            except (TypeError, ValueError):
                logger.debug("istisna yutuldu", exc_info=True)
            ClipboardSyncClient(dev.address, port).send_text(
                text, timeout=timeout)
            ok = True
        except Exception as e:
            logger.debug("yayın hatası %s: %s", getattr(dev, "address", "?"), e)
            ok = False
        with lock:
            results[dev.address] = ok
            done[0] += 1
            if progress_cb:
                try:
                    progress_cb(done[0], len(targets))
                except Exception:
                    logger.debug("istisna yutuldu", exc_info=True)

    threads = [threading.Thread(target=_one, args=(d,), daemon=True)
               for d in targets]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=max(timeout + 5.0, 10.0))
    with lock:
        for d in targets:
            results.setdefault(d.address, False)
    return results


def summarize_broadcast(results: dict[str, bool]) -> str:
    ok = sum(1 for v in results.values() if v)
    return f"{ok}/{len(results)} cihaza ulaştı"


def boards_only(devices) -> list:
    """Tahta olabilecek cihazlar (öğretmenin kendisi hariç tutulmaz;
    çağıran kendi IP'sini eler)."""
    return [d for d in (devices or []) if getattr(d, "address", None)]
