"""
mDNS / Zeroconf Wi-Fi Device Discovery for Pardus Ecosystem.
Broadcasts _pardus-share._tcp.local. and discovers local network Pardus devices.
Compatible with both older and newer python-zeroconf API versions.
"""

import logging
import os
import socket
import threading
import time
from typing import Callable, Iterable, Optional

from pardus_paylasim import platform_info

logger = logging.getLogger(__name__)

# Simülasyon (sahte cihaz enjeksiyonu) yalnız bu env değişkeni "1" iken açılır.
# Prod'da KAPALI: zeroconf yoksa/çökerse hayalet peer üretmek yerine hata
# durumuna geçilir. Geçmişte fallback prod'a sahte 192.168.1.101 sızdırıyordu.
SIMULATE_ENV = "PARDUS_MDNS_SIMULATE"

SERVICE_VERSION = "1.0.0"

# Servis portları (TXT kayıtlarında yayınlanır; keşfeden taraf okur).
# Ekran = MJPEG HTTP(S); dosya = transfer; pano = clipboard_sync.
# Kontrol kanalı Faz 1'de açılacak → 0 = yok/yayınlanmaz.
DEFAULT_SCREEN_PORT = 52345
DEFAULT_FILE_PORT = 8900
DEFAULT_CLIP_PORT = 8901
DEFAULT_CONTROL_PORT = 0

# Yayınlanabilir yetenek anahtarları (TXT `*_share` bayraklarına eşlenir).
CAP_SCREEN = "screen"
CAP_FILE = "file"
CAP_CLIPBOARD = "clipboard"
CAP_CONTROL = "control"
DEFAULT_CAPABILITIES = frozenset({CAP_SCREEN, CAP_FILE, CAP_CLIPBOARD})


def _simulation_enabled() -> bool:
    """Simülasyon modu açık mı? (yalnız `PARDUS_MDNS_SIMULATE=1` ile)."""
    return os.environ.get(SIMULATE_ENV, "").strip() == "1"


# Determine zeroconf availability and API version
HAS_ZEROCONF = False
ZEROCONF_API_V2 = False  # New API (>= 0.39.0 uses ServiceInfo differently)

try:
    from zeroconf import (
        ServiceBrowser,
        ServiceInfo,
        ServiceListener,
        Zeroconf,
    )

    HAS_ZEROCONF = True
    # Check for newer API: ServiceInfo constructor accepts type_ keyword
    import inspect

    try:
        sig = inspect.signature(ServiceInfo.__init__)
        params = list(sig.parameters.keys())
        if "type_" in params:
            ZEROCONF_API_V2 = True
    except Exception as e:
        pass  # Fallback: try version-based detection
    if not ZEROCONF_API_V2:
        try:
            from zeroconf import __version__ as zc_version

            major_minor = tuple(int(x) for x in zc_version.split(".")[:2])
            if major_minor >= (0, 39):
                ZEROCONF_API_V2 = True
        except (ImportError, AttributeError, ValueError):
            pass  # If __version__ not available, default to old API
except ImportError:
    HAS_ZEROCONF = False

    class ServiceListener:
        pass

    class Zeroconf:
        pass

    class ServiceInfo:
        pass

    class ServiceBrowser:
        pass


class PardusZeroconfListener(ServiceListener):
    """Listener for mDNS service discovery events."""

    def __init__(
        self,
        callback: Callable[[str, str, int, dict], None],
        remove_callback: Callable[[str], None] = None,
    ):
        super().__init__()
        self.callback = callback
        self.remove_callback = remove_callback

    def remove_service(self, zeroconf: Zeroconf, type_: str, name: str):
        # Device went offline - notify to remove from list
        if self.remove_callback:
            try:
                name_clean = name.split(".")[0] if "." in name else name
                self.remove_callback(name_clean)
            except Exception as e:
                pass

    def add_service(self, zeroconf: Zeroconf, type_: str, name: str):
        info = zeroconf.get_service_info(type_, name)
        if info:
            self._report_service(info, name)

    def update_service(self, zeroconf: Zeroconf, type_: str, name: str):
        info = zeroconf.get_service_info(type_, name)
        if info:
            self._report_service(info, name)

    def _report_service(self, info: ServiceInfo, device_name: str = ""):
        """Extract service info and invoke callback with device details."""
        try:
            from socket import inet_ntoa

            # Parse addresses (different formats in different API versions)
            ip = "127.0.0.1"
            try:
                if hasattr(info, "parsed_addresses") and info.parsed_addresses:
                    ip = info.parsed_addresses[0]
            except Exception as e:
                pass
            try:
                if ip == "127.0.0.1" and hasattr(info, "addresses"):
                    addresses = info.addresses
                    if callable(addresses):
                        addresses = addresses()
                    if addresses and len(addresses) > 0:
                        ip = inet_ntoa(addresses[0])
            except Exception as e:
                pass
            try:
                if ip == "127.0.0.1" and hasattr(info, "address"):
                    addr = info.address
                    if callable(addr):
                        addr = addr()
                    if isinstance(addr, bytes):
                        ip = inet_ntoa(addr)
                    elif addr:
                        ip = str(addr)
            except Exception as e:
                pass

            # Get port safely (could be a callable in some API versions)
            port = DEFAULT_SCREEN_PORT
            try:
                p = info.port
                if callable(p):
                    p = p()
                if p:
                    port = int(p)
            except Exception as e:
                port = DEFAULT_SCREEN_PORT

            # Parse properties (bytes or strings depending on API version)
            properties = {}
            try:
                props = info.properties
                # In some zeroconf versions, properties is a method; in others it's a dict
                if callable(props):
                    props = props()
                if isinstance(props, dict) and props:
                    for k, v in props.items():
                        key = k.decode("utf-8", errors="ignore") if isinstance(k, bytes) else k
                        val = v.decode("utf-8", errors="ignore") if isinstance(v, bytes) else v
                        properties[key] = val
            except Exception as e:
                properties = {}

            # Extract device name from service name (remove domain suffix)
            name_clean = device_name.split(".")[0] if "." in device_name else device_name
            if not name_clean:
                name_clean = device_name or "Pardus Cihaz"
            self.callback(name_clean, ip, port, properties)

        except Exception as e:
            logger.warning("Servis bilgisi okunamadı: %s", e)


class MDNSDiscovery:
    """mDNS/Zeroconf service for Pardus device discovery."""

    SERVICE_TYPE = "_pardus-share._tcp.local."

    def __init__(
        self,
        device_name: str,
        port: int = DEFAULT_SCREEN_PORT,
        file_port: int = DEFAULT_FILE_PORT,
        clip_port: int = DEFAULT_CLIP_PORT,
        control_port: int = DEFAULT_CONTROL_PORT,
        capabilities: Optional[Iterable[str]] = None,
    ):
        self.device_name = device_name
        self.port = port  # Ekran (MJPEG) portu — SRV kaydının ana portu.
        self.file_port = file_port
        self.clip_port = clip_port
        self.control_port = control_port  # 0 = kontrol kanalı henüz yok.
        # Yayınlanan yetenekler; None → varsayılan (ekran+dosya+pano).
        self.capabilities = frozenset(
            capabilities if capabilities is not None else DEFAULT_CAPABILITIES
        )
        self.zeroconf: Optional[Zeroconf] = None
        self.browser: Optional[ServiceBrowser] = None
        self.running = False
        # Zeroconf başlatılamadığında dolar (UI hata durumu göstersin diye).
        self.error: Optional[str] = None
        self._on_device_found: Optional[Callable[[str, str, int, dict], None]] = None
        self._on_error: Optional[Callable[[str], None]] = None

    def _build_txt_props(self) -> dict:
        """
        Yayınlanacak TXT kayıt sözlüğü (gerçek OS + yetenek + portlar).

        OS `platform_info.current_os_label()`'dan gelir (hardcoded değil) →
        çapraz-platform (Pardus/Windows) doğru raporlar. Yetenekler `*_share`
        bayrakları olarak; her servis portu ayrı alan olarak yazılır ki
        keşfeden taraf tek ekran portuna sıkışmadan doğru servise bağlanabilsin.
        Kontrol portu yalnız kanal varsa (>0) yayınlanır.
        """
        props = {
            "os": platform_info.current_os_label(),
            "session": platform_info.session_type(),
            "device": self.device_name,
            "version": SERVICE_VERSION,
            "screen_share": "1" if CAP_SCREEN in self.capabilities else "0",
            "file_share": "1" if CAP_FILE in self.capabilities else "0",
            "clipboard_share": ("1" if CAP_CLIPBOARD in self.capabilities else "0"),
            "control_share": "1" if CAP_CONTROL in self.capabilities else "0",
            "screen_port": str(self.port),
            "file_port": str(self.file_port),
            "clip_port": str(self.clip_port),
        }
        if self.control_port > 0:
            props["control_port"] = str(self.control_port)
        # Cihaz parmak izi: karşı taraf kimliği doğrulayabilsin (TOFU).
        # Yoksa (cryptography eksik) alan atılır; keşif yine çalışır.
        try:
            from pardus_paylasim.auth.trust_store import own_fingerprint

            own_fp = own_fingerprint()
            if own_fp:
                props["fp"] = own_fp
        except Exception as e:
            pass
        return props

    def start_broadcasting_and_scanning(
        self,
        on_device_found: Callable[[str, str, int, dict], None],
        on_device_removed: Callable[[str], None] = None,
        on_error: Callable[[str], None] = None,
    ):
        """Start advertising this device and scanning for others."""
        self._on_device_found = on_device_found
        self._on_device_removed = on_device_removed
        self._on_error = on_error
        self.running = True
        self.error = None

        if HAS_ZEROCONF:
            try:
                self._start_zeroconf(on_device_found, on_device_removed)
            except Exception as e:
                self._handle_start_failure(f"Zeroconf başlatılamadı: {e}", on_device_found)
        elif _simulation_enabled():
            # Test/demo: zeroconf kurulu değil ama simülasyon açıkça istendi.
            self._start_simulation(on_device_found)
        else:
            self._handle_start_failure(
                "Zeroconf kütüphanesi kurulu değil (python3-zeroconf)",
                on_device_found,
            )

    def _start_zeroconf(
        self,
        on_device_found: Callable[[str, str, int, dict], None],
        on_device_removed: Callable[[str], None] = None,
    ):
        """Start real zeroconf broadcasting and discovery."""
        self.zeroconf = Zeroconf()
        hostname = socket.gethostname()
        local_ip = self._get_local_ip()

        service_name = f"{self.device_name}.{self.SERVICE_TYPE}"

        props = self._build_txt_props()

        try:
            if ZEROCONF_API_V2:
                # Newer API (zeroconf >= 0.39.0)
                info = ServiceInfo(
                    type_=self.SERVICE_TYPE,
                    name=service_name,
                    addresses=[socket.inet_aton(local_ip)],
                    port=self.port,
                    properties=props,
                    server=f"{hostname}.local.",
                )
            else:
                # Older API (< 0.39.0): ServiceInfo(type_, name, address, port, properties, server)
                info = ServiceInfo(
                    self.SERVICE_TYPE,
                    service_name,
                    address=socket.inet_aton(local_ip),
                    port=self.port,
                    properties={k.encode("utf-8"): v.encode("utf-8") for k, v in props.items()},
                    server=f"{hostname}.local.",
                )

            self.zeroconf.register_service(info)

            # Start browsing for other devices
            listener = PardusZeroconfListener(on_device_found, on_device_removed)
            self.browser = ServiceBrowser(self.zeroconf, self.SERVICE_TYPE, listener)

            logger.info("Zeroconf yayını başladı: %s @ %s:%s", service_name, local_ip, self.port)

        except Exception as e:
            self._handle_start_failure(f"Zeroconf kayıt/bulma hatası: {e}", on_device_found)

    def _handle_start_failure(
        self, message: str, on_device_found: Callable[[str, str, int, dict], None]
    ):
        """
        Zeroconf başlatma hatası: hata durumuna geç (sahte peer ÜRETME).

        Simülasyon yalnız `PARDUS_MDNS_SIMULATE=1` iken açılır — o zaman
        demo/test için yerel tarama taklidi yapılır. Aksi halde hata kaydedilir
        ve varsa `on_error` callback'i tetiklenir; DeviceManager'a hayalet
        cihaz enjekte edilmez.
        """
        if _simulation_enabled():
            logger.warning("%s — simülasyon modu (env açık)", message)
            self._start_simulation(on_device_found)
            return

        self.error = message
        logger.error("mDNS keşif hatası: %s", message)
        if self._on_error:
            try:
                self._on_error(message)
            except Exception as e:
                pass

    def _start_simulation(self, on_device_found: Callable[[str, str, int, dict], None]):
        """Simulated device discovery — YALNIZ test/demo (env-gated)."""
        threading.Thread(
            target=self._simulate_local_scan,
            args=(on_device_found,),
            daemon=True,
        ).start()

    def _get_local_ip(self) -> str:
        """Get local non-loopback IP address."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.settimeout(1)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            return ip
        except Exception as e:
            return "127.0.0.1"
        finally:
            try:
                s.close()
            except Exception as e:
                pass

    def _simulate_local_scan(self, on_device_found: Callable[[str, str, int, dict], None]):
        """
        Simulate discovering local Pardus devices — YALNIZ test/demo.

        `PARDUS_MDNS_SIMULATE=1` olmadan çağrılmaz. Yalnız BU cihazı raporlar;
        eskiden buradaki uydurma `192.168.1.101` XFCE peer'i prod'a sızıp
        hayalet cihaz gösteriyordu — kaldırıldı.
        """
        time.sleep(1)
        if not self.running:
            return

        local_ip = self._get_local_ip()

        # Report this device itself (gerçek TXT + keşif-tarafı `type` etiketi).
        props = self._build_txt_props()
        props["type"] = "Wi-Fi (mDNS)"
        on_device_found(self.device_name, local_ip, self.port, props)

    def stop(self):
        """Stop mDNS broadcasting and scanning."""
        self.running = False
        if HAS_ZEROCONF and self.zeroconf:
            try:
                self.zeroconf.close()
            except Exception as e:
                pass
            self.zeroconf = None
