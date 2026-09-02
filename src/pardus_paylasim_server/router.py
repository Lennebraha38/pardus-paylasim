import asyncio
import json
import logging
import random

import websockets

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Router")

# Aktif cihazlar: id -> websocket
devices = {}


def generate_id():
    while True:
        candidate = str(random.randint(100000000, 999999999))
        if candidate not in devices:
            return candidate


async def handler(websocket, path=None):
    device_id = None
    try:
        async for message in websocket:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "register":
                device_id = generate_id()
                devices[device_id] = websocket
                await websocket.send(json.dumps({"type": "registered", "id": device_id}))
                logger.info(f"Cihaz kaydedildi: {device_id}")

            elif msg_type == "offer":
                # İstemciden Host'a WebRTC SDP teklifi
                target_id = data.get("target_id")
                if target_id in devices:
                    await devices[target_id].send(
                        json.dumps(
                            {
                                "type": "offer",
                                "sdp": data.get("sdp"),
                                "offer_type": data.get("offer_type"),
                                "monitor_index": data.get("monitor_index", 0),
                                "sender_id": device_id,
                            }
                        )
                    )
                else:
                    if websocket:
                        await websocket.send(
                            json.dumps({"type": "error", "message": "Target not found"})
                        )

            elif msg_type == "answer":
                # Host'tan İstemciye cevap
                target_id = data.get("target_id")
                if target_id in devices:
                    await devices[target_id].send(
                        json.dumps(
                            {
                                "type": "answer",
                                "sdp": data.get("sdp"),
                                "answer_type": data.get("answer_type"),
                            }
                        )
                    )

    except websockets.ConnectionClosed:
        pass
    finally:
        if device_id and device_id in devices:
            del devices[device_id]
            logger.info(f"Cihaz ayrıldı: {device_id}")


async def main():
    logger.info("Rendezvous Router başlatılıyor (wss://0.0.0.0:8765)")

    # Geliştirme için fallback (kendi kendini imzalayan sertifika)
    import ssl

    try:
        from pardus_paylasim.screen.tls_util import build_server_context, generate_self_signed_cert

        cert_pem, key_pem, _ = generate_self_signed_cert()
        ssl_context = build_server_context(cert_pem, key_pem)
    except ImportError:
        logger.warning("pardus_paylasim modülü bulunamadı, varsayılan SSL bağlamı oluşturuluyor...")
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.check_hostname = False
        # Geçerli bir sertifika anahtarı olmadığı için WSS başlatılamayabilir,
        # ancak konsept olarak SSL_context atanıyor.
        # Üretim ortamında gerçek sertifika yüklenmelidir.

    async with websockets.serve(handler, "0.0.0.0", 8765, ssl=ssl_context):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
