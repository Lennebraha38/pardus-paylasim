"""
GTK4 Mesh Network View Controller and Component.
Manages P2P Mesh node activation, peer table, and multi-hop relay metrics.
"""

from dataclasses import dataclass
from typing import Any

from pardus_paylasim.discovery.mesh.mesh_network import MeshNode


@dataclass(frozen=True)
class MeshPeerInfo:
    peer_id: str
    ip: str
    port: int
    hops: int = 1
    is_direct: bool = True


class MeshViewHandler:
    """Controller for P2P Mesh Network operations."""

    def __init__(self, node: MeshNode | None = None):
        self.node = node

    def ensure_node(
        self,
        peer_id: str = "local_node",
        local_ip: str = "0.0.0.0",  # noqa: S104
        port: int = 8920,
    ) -> MeshNode:
        if self.node is None:
            self.node = MeshNode(peer_id=peer_id, local_ip=local_ip, mesh_port=port)
        return self.node

    def add_peer(self, ip: str, port: int) -> bool:
        if self.node is None:
            return False
        return self.node.add_peer(ip, port)

    def get_peers(self) -> list[MeshPeerInfo]:
        if self.node is None:
            return []
        res = []
        for peer_id, addr in getattr(self.node, "peers", {}).items():
            if isinstance(addr, tuple) and len(addr) >= 2:
                res.append(MeshPeerInfo(peer_id=peer_id, ip=addr[0], port=addr[1]))
            elif isinstance(addr, str) and ":" in addr:
                ip, port_s = addr.split(":", 1)
                res.append(MeshPeerInfo(peer_id=peer_id, ip=ip, port=int(port_s)))
        return res

    def get_stats(self) -> dict[str, int]:
        if self.node is None:
            return {"peers_count": 0, "active": 0}
        return {
            "peers_count": len(getattr(self.node, "peers", {})),
            "active": 1 if getattr(self.node, "running", False) else 0,
        }


class MeshViewComponent:
    """GTK4 Mesh Görünüm Bileşeni."""

    def __init__(self, handler: MeshViewHandler | None = None):
        self.handler = handler or MeshViewHandler()
        self.container: Any = None
        self.is_active = False

    def toggle_mesh(self, active: bool) -> bool:
        node = self.handler.ensure_node()
        if active:
            node.start()
            self.is_active = True
        else:
            node.stop()
            self.is_active = False
        return self.is_active
