$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd_HHmmss")
$logDir = "$PWD\artifacts\verification\$timestamp"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = "$logDir\run_verify.log"

Start-Transcript -Path $logFile -Append

$clean = git status --porcelain
if ($clean) {
    Write-Error "Çalışma ağacı kirli (DIRTY). İmmutable verification sadece temiz bir commit üzerinden yapılabilir."
    Stop-Transcript
    exit 1
}

$commit = git rev-parse HEAD
Write-Host "Temiz commit doğrulandı: $commit. Docker imajı build ediliyor..."

$tempDir = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), "pardus-paylasim-verify-$commit")
if (Test-Path $tempDir) {
    Remove-Item -Recurse -Force $tempDir
}
New-Item -ItemType Directory -Force -Path $tempDir | Out-Null

Write-Host "Temiz git arşivi oluşturulup $tempDir içine açılıyor..."
git archive HEAD -o "$tempDir\archive.tar"
if ($LASTEXITCODE -ne 0) {
    Write-Error "git archive başarısız (exit $LASTEXITCODE). Kanıt üretilemedi."
    Stop-Transcript
    exit 1
}
tar -xf "$tempDir\archive.tar" -C $tempDir
if ($LASTEXITCODE -ne 0) {
    Write-Error "tar çıkarma başarısız (exit $LASTEXITCODE). Kanıt üretilemedi."
    Stop-Transcript
    exit 1
}

$exitCode = 0
Push-Location $tempDir
try {
    docker compose -f tests/docker/docker-compose.verify.yml build --build-arg GIT_COMMIT=$commit
    if ($LASTEXITCODE -ne 0) {
        # 'exit' try içinde finally'yi tetikler; Stop-Transcript orada yapilir.
        # Burada tekrar cagirmak "host is not transcribing" hatasi bastirir.
        Write-Error "Docker build başarısız."
        $exitCode = $LASTEXITCODE
        exit $exitCode
    }

    Write-Host "=== DOCKER IMAGE BİLGİSİ ==="
    Write-Host "Test edilen HEAD: $commit"
    $images = docker compose -f tests/docker/docker-compose.verify.yml config --images
    foreach ($img in $images) {
        Write-Host "Image: $img"
        Write-Host "Digest/ID:"
        docker image inspect $img --format '{{.Id}}'
        Write-Host "Labels (git_commit dahil):"
        docker image inspect $img --format '{{json .Config.Labels}}'
    }

    Write-Host "=== ORTAM BİLGİSİ ==="
    docker info | Select-String "Server Version|Operating System|OSType|Architecture"

    Write-Host "=== TESTLER ÇALIŞTIRILIYOR ==="
    # Compose çıktısını hem transcript'e bas hem de değişkene al (pytest özetini
    # ayrıştırmak için). Tee-Object bir cmdlet olduğu için native compose'un
    # $LASTEXITCODE değerini DEĞİŞTİRMEZ — çıkış kodu pipeline'dan hemen sonra alınır.
    docker compose -f tests/docker/docker-compose.verify.yml up --abort-on-container-exit --exit-code-from verify 2>&1 |
        Tee-Object -Variable composeOutput
    $exitCode = $LASTEXITCODE

    # --- pytest özet satırından gerçek sayıları çıkar ---------------------
    # -match yalnizca ILK eslesmeyi verir; ayni container icinde birden fazla
    # pytest calismasi olursa yanlis sayilar raporlanir. SON eslesmeyi
    # (nihai toplam) al: tum eslesmeleri tara, sonuncuyu kullan.
    $composeText = ($composeOutput | Out-String)
    $passed  = 0; $skipped = 0; $failed = 0; $errors = 0
    function Get-LastCount([string]$text, [string]$word) {
        $m = [regex]::Matches($text, "(\d+)\s+$word")
        if ($m.Count -gt 0) { return [int]$m[$m.Count - 1].Groups[1].Value }
        return 0
    }
    $passed  = Get-LastCount $composeText 'passed'
    $skipped = Get-LastCount $composeText 'skipped'
    $failed  = Get-LastCount $composeText 'failed'
    $errors  = Get-LastCount $composeText 'error'

    Write-Host "=== TEST ÖZETİ (GERÇEK SAYILAR) ==="
    Write-Host "Passed : $passed"
    Write-Host "Skipped: $skipped"
    Write-Host "Failed : $failed"
    Write-Host "Errors : $errors"
    Write-Host "Compose exit code: $exitCode"

    # --- Assert: körü körüne '397' zorunlu değil; exit=0 VE failed=0 VE error=0 ---
    if ($exitCode -ne 0 -or $failed -ne 0 -or $errors -ne 0) {
        Write-Error "DOĞRULAMA BAŞARISIZ: exit=$exitCode, failed=$failed, errors=$errors (passed=$passed, skipped=$skipped)"
        $exitCode = if ($exitCode -ne 0) { $exitCode } else { 1 }
    } else {
        Write-Host "DOĞRULAMA BAŞARILI: exit=0, failed=0, errors=0 (passed=$passed, skipped=$skipped)"
    }

    Write-Host "=== SONUÇ ==="
    Write-Host "EXIT CODE: $exitCode"
} finally {
    Pop-Location
    Remove-Item -Recurse -Force $tempDir
    Stop-Transcript
}
exit $exitCode
