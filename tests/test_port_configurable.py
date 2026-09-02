"""
0.11 — Port uçtan uca yapılandırılabilir: hardcoded 52345 kalkar.

Sunucunun gerçek dinlediği port config'ten (GSettings/JSON) türetilir. UI
katmanı bu portu `ScreenShareViewHandler.host_port` üzerinden yüzeye çıkarır;
istemci API'leri ve mDNS fallback'i sihirli sabit yerine ortak `DEFAULT_PORT`
sabitini kullanır. Böylece varsayılan dışı bir port yapılandırıldığında
gösterilen adres gerçek portla eşleşir.
"""

import inspect
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from pardus_paylasim.discovery import mdns_discovery
from pardus_paylasim.screen.stream_client import ScreenStreamClient
from pardus_paylasim.screen.stream_config import DEFAULT_PORT
from pardus_paylasim.screen.stream_server import ScreenStreamServer
from pardus_paylasim.ui.screen_share_view import ScreenShareViewHandler


class TestHostPortSurface(unittest.TestCase):
    """`host_port` sunucunun gerçek portunu yüzeye çıkarır."""

    def test_default_host_port_matches_server(self):
        # Arrange / Act
        handler = ScreenShareViewHandler()
        # Assert: property doğrudan server.port'u yansıtır.
        self.assertEqual(handler.host_port, handler.server.port)

    def test_default_host_port_is_default_constant(self):
        # Config override'ı yoksa varsayılan port DEFAULT_PORT olmalı.
        handler = ScreenShareViewHandler()
        self.assertEqual(handler.host_port, DEFAULT_PORT)

    def test_host_port_reflects_configured_port(self):
        # Sunucu farklı porta kurulduğunda handler bunu yüzeye çıkarır.
        handler = ScreenShareViewHandler()
        handler.server = ScreenStreamServer(port=59999)
        self.assertEqual(handler.host_port, 59999)


class TestServerPortOverride(unittest.TestCase):
    """Açık `port` kwarg'ı config portunu ezer (geriye-uyum)."""

    def test_explicit_port_overrides_config(self):
        server = ScreenStreamServer(port=51000)
        self.assertEqual(server.port, 51000)

    def test_no_port_uses_config_default(self):
        # port verilmezse config'ten gelir; test ortamında varsayılan.
        server = ScreenStreamServer()
        self.assertEqual(server.port, DEFAULT_PORT)


class TestClientDefaultsUseConstant(unittest.TestCase):
    """İstemci API imzaları sihirli 52345 yerine DEFAULT_PORT kullanır."""

    def test_target_port_default(self):
        client = ScreenStreamClient()
        self.assertEqual(client.target_port, DEFAULT_PORT)

    def test_public_api_port_defaults_match_constant(self):
        # request_pin / get_server_info / ping_server / connect_to_stream
        for name in (
            "request_pin",
            "get_server_info",
            "ping_server",
            "connect_to_stream",
        ):
            sig = inspect.signature(getattr(ScreenStreamClient, name))
            self.assertEqual(
                sig.parameters["port"].default,
                DEFAULT_PORT,
                f"{name}.port varsayılanı DEFAULT_PORT olmalı",
            )


class TestMdnsFallbackConstant(unittest.TestCase):
    """mDNS port fallback'i sihirli sabit değil, modül sabiti kullanır."""

    def test_screen_port_constant_matches_default(self):
        self.assertEqual(mdns_discovery.DEFAULT_SCREEN_PORT, DEFAULT_PORT)


if __name__ == "__main__":
    unittest.main()
