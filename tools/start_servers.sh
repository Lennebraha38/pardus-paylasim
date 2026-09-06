#!/bin/bash
# Pardus Paylaşım — sunucu başlatma
#
#   bash tools/start_servers.sh screen   # Ekran sunucusu (HTTPS, web viewer) :52345
#   bash tools/start_servers.sh signal   # Sinyal sunucusu (WSS rendezvous)  :8765
#   bash tools/start_servers.sh mesh     # Mesh düğümü (P2P)                 :8920
#
# Durdurma: Ctrl+C
set -e
cd "$(dirname "$0")/.." || exit 1
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"

cmd="${1:-screen}"
case "$cmd" in
  screen)
    echo "== Ekran sunucusu baslatiliyor (https://<IP>:52345) =="
    python3 -u -c "
from pardus_paylasim.screen.stream_server import ScreenStreamServer
try:
    srv = ScreenStreamServer()
    pin = srv.start_server()
except RuntimeError as e:
    print('BASLATILAMADI (fail-closed):', e)
    print('Cozum: python3-cryptography kurun (Debian: apt install python3-cryptography).')
    raise SystemExit(1)
print('PIN:', pin)
print('Web viewer: https://<bu-cihazin-IP>:52345/  (PIN ile gir)')
print('Durdurmak icin Ctrl+C')
try:
    import time
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    srv.stop_server()
    print('Durduruldu.')
"
    ;;
  signal)
    echo "== Sinyal sunucusu baslatiliyor (wss://0.0.0.0:8765) =="
    python3 src/pardus_paylasim_server/router.py
    ;;
  mesh)
    echo "== Mesh dugumu baslatiliyor (:8920, Ctrl+C ile durdur) =="
    python3 -u -c "
import time, uuid, socket
from pardus_paylasim.discovery.mesh.mesh_network import MeshNode
def lip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80)); ip = s.getsockname()[0]; s.close(); return ip
    except OSError:
        return '127.0.0.1'
n = MeshNode(peer_id=str(uuid.uuid4())[:8], local_ip=lip())
n.start()
print('Mesh calisiyor:', n.peer_id, n.local_ip, n.mesh_port)
try:
    while True: time.sleep(1)
except KeyboardInterrupt:
    n.stop(); print('Durduruldu.')
"
    ;;
  *)
    echo "Kullanim: bash tools/start_servers.sh [screen|signal|mesh]"
    exit 1
    ;;
esac
