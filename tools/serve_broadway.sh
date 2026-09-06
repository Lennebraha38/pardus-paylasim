#!/bin/bash
# Pardus Paylaşım — GERÇEK GTK arayüzünü telefon tarayıcısında göster
# (GTK Broadway backend; Termux:X11 GEREKTİRMEZ)
#
# Telefonda (Termux):
#   cd ~/pardus-paylasim && git pull && bash tools/serve_broadway.sh
# Sonra telefon tarayıcısında:  http://127.0.0.1:8085
#
# Çalışmazsa: ÇIKTININ TAMAMINI yapıştır (teşhis satırları dahildir).
set -e

echo "== 1/2 broadwayd kurulumu (proot Debian) =="
proot-distro login debian -- bash -c "
set -e
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends libgtk-4-bin curl procps
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
echo \"DIAG: sunucu binary = \$BW\"
\"\$BW\" --help 2>&1 | head -5 || true
setsid \"\$BW\" :5 </dev/null >/tmp/broadwayd.log 2>&1 &
sleep 2
echo 'DIAG: broadway islemleri:'
ps aux | grep '[b]roadwayd' || echo 'DIAG: islem YOK!'
echo 'DIAG: dinlenen portlar (8085 beklenir):'
(cat /proc/net/tcp /proc/net/tcp6 2>/dev/null | awk 'NR>1 {split(\$2,a,\":\"); print strtonum(\"0x\" a[2])}' | sort -un | tr '\n' ' '; echo) || true
for i in \$(seq 1 15); do
    CODE=\$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 http://127.0.0.1:8085/ || echo FAIL)
    echo \"DIAG: deneme \$i -> HTTP \$CODE\"
    if [ \"\$CODE\" = '200' ]; then
        echo 'broadwayd hazir (8085).'
        break
    fi
    sleep 1
    if [ \$i -eq 15 ]; then
        echo 'HATA: broadwayd cevap vermiyor. Log:'
        cat /tmp/broadwayd.log
        exit 1
    fi
done
export GDK_BACKEND=broadway
export BROADWAY_DISPLAY=:5
cd ~/pardus-paylasim
PYTHONPATH=src python3 -m pardus_paylasim.app"
