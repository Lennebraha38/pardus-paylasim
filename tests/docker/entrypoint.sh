#!/bin/bash
set -e

if [ ! -f "/app/pardus-paylasim.deb" ]; then
    echo "[HATA] /app/pardus-paylasim.deb bulunamadı!"
    exit 1
fi

echo "[Pardus Test] Lintian (Debian Paket Analizi) Çalıştırılıyor..."
lintian --no-tag-display-limit /app/pardus-paylasim.deb || true

echo "[Pardus Test] Paket Kurulumu (dpkg/apt)..."
apt-get update
apt-get install -y /app/pardus-paylasim.deb

echo "[Pardus Test] Örnek Dosya Oluşturuluyor..."
echo "dummy file" > /tmp/dummy.pdf

echo "[Pardus Test] CLI Testi (Metadata Temizleme)..."
pardus-paylasim --clean /tmp/dummy.pdf --out /tmp/dummy_clean.pdf
file /tmp/dummy_clean.pdf

echo "[Pardus Test] Headless GUI Testi (Xvfb ve DBus ile başlatma)..."
export $(dbus-launch)
xvfb-run -a pardus-paylasim &
APP_PID=$!
sleep 3
if kill -0 $APP_PID 2>/dev/null; then
    echo "[Pardus Test] GTK arayüzü çökmeden başarıyla başlatıldı!"
    kill $APP_PID
else
    echo "[HATA] GTK arayüzü başlatılırken çöktü (Fatal Error)!"
    exit 1
fi

echo ""
echo "==========================================="
echo "⚙️ Pardus Backend Testleri Çalıştırılıyor (Config & P2P & AES)..."
echo "==========================================="
pytest /app/test_backend.py -v

echo ""
echo "==========================================="
echo "🧪 Pardus Turing Testleri (Fonksiyonel) Başlıyor..."
echo "==========================================="
export PYTHONPATH="/usr/lib/python3/dist-packages"
python3 /app/test_turing.py

# Platform-bagimsiz suite kurulu paket uzerinde (mount edilmisse).
# run_docker_test.sh /app/project-tests'e mount eder; yoksa atlanir.
if [ -d "/app/project-tests" ]; then
    echo ""
    echo "==========================================="
    echo "📦 Platform-bagimsiz suite (kurulu paket): pytest tests/"
    echo "==========================================="
    pytest /app/project-tests -v
fi

echo "[Pardus Test] Tüm testler BAŞARILI!"
