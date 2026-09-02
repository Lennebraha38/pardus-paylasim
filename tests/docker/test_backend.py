import time

import pytest

from pardus_paylasim.config import AppConfig
from pardus_paylasim.discovery.transfer import FileReceiverServer, FileSender

pytestmark = pytest.mark.docker


def test_config_save_load():
    config = AppConfig()
    config.set("test_key", "12345")

    # Reload from file to ensure it's saved
    config2 = AppConfig()
    config2.load()
    assert config2.get("test_key") == "12345"


def test_file_transfer_normal(tmp_path):
    from pardus_paylasim.screen import tls_util

    cert, key, _ = tls_util.generate_self_signed_cert()
    server_ctx = tls_util.build_server_context(cert, key)
    client_ctx = tls_util.build_client_context(cert)

    download_dir = tmp_path / "downloads"
    download_dir.mkdir()

    # Start receiver
    receiver = FileReceiverServer(str(download_dir), port=8901, ssl_context=server_ctx)

    received_files = []

    def on_recv(path):
        received_files.append(path)

    receiver.on_file_received = on_recv
    receiver.on_file_request = lambda name, size, ip: True
    receiver.start()

    time.sleep(1)  # wait for bind

    # Create test file
    test_file = tmp_path / "test_normal.txt"
    test_file.write_text("Hello Pardus Normal Transfer!")

    sender = FileSender("127.0.0.1", 8901)
    sender.ssl_context = client_ctx
    sender.send_file(str(test_file))

    time.sleep(2)  # wait for receive
    receiver.stop()

    assert len(received_files) == 1
    assert "test_normal.txt" in received_files[0]

    with open(received_files[0], "r") as f:
        content = f.read()
    assert content == "Hello Pardus Normal Transfer!"


def test_file_transfer_secret(tmp_path):
    from pardus_paylasim.screen import tls_util

    cert, key, _ = tls_util.generate_self_signed_cert()
    server_ctx = tls_util.build_server_context(cert, key)
    client_ctx = tls_util.build_client_context(cert)

    download_dir = tmp_path / "secret_downloads"
    download_dir.mkdir()

    receiver = FileReceiverServer(str(download_dir), port=8902, ssl_context=server_ctx)

    received_files = []

    def on_recv(path):
        received_files.append(path)

    def on_pin_request(filename):
        return "999999"  # Test PIN

    receiver.on_file_received = on_recv
    receiver.get_secret_pin_callback = on_pin_request
    receiver.on_file_request = lambda name, size, ip: True
    receiver.start()

    time.sleep(1)

    test_file = tmp_path / "test_secret.txt"
    test_file.write_text("Hello Pardus Secret AES-256 Transfer!")

    sender = FileSender("127.0.0.1", 8902)
    sender.ssl_context = client_ctx
    sender.send_file(str(test_file), secret_pin="999999")

    time.sleep(2)
    receiver.stop()

    assert len(received_files) == 1
    with open(received_files[0], "r") as f:
        content = f.read()
    assert content == "Hello Pardus Secret AES-256 Transfer!"
