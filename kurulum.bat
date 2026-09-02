@echo off
chcp 65001 > nul
title Pardus Güvenli Paylaşım - 1 Tıkla Kurulum
echo ==================================================================
echo   Pardus Güvenli Paylaşım ve Süreklilik Merkezi - Otomatik Kurulum
echo ==================================================================
echo.
echo [*] Gerekli dosyalar hazırlanıyor ve bağımlılıklar kontrol ediliyor...
python -m pip install -e . --no-warn-script-location 2>nul
echo.
echo [BAŞARILI] Kurulum tamamlandı!
echo Uygulamayı başlatmak için "baslat.bat" dosyasına çift tıklayabilirsiniz.
echo.
pause
