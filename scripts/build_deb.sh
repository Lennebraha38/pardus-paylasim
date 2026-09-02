#!/bin/bash
set -e

echo "Pardus Paylaşım DEB paketleme scripti başlatılıyor..."

# dpkg-buildpackage ile debian/ dizinindeki konfigürasyonlara göre paket oluşturuluyor.
# GPG imzalaması atlanıyor (-uc -us), çünkü CI/CD pipeline'da veya harici araçla yapılacak.
dpkg-buildpackage -uc -us -b

echo "DEB paketi bir üst dizinde oluşturuldu (../pardus-paylasim_*.deb)."
