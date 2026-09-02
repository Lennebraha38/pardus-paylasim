import json
import os
import sys
import time

# Add src to path
sys.path.insert(0, "/app/src")

from pardus_paylasim.config import AppConfig
from pardus_paylasim.discovery.mdns_discovery import MDNSDiscovery
from pardus_paylasim.discovery.transfer import FileReceiverServer
from pardus_paylasim.screen.stream_server import ScreenStreamServer


def main():
    print("[Alice] Starting Alice (Host)...")

    # Configuration
    config = AppConfig()
    config.set("device_name", "Pardus-Alice")
    config.set("download_dir", "/tmp/alice_downloads")
    os.makedirs("/tmp/alice_downloads", exist_ok=True)

    # Onceki kosumdan kalan durum dosyalarini temizle (self-cleaning harness).
    for stale in ("/shared/pins.json", "/shared/received.json"):
        try:
            os.remove(stale)
        except FileNotFoundError:
            pass

    # 1. Start File Receiver Server
    def on_completed(file_path):
        print(f"[Alice] File transfer completed: {file_path}")
        # Bob'un uctan-uca dogrulamasi icin onay + md5 yaz.
        import hashlib

        try:
            with open(file_path, "rb") as fh:
                digest = hashlib.md5(fh.read()).hexdigest()
            with open("/shared/received.json", "w") as rf:
                json.dump({"path": file_path, "md5": digest}, rf)
            print(f"[Alice] Receipt written (md5={digest}).")
        except Exception as e:
            print(f"[Alice] Receipt write failed: {e}")

    file_port = 52345
    file_server = FileReceiverServer("/tmp/alice_downloads", port=file_port)
    file_server.on_file_received = on_completed
    file_server.start()
    print(f"[Alice] File server started on port {file_port}")

    # 2. Start Screen Server
    screen_server = ScreenStreamServer(device_name="Pardus-Alice", port=55555)
    pins = {}

    def on_screen_pin(pin):
        pins["screen_pin"] = pin
        print(f"[Alice] Screen PIN generated: {pin}")

    screen_server.start_server(pin_callback=on_screen_pin)
    print("[Alice] Screen server started on port 55555")

    # Generate file transfer PIN
    file_pin = "123456"  # Hardcoded for test since FileReceiverServer doesn't have pairing_mgr
    pins["file_pin"] = file_pin
    print(f"[Alice] File transfer PIN generated: {file_pin}")

    def get_pin(filename):
        return file_pin

    file_server.get_secret_pin_callback = get_pin

    # Write pins to shared volume for Bob to read
    with open("/shared/pins.json", "w") as f:
        json.dump(pins, f)

    # 3. Start mDNS Discovery
    scanner = MDNSDiscovery("Pardus-Alice", file_port)
    scanner.start_broadcasting_and_scanning(lambda n, i, p, inf: None)

    print("[Alice] Alice is fully running and broadcasting. Waiting for Bob...")

    # Keep running for a while
    for _ in range(60):
        time.sleep(1)
        # Check if file was received
        if os.path.exists("/tmp/alice_downloads/test_file.txt"):
            print("[Alice] Found received file! Transfer successful.")
            break

    # Cleanup
    scanner.stop()
    screen_server.stop_server()
    file_server.stop()

    print("[Alice] Shutting down.")


if __name__ == "__main__":
    main()
