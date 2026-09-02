import json
import os
import sys
import time

# Add src to path
sys.path.insert(0, "/app/src")

from pardus_paylasim.config import AppConfig
from pardus_paylasim.discovery.mdns_discovery import MDNSDiscovery
from pardus_paylasim.discovery.transfer import FileSender
from pardus_paylasim.screen.stream_client import ScreenStreamClient


def main():
    print("[Bob] Starting Bob (Client)...")

    config = AppConfig()
    config.set("device_name", "Pardus-Bob")

    # 1. Start mDNS Discovery
    discovered = {}

    def on_device(name, ip, port, info):
        print(f"[Bob] Discovered device: {name} at {ip}:{port}")
        discovered[name] = {"ip": ip, "port": port}

    scanner = MDNSDiscovery("Pardus-Bob", 52345)
    scanner.start_broadcasting_and_scanning(on_device)

    # Wait for Alice
    print("[Bob] Waiting for Alice to appear on network...")
    for _ in range(15):
        if "Pardus-Alice" in discovered:
            break
        time.sleep(1)

    if "Pardus-Alice" not in discovered:
        print("[Bob] FAILED: Could not discover Pardus-Alice via mDNS.")
        sys.exit(1)

    alice_ip = discovered["Pardus-Alice"]["ip"]
    alice_file_port = discovered["Pardus-Alice"]["port"]

    # Read PINs
    while not os.path.exists("/shared/pins.json"):
        time.sleep(1)

    with open("/shared/pins.json", "r") as f:
        pins = json.load(f)

    file_pin = pins.get("file_pin", "")
    print(f"[Bob] Acquired file PIN from Alice: {file_pin}")

    # 2. Test Screen Connection (gercek eslesme akisi)
    # PIN, istegi yapan client_ip'ye baglidir; bu yuzden Bob PIN'i pins.json'dan
    # degil dogrudan sunucudan ister (request_pin), sonra ayni PIN ile baglanir.
    print("\n[Bob] Connecting to Alice's Screen Stream...")
    screen_client = ScreenStreamClient()
    screen_pin = screen_client.request_pin(alice_ip, 55555)
    if not screen_pin:
        print("[Bob] FAILED: Could not obtain screen PIN from Alice.")
        sys.exit(1)
    print(f"[Bob] Screen PIN issued by Alice: {screen_pin}")

    frames = {"count": 0}

    def on_frame(_f):
        frames["count"] += 1

    connected = screen_client.connect_to_stream(alice_ip, 55555, screen_pin, on_frame)
    # connect_to_stream ping'e gore erken True doner; PIN dogrulamasi arka
    # thread'de olur. Gercek dogrulama: kisa bir sure sonra hala bagli miyiz?
    time.sleep(2)
    if connected and screen_client.is_connected:
        print(f"[Bob] SUCCESS: Screen stream authenticated (frames={frames['count']}).")
        screen_client.disconnect()
    else:
        print("[Bob] FAILED: Screen auth rejected (wrong PIN / 403).")
        sys.exit(1)

    # 3. Test File Transfer
    print("\n[Bob] Sending a test file to Alice...")
    payload = "Hello Alice! This is a test file from Bob via Pardus Share."
    with open("/tmp/test_file.txt", "w") as f:
        f.write(payload)

    sender = FileSender(alice_ip, alice_file_port)

    def progress(p):
        pass

    try:
        sender.send_file("/tmp/test_file.txt", file_pin, progress_callback=progress)
        print("[Bob] File sent, awaiting server-side confirmation...")
    except Exception as e:
        print(f"[Bob] FAILED: File send error: {e}")
        sys.exit(1)

    # Dogrulama: karsi taraf (Alice) dosyayi gercekten yazdi mi?
    # Alice /shared/received.json'a onay + md5 yazar (alice.py on_completed).
    received = None
    for _ in range(15):
        if os.path.exists("/shared/received.json"):
            with open("/shared/received.json", "r") as f:
                received = json.load(f)
            break
        time.sleep(1)

    if not received:
        print("[Bob] FAILED: Alice never confirmed file receipt.")
        sys.exit(1)

    import hashlib

    sent_md5 = hashlib.md5(payload.encode()).hexdigest()
    if received.get("md5") == sent_md5:
        print(f"[Bob] SUCCESS: File verified end-to-end (md5={sent_md5}).")
    else:
        print(f"[Bob] FAILED: md5 mismatch sent={sent_md5} got={received.get('md5')}")
        sys.exit(1)

    print("\n[Bob] All integration tests passed! Exiting.")


if __name__ == "__main__":
    main()
