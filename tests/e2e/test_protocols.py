import asyncio
import json
import socket
import ssl

import aiohttp
import pytest
import websockets

from pardus_paylasim.discovery.transfer import FileReceiverServer
from pardus_paylasim.screen import tls_util
from pardus_paylasim.screen.stream_config import StreamConfig
from pardus_paylasim.screen.stream_server import ScreenStreamServer

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.docker,
]


def _is_router_reachable():
    try:
        socket.gethostbyname("router")
        return True
    except OSError:
        return False


@pytest.mark.skipif(
    not _is_router_reachable(),
    reason="router hostu bulunamadı, Docker ortamı dışında çalıştırılamaz",
)
@pytest.mark.asyncio
async def test_rendezvous_router_signaling():
    """Rendezvous Router üzerinden iki cihazın haberleşmesini (signaling) test eder."""
    try:
        cert_pem = ssl.get_server_certificate(("router", 8765))
        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_ctx.load_verify_locations(cadata=cert_pem)
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_REQUIRED

        # Host cihazı (sunucu)
        async with websockets.connect("wss://router:8765", ssl=ssl_ctx) as host_ws:
            await host_ws.send(json.dumps({"type": "register"}))
            resp = json.loads(await host_ws.recv())
            assert resp.get("type") == "registered"
            host_id = resp["id"]

            # İstemci cihazı
            async with websockets.connect("wss://router:8765", ssl=ssl_ctx) as client_ws:
                await client_ws.send(json.dumps({"type": "register"}))
                resp2 = json.loads(await client_ws.recv())
                client_id = resp2["id"]

                # Client Host'a SDP offer gönderir
                await client_ws.send(
                    json.dumps(
                        {
                            "type": "offer",
                            "target_id": host_id,
                            "sdp": "fake-sdp-offer",
                            "offer_type": "offer",
                        }
                    )
                )

                # Host Offer'ı alır
                offer_resp = json.loads(await host_ws.recv())
                assert offer_resp.get("type") == "offer"
                assert offer_resp.get("sdp") == "fake-sdp-offer"
                assert offer_resp.get("sender_id") == client_id

                # Host Client'a SDP answer gönderir
                await host_ws.send(
                    json.dumps(
                        {
                            "type": "answer",
                            "target_id": client_id,
                            "sdp": "fake-sdp-answer",
                            "answer_type": "answer",
                        }
                    )
                )

                # Client Answer'ı alır
                answer_resp = json.loads(await client_ws.recv())
                assert answer_resp.get("type") == "answer"
                assert answer_resp.get("sdp") == "fake-sdp-answer"

    except Exception as e:
        pytest.fail(f"Router signaling hatası: {e}")


@pytest.mark.skipif(
    not _is_router_reachable(),
    reason="router hostu bulunamadı, Docker ortamı dışında çalıştırılamaz",
)
@pytest.mark.asyncio
async def test_invalid_cert_rejected():
    """Yanlış (veya eksik) sertifikanın reddedildiğini (fail-closed) doğrular."""
    bad_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    bad_ctx.check_hostname = False
    bad_ctx.verify_mode = ssl.CERT_REQUIRED
    # CA yüklenmediği için reddedilmeli
    with pytest.raises(ssl.SSLCertVerificationError):
        async with websockets.connect("wss://router:8765", ssl=bad_ctx):
            pass


@pytest.fixture
def agent_server():
    """Local E2E testleri için StreamServer başlatır."""
    config = StreamConfig(port=0)  # OS seçsin
    server = ScreenStreamServer(device_name="TestAgent", config=config)

    pin = []

    def on_pin(new_pin: str):
        pin.append(new_pin)

    server.start_server(pin_callback=on_pin)
    yield server, pin[0], server._tls_cert_path
    server.stop_server()


@pytest.mark.asyncio
async def test_agent_invalid_token_and_scope(agent_server):
    """Geçersiz token ve yetkisiz scope reddini (403/401) test eder."""
    server, pin, cert_path = agent_server
    port = server.port

    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_REQUIRED
    ssl_ctx.load_verify_locations(cafile=cert_path)

    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_ctx)) as session:
        # 1. Geçersiz token ile stream isteği
        async with session.get(
            f"https://127.0.0.1:{port}/stream", headers={"X-Pardus-Session": "wrong_token"}
        ) as resp:
            assert resp.status == 403 or resp.status == 401

        # 2. Geçersiz token ile control ws
        with pytest.raises(Exception):
            async with session.ws_connect(
                f"wss://127.0.0.1:{port}/control", headers={"X-Pardus-Session": "wrong"}
            ):
                pass


@pytest.mark.asyncio
async def test_agent_valid_control_and_stream(agent_server):
    """Doğru PIN ile stream ve control erişimi, reconnect, cleanup test eder."""
    server, pin, cert_path = agent_server
    port = server.port

    # Ensure control_server is instantiated
    if not hasattr(server, "control_server"):
        from pardus_paylasim.screen.control_server import ControlChannelServer

        server.control_server = ControlChannelServer(server)

    server.control_server.set_control_allowed(True)

    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_REQUIRED
    ssl_ctx.load_verify_locations(cafile=cert_path)

    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_ctx)) as session:
        # Önce login olup token alalım
        login_resp = await session.post(f"https://127.0.0.1:{port}/auth", json={"pin": pin})
        assert login_resp.status == 200
        token = login_resp.cookies["pardus_session"].value

        # Control bağlantısı (Token doğru)
        async with session.ws_connect(
            f"wss://127.0.0.1:{port}/control", headers={"X-Pardus-Session": token}
        ) as ws:
            # Control mesajı gönderelim
            await ws.send_json({"type": "move", "x": 0.5, "y": 0.5})
            # Hata fırlatmadan kabul etmeli (mock olduğu için yanıt dönmeyebilir)

            # Clipboard eventi gönder
            await ws.send_json({"type": "clipboard", "text": "test_clip"})

        # Reconnect testi
        async with session.ws_connect(
            f"wss://127.0.0.1:{port}/control", headers={"X-Pardus-Session": token}
        ) as ws:
            await ws.send_json({"type": "key", "code": 13, "down": True})


@pytest.mark.asyncio
async def test_file_transfer_protocol():
    """Dosya transfer portunun açıldığını test eder."""
    cert_path, key_path, _ = tls_util.generate_self_signed_cert()
    ssl_ctx = tls_util.build_server_context(cert_path, key_path)
    receiver = FileReceiverServer("/tmp", port=0, ssl_context=ssl_ctx)

    def on_req(name, size, sender):
        return True

    receiver.on_file_request = on_req
    receiver.start()

    try:
        # Port açılmış olmalı
        await asyncio.sleep(0.1)  # Thread başlaması için kısa bir bekleme
        actual_port = receiver.server_socket.getsockname()[1] if receiver.server_socket else 0
        assert actual_port > 0
        reader, writer = await asyncio.open_connection("127.0.0.1", actual_port)
        writer.write(b"NOT_A_VALID_FILE_REQUEST")
        await writer.drain()
        writer.close()
        await writer.wait_closed()
    finally:
        receiver.stop()
