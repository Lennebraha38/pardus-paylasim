# Faz 1: GÃ¼venlik SÄ±nÄ±rlandÄ±rmasÄ± (Security Containment) KanÄ±tlarÄ±

## 1.1 PIN Disclosure
- /request_pin JSON yanÄ±tÄ±ndan PIN Ã§Ä±karÄ±ldÄ±.
- Host UI iÃ§in start_server'a callback eklendi.
- PIN Ã¼retimi iÃ§in secrets.randbelow kullanÄ±ldÄ±.
- gent.py iÃ§indeki PIN loglamalarÄ± kaldÄ±rÄ±ldÄ±.

## 1.2 Auto-trust Bypass
- stream_server.py iÃ§indeki _check_auth metodundan Device-Id yetkilendirmesi Ã§Ä±karÄ±ldÄ±.
- Query string Ã¼zerinden PIN kontrolÃ¼ kaldÄ±rÄ±ldÄ±.
- BaÅŸarÄ±lÄ± PIN sonrasÄ± TrustStore'a otomatik kayÄ±t yapÄ±lmasÄ± engellendi.

## 1.3 TLS Fail-Closed
- stream_server.py iÃ§indeki _setup_tls metodu, cryptography yoksa veya kurulum baÅŸarÄ±sÄ±z olursa dÃ¼z HTTP'ye dÃ¼ÅŸmek yerine RuntimeError fÄ±rlatacak ÅŸekilde gÃ¼ncellendi.

## 1.4 Sandbox Path Denetimi
- s_server.py iÃ§indeki esolve_path metodu gÃ¼ncellendi: Windows os.path.join sÃ¼rÃ¼cÃ¼ harfi aÃ§Ä±ÄŸÄ± (C:, D: atlama) : kontrolÃ¼yle kapatÄ±ldÄ±.
- os.path.realpath kullanÄ±larak symlink ve .. traversalÄ± kÄ±rÄ±lamaz hale getirildi.
- PathTraversalError eklendi; ihlal durumunda stream_server bu hatayÄ± yakalayÄ±p istemci IP'sinin PIN yetkisini evoke_pin ile dÃ¼ÅŸÃ¼rÃ¼yor ve 403 dÃ¶nÃ¼yor.
## 1.4 Dosya Consent Fail-Closed
- gent.py içindeki _on_file_req MessageBox hatasında True yerine False dönecek şekilde düzeltildi (Fail-Closed).
- 	ransfer.py içindeki dosya kabul kontrolünde policy yokluğu (on_file_request is None) varsayılan ret ile değiştirildi.
- 	ransfer.py receiver yalnız ssl_context ile başlayacak şekilde güncellendi, SSL yoksa başlatılmayarak (Fail-Closed) plain text transfer engellendi.

## 1.5 Deneysel İnternet Erişimi
- stream_server.py içindeki /webrtc/offer endpoint'i PARDUS_ENABLE_EXPERIMENTAL=1 ortam değişkeniyle kilitlendi. Değişken yoksa 403 EXPERIMENTAL_FEATURE_DISABLED döndürüyor.
- device_manager.py ve UI'da internet erişimi iddiaları şimdilik varsayılan yapılandırma ile örtüşecek şekilde (WOL ve Rendezvous) kapalı konumda kilitli kalacak.
