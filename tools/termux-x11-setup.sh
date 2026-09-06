#!/bin/bash
# Pardus Paylaşım — Termux:X11 + proot Debian ile GERÇEK GTK4 arayüzü
#
# ÖN KOŞUL (telefonda, bir kez):
#   1. Termux:X11 APK'sını kur: https://github.com/termux/termux-x11/releases
#   2. Termux'u açıp bu betiği çalıştır:  bash tools/termux-x11-setup.sh
#
# Betik; Debian proot kurar, GTK4 + libadwaita + Python bağımlılıklarını
# yükler, repoyu klonlar ve uygulamayı Termux:X11 ekranına açar.

set -e

echo "== 1/5 Termux paketleri =="
pkg update -y
pkg install -y x11-repo proot-distro git termux-x11

echo "== 2/5 Debian proot =="
if proot-distro login debian -- true >/dev/null 2>&1; then
    echo "Debian zaten kurulu, atlanıyor."
else
    proot-distro install debian
fi

echo "== 3/5 Debian içi: GTK4 + Python bağımlılıkları =="
proot-distro login debian -- bash -c "
set -e
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3 python3-gi python3-cryptography python3-pip git \
    gir1.2-gtk-4.0 gir1.2-adw-1 \
    libgtk-4-1 libadwaita-1-0
python3 -m pip install --break-system-packages -q zeroconf qrcode 2>/dev/null || \
    pip3 install -q zeroconf qrcode
echo DEBIAN-READY"

echo "== 4/5 Repo =="
proot-distro login debian -- bash -c "
if [ ! -d ~/pardus-paylasim ]; then
    git clone https://github.com/Lennebraha38/pardus-paylasim.git ~/pardus-paylasim
else
    cd ~/pardus-paylasim && git pull --ff-only || true
fi"

echo "== 5/5 X sunucusu + uygulama =="
# Eski kalmış X sunucusu varsa kapat, :0'ı Termux tarafında başlat.
pkill -f "termux-x11 :0" 2>/dev/null || true
termux-x11 :0 &
sleep 3
if [ ! -S /tmp/.X11-unix/X0 ] && [ ! -S "$PREFIX/tmp/.X11-unix/X0" ]; then
    echo "UYARI: X soketi bulunamadı. Termux:X11 uygulamasını manuel açıp tekrar dene."
fi
echo "Termux:X11 uygulamasını ŞİMDİ aç (Display 0). Uygulama 5 sn sonra başlıyor..."
sleep 5

proot-distro login debian -- bash -c "
export DISPLAY=:0
export GDK_BACKEND=x11
X11_DIR=/data/data/com.termux/files/usr/tmp/.X11-unix
if [ -S \"\$X11_DIR/X0\" ]; then
    mkdir -p /tmp/.X11-unix
    ln -sfn \"\$X11_DIR/X0\" /tmp/.X11-unix/X0
    echo 'X soketi baglandi.'
else
    echo 'UYARI: X0 soketi yok; Termux:X11 uygulamasini acip tekrar dene.'
fi
cd ~/pardus-paylasim
PYTHONPATH=src python3 -m pardus_paylasim.app"
