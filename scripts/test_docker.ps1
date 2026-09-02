$ErrorActionPreference = "Stop"
Write-Host "Pardus Paylasim Docker E2E Testleri Baslatiliyor..."

Write-Host "1. Docker konteynerlerini ayaga kaldir (build)..."
docker compose -f tests/docker/docker-compose.yml up --build -d

Write-Host "Konteynerlerin hazirlanmasi icin 5 saniye bekleniyor..."
Start-Sleep -Seconds 5

Write-Host "3. E2E Testlerini kos (Windows Host üzerinden Docker agina dogru veya container icinden)..."
# Burada testleri container icinden tetikliyoruz (router konteyneri python içerir)
docker compose -f tests/docker/docker-compose.yml exec -T windows-agent pytest tests/e2e/test_protocols.py -v

$test_exit = $LASTEXITCODE

Write-Host "4. Temizlik yapiliyor..."
docker compose -f tests/docker/docker-compose.yml down

if ($test_exit -eq 0) {
    Write-Host "Testler BASARIYLA TAMAMLANDI." -ForegroundColor Green
} else {
    Write-Host "Testler BASARISIZ." -ForegroundColor Red
}
exit $test_exit
