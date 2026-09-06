#!/bin/bash
# Pardus Paylaşım — GERÇEK GTK arayüzünü telefon tarayıcısında göster
# (GTK Broadway backend; Termux:X11 GEREKTİRMEZ)
#
# Telefonda (Termux):
#   cd ~/pardus-paylasim && git pull && bash tools/serve_broadway.sh
# Sonra telefon tarayıcısında:  http://127.0.0.1:8085
set -e

echo "== 1/2 broadwayd kurulumu (proot Debian) =="
proot-distro login debian -- bash -c "
set -e
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends libgtk-4-bin
command -v gtk4-broadwayd || command -v broadwayd
echo BROADWAY-READY"

echo "== 2/2 broadwayd + uygulama (tek oturum) =="
echo "Telefon tarayicisinda ac:  http://127.0.0.1:8085"
echo "Durdurma: Ctrl+C"
proot-distro login debian -- bash -c "
set -e
pkill -f '[g]tk4-broadwayd :5' 2>/dev/null || true
sleep 1
if command -v gtk4-broadwayd >/dev/null 2>&1; then
    BW=gtk4-broadwayd
else
    BW=broadwayd
fi
echo \"Kullanilan sunucu: \$BW\"
setsid \"\$BW\" :5 </dev/null >/tmp/broadwayd.log 2>&1 &
for i in \$(seq 1 15); do
    if (echo > /dev/tcp/127.0.0.1/8085) 2>/dev/null; then
        echo 'broadwayd hazir (8085).'
        break
    fi
    sleep 1
    if [ \$i -eq 15 ]; then
        echo 'HATA: broadwayd 8085 portunu acamadi. Log:'
        cat /tmp/broadwayd.log
        exit 1
    fi
done
export GDK_BACKEND=broadway
export BROADWAY_DISPLAY=:5
cd ~/pardus-paylasim
PYTHONPATH=src python3 -m pardus_paylasim.app"
