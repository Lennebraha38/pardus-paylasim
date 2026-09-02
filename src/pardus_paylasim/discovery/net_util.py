"""
Ağ yardımcı işlevleri.
"""

import socket
from typing import Optional


def recv_exact(conn: socket.socket, n: int) -> Optional[bytes]:
    """Tam n bayt okur; bağlantı erken kapanırsa None döner."""
    buf = bytearray()
    while len(buf) < n:
        try:
            chunk = conn.recv(min(65536, n - len(buf)))
            if not chunk:
                return None
            buf.extend(chunk)
        except OSError:
            return None
    return bytes(buf)
