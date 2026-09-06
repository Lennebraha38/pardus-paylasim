#!/bin/bash
# Pardus Paylaşım — GERÇEK GTK arayüzünü telefon tarayıcısında göster
# (GTK Broadway backend; Termux:X11 GEREKTİRMEZ)
#
# Telefonda (Termux):
#   cd ~/pardus-paylasim && git pull && bash tools/serve_broadway.sh
# Sonra telefon tarayıcısında:  http://127.0.0.1:8085
set -e

echo "== 1/3 broadwayd kurulumu (proot Debian) =="
proot-distro login debian -- bash -c "
set -e
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends libgtk-4-bin 2>&1 | tail -1
echo BROADWAY-READY"

echo "== 2/3 broadwayd baslatiliyor (:5 -> http://127.0.0.1:8085) =="
pkill -f "broadwayd :5" 2>/dev/null || true
sleep 1
# broadwayd proot icinde calismali (GTK kutuphaneleri orada)
proot-distro login debian -- bash -c "nohup broadwayd :5 >/tmp/broadwayd.log 2>&1 &"
sleep 3

echo "== 3/3 uygulama baslatiliyor =="
echo "Telefon tarayicisinda ac:  http://127.0.0.1:8085"
echo "Durdurma: Ctrl+C (ardindan: pkill -f 'broadwayd :5')"
proot-distro login debian -- bash -c "
export GDK_BACKEND=broadway
export BROADWAY_DISPLAY=:5
cd ~/pardus-paylasim
PYTHONPATH=src python3 -m pardus_paylasim.app"
