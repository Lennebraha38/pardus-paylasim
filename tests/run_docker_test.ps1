Write-Host "1. .deb Paketi Derleniyor..."
python build_deb.py

Write-Host "2. Pardus Test İmajı Hazırlanıyor..."
docker build -t pardus-paylasim-test -f tests/docker/Dockerfile tests/docker

Write-Host "3. Container İçinde Testler Çalıştırılıyor..."
docker run --rm `
  -v "$pwd\pardus-paylasim.deb:/app/pardus-paylasim.deb" `
  -v "$pwd\tests:/app/project-tests:ro" `
  pardus-paylasim-test
