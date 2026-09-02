@echo off
chcp 65001 > nul
title Pardus Güvenli Paylaşım Merkezi
set PYTHONPATH=src
python -m pardus_paylasim.app %*
if errorlevel 1 (
    echo.
    echo Uygulama kapatıldı.
    pause
)
