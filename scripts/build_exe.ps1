$ErrorActionPreference = "Stop"
Write-Host "Pardus Paylasim EXE paketleme scripti baslatiliyor..."

# Bağımlılıkları kontrol et (uv üzerinden otomatik sağlanır)

# Dist dizinini temizle
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }

# Ana agent'ı paketle
uv run --with pyinstaller pyinstaller --name "pardus-paylasim-agent" --windowed --noconsole --version-file "version_info.txt" "src/pardus_paylasim_agent/agent.py"

Write-Host "EXE paketi dist/ dizininde olusturuldu."
