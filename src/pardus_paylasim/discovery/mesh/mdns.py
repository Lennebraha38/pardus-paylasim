"""Mesh eşleri için mDNS tabanlı otomatik keşif.

`_pardus-mesh._tcp.local.` servisini duyurur ve dinler; bulunan eşleri
`on_peer(ip, port, peer_id)` ile bildirir, kaybolanları
`on_peer_lost(peer_id)` ile düşer. Kendini (aynı peer_id) eleyer.

zeroconf kurulu değilse tüm metotlar güvenli no-op'tur (False döner);
böylece başsız/test ortamlarında içe aktarma ve yaşam döngüsü kırılmaz.
"""

import logging
import socket
import struct
import threading
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)

SERVICE_TYPE = "_pardus-mesh._tcp.local."
SERVICE_NAME_FMT = "pardus-mesh-{peer_id}._pardus-mesh._tcp.local."

try:
    from zeroconf import ServiceBrowser, ServiceInfo, ServiceListener, Zeroconf

    HAS_ZEROCONF = True
except ImportError:
    HAS_ZEROCONF = False


def build_service_name(peer_id: str) -> str:
    """Duyuru adı (nokta/boşluk temizlenir, mDNS'e uygun)."""
    safe = "".join(c if (c.isalnum() or c in "-_") else "-" for c in peer_id)[:32]
    return SERVICE_NAME_FMT.format(peer_id=safe or "anonim")


def encode_txt(peer_id: str) -> Dict[bytes, bytes]:
    return {b"peer_id": peer_id.encode("utf-8")}


def decode_peer_id(properties: Optional[Dict]) -> str:
    """zeroconf properties sözlüğünden peer_id çıkarır (bayt/str tolerant)."""
    if not properties:
        return ""
    raw = properties.get(b"peer_id", properties.get("peer_id", b""))
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return str(raw)


class _MeshListener:
    """Bulunan/kaybolan servisleri çözümleyip geri çağırır."""

    def __init__(self, zc, own_peer_id, on_peer, on_peer_lost):
        self._zc = zc
        self._own = own_peer_id
        self._on_peer = on_peer
        self._on_lost = on_peer_lost
        self._lock = threading.Lock()
        self._known: Dict[str, str] = {}

    def add_service(self, zc, type_, name):
        try:
            info = zc.get_service_info(type_, name)
        except Exception as e:
            logger.debug("mDNS çözümleme hatası: %s", e)
            return
        if info is None:
            return
        self._report(info)

    def remove_service(self, zc, type_, name):
        # İsimden peer_id türetilemezse sessiz geç (TXT zaten okunmuştu).
        with self._lock:
            for pid, svc_name in list(self._known.items()):
                if svc_name == name and self._on_lost:
                    try:
                        self._on_lost(pid)
                    except Exception as e:
                        logger.debug("on_peer_lost hatası: %s", e)
                    del self._known[pid]

    def update_service(self, zc, type_, name):
        self.add_service(zc, type_, name)

    def _report(self, info):
        peer_id = decode_peer_id(getattr(info, "properties", None))
        if not peer_id or peer_id == self._own:
            return
        addresses = getattr(info, "addresses", []) or []
        port = getattr(info, "port", 0) or 0
        if not addresses or not port:
            return
        try:
            ip = socket.inet_ntoa(addresses[0])
        except (OSError, struct.error):
            return
        with self._lock:
            self._known[peer_id] = getattr(info, "name", "")
        if self._on_peer:
            try:
                self._on_peer(ip, port, peer_id)
            except Exception as e:
                logger.debug("on_peer hatası: %s", e)


class MeshDiscovery:
    """mDNS duyuru + tarama yaşam döngüsü (tek nesne, start/stop)."""

    def __init__(self, peer_id, local_ip, mesh_port,
                 on_peer: Optional[Callable[[str, int, str], None]] = None,
                 on_peer_lost: Optional[Callable[[str], None]] = None):
        self.peer_id = peer_id
        self.local_ip = local_ip
        self.mesh_port = mesh_port
        self.on_peer = on_peer
        self.on_peer_lost = on_peer_lost
        self._lock = threading.Lock()
        self._zc = None
        self._browser = None
        self._info = None
        self._running = False

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    def start(self) -> bool:
        """Duyur + tara. zeroconf yoksa False (sessiz degrade)."""
        with self._lock:
            if self._running:
                return True
            if not HAS_ZEROCONF:
                logger.info("zeroconf yok; mesh keşfi kapalı (manuel eş eklenebilir).")
                return False
            try:
                addr = socket.inet_aton(self.local_ip)
            except OSError as e:
                logger.warning("Geçersiz yerel IP %r: %s", self.local_ip, e)
                return False
            name = build_service_name(self.peer_id)
            try:
                try:
                    info = ServiceInfo(
                        type_=SERVICE_TYPE, name=name,
                        addresses=[addr], port=self.mesh_port,
                        properties=encode_txt(self.peer_id),
                    )
                except TypeError:
                    info = ServiceInfo(
                        SERVICE_TYPE, name, addr, self.mesh_port,
                        properties=encode_txt(self.peer_id),
                    )
                zc = Zeroconf()
                zc.register_service(info)
                listener = _MeshListener(zc, self.peer_id, self.on_peer, self.on_peer_lost)
                browser = ServiceBrowser(zc, SERVICE_TYPE, listener)
            except Exception as e:
                logger.warning("mDNS keşfi başlatılamadı: %s", e)
                try:
                    zc.close()
                except Exception:
                    pass
                return False
            self._zc, self._browser, self._info = zc, browser, info
            self._running = True
            logger.info("Mesh mDNS keşfi başladı (%s).", name)
            return True

    def stop(self):
        with self._lock:
            self._running = False
            zc, browser, info = self._zc, self._browser, self._info
            self._zc = self._browser = self._info = None
        if zc is not None:
            try:
                if info is not None:
                    try:
                        zc.unregister_service(info)
                    except Exception as e:
                        logger.debug("unregister hatası: %s", e)
                try:
                    zc.close()
                except Exception as e:
                    logger.debug("zeroconf kapatma hatası: %s", e)
            except Exception as e:
                logger.debug("mDNS durdurma hatası: %s", e)
