import logging
import socket

logger = logging.getLogger("WOL")


def send_magic_packet(mac_address: str, ip_address: str = "255.255.255.255", port: int = 9):
    """Wake-on-LAN sihirli paketini gönderir."""
    try:
        # MAC adresini temizle ve byte array'e çevir
        mac = mac_address.replace(":", "").replace("-", "")
        if len(mac) != 12:
            raise ValueError("Geçersiz MAC adresi formatı")

        data = bytes.fromhex("FF" * 6 + mac * 16)

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(data, (ip_address, port))

        logger.info(f"WOL Magic Packet gönderildi -> {mac_address} ({ip_address}:{port})")
        return True
    except Exception as e:
        logger.error(f"WOL gönderilemedi: {e}")
        return False
