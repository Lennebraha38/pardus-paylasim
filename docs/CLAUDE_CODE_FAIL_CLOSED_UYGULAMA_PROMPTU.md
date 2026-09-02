# Claude Code için Fail-Closed Uygulama Promptu

Aşağıdaki metni Claude Code’a, depo kökünde çalışırken tek parça hâlinde ver.

---

## ROLÜN

Sen bu görevde kıdemli bir güvenlik mühendisi, çapraz-platform Python geliştiricisi, WebRTC mühendisi, erişilebilirlik uzmanı, Debian/Windows paketleme mühendisi ve test liderisin.

Çalışma depon:

```text
D:\Müşteri İşleri\Pardus app\pardus-paylasim
```

Amaç, “özellik varmış gibi görünen prototip” üretmek değil; Pardus 23/25 ve Windows üzerinde kanıtlanabilir şekilde çalışan, güvenli varsayılanlara sahip, başarısızlıkta yetki vermeyen ve her fazı test kapısından geçen bir ürün adayı oluşturmaktır.

Bu promptta yazmayan yeni büyük özellikleri ekleme. Önce güvenlik, doğruluk ve doğrulama borcunu kapat. Bütün eski “tamamlandı”, “%100”, “kusursuz” ve “tüm protokoller test edildi” ifadelerini kanıtlanmamış varsay.

## BAŞLANGIÇTA BİLDİĞİN KANITLAR

Bu bulguları yeniden doğrula; doğru çıkarsa başlangıç denetim raporuna koy:

```text
Branch: master
HEAD: 769f70f
origin/master'ın 53 commit önünde
11 değiştirilmiş + 28 izlenmeyen çalışma ağacı girdisi

compileall: başarılı
pip check: başarılı
Ruff: 110 hata

Temel suite, E2E ve test_web_viewer hariç:
  369 passed, 6 skipped

test_web_viewer:
  13 passed, 1 failed

Tam koleksiyon:
  382 passed, 6 skipped, 4 failed

Coverage:
  toplam yaklaşık %42
  webrtc_server %0
  webrtc_tracks %0
  fs_server %0
  rendezvous_client %0
  wol %0
  tray %0
  audit/trust modüllerinin adanmış testleri yok
```

Bilinen yüksek riskler:

1. `/request_pin` PIN’i unauthenticated isteyene döndürüyor.
2. `pairing.py` PIN için `random.randint` kullanıyor.
3. `X-Pardus-Device-Id` veya query `device_id`, imzalı challenge olmadan trusted erişim sağlayabiliyor.
4. Başarılı PIN sonrası istemcinin verdiği cihaz ID’si otomatik trust store’a yazılıyor.
5. TLS kurulumu başarısızsa sunucu plaintext devam ediyor.
6. Web viewer PIN’i WebRTC, stream, WebSocket, upload veya file manager yollarında query string’e koyabiliyor.
7. Normal dosya ve bağımsız pano kanalları varsayılan plaintext.
8. Windows agent dosya onay UI’si hata verirse `True` dönüyor.
9. File receiver, gönderilen boyuta göre tüm payload’ı RAM’e alıyor.
10. Web upload 1 GB’a kadar tüm gövdeyi RAM’e alıyor.
11. `fs_server.resolve_path` symlink-safe değil.
12. File manager inline JS/CSS içeriyor; CSP bunları engelliyor.
13. WebSocket handshake Origin, Upgrade/Connection ve version doğrulamasını tamamlamıyor.
14. Granular permission setter UI tarafından kullanılmıyor; tüm yetkiler varsayılan açık.
15. Portal backend, session oluşturmayan bir stub.
16. WebRTC ICE aday değişimi eksik; TURN yok; Google STUN sabit.
17. WebRTC kontrol koordinatı `<video>` için yanlış `naturalWidth/naturalHeight` kullanıyor.
18. Rendezvous router plaintext/auth’suz ve uygulamaya güvenli biçimde bağlı değil.
19. Docker “Windows mock” Linux; Windows API’lerini test edemez.
20. Yeni Docker giriş noktası olarak olmayan `src/pardus_paylasim/agent_main.py` kullanılıyor.
21. `scripts/build_deb.sh` olmayan `setup.py` dosyasını çağırıyor.
22. `scripts/build_exe.ps1` olmayan giriş dosyası ve ikon kullanıyor.
23. Debian paket girdileri web viewer dosyalarını kurmuyor.
24. GitHub Actions `main` branch’ini dinliyor; aktif branch `master`.
25. Ruff ve Debian integration CI’da non-gating.

## MUTLAK KURALLAR

### Güvenlik

1. **Fail-closed:** TLS, kimlik doğrulama, consent, path sandbox veya güvenli anahtar deposu kurulamazsa ilgili özellik başlamayacak. Plaintext’e, auto-accept’e veya sessiz no-op backend’e düşme.
2. Güvenlik özelliği “opsiyonel” ise varsayılan kapalı olacak; kullanıcı açıkça etkinleştirecek.
3. PIN, token, session ID, pano içeriği, sohbet içeriği, özel anahtar veya tam hassas yol loglanmayacak.
4. PIN ve bearer token URL query’sinde taşınmayacak.
5. Kullanıcı tarafından gönderilen bir metin “public key” veya “trusted identity” sayılmayacak.
6. Kendi kriptografik algoritmanı icat etme. `cryptography` ve standart protokoller kullan.
7. Eş doğrulanmadan unattended access, dosya erişimi, pano veya input capability verme.
8. Consent penceresi açılamazsa istek reddedilecek.
9. Backend “available” raporlanıyorsa gerçek bir probe ve temel operasyon testi başarılı olmalı; stub available sayılmayacak.
10. İnternet/rendezvous özellikleri güvenli signaling ve TURN gate’leri geçmeden release build’de etkin olmayacak.

### Kod ve depo güvenliği

1. Kullanıcının mevcut değişikliklerini silme, resetleme veya üzerine yazma.
2. `git reset --hard`, `git checkout -- .`, toplu geri alma veya geniş silme kullanma.
3. Önce çalışma ağacının tam envanterini ve patch yedeğini üret.
4. Mevcut dirty tree’yi tek hamlede `git add -A` ile commit etme.
5. Her commit tek konuya ait ve yalnız doğrulanan dosyalardan oluşsun.
6. Her fazdan önce ve sonra `git status --short` raporla.
7. Test başarısızken sonraki faza geçme.
8. “Bende çalıştı” ifadesi yerine komut, exit code, ortam ve artefact hash ver.
9. Test çalışmadıysa “geçti” yazma. `skip`, `xfail`, mock ve manuel testi açıkça ayır.
10. Paketleme, bütün önceki güvenlik ve işlev gate’leri yeşil olmadan başlamayacak.

### Ürün dürüstlüğü

1. `/info`, capability reklamı ve UI gerçek runtime durumunu göstermeli.
2. Deneysel özellik `experimental` etiketi taşımalı.
3. Fiziksel Windows/Pardus testi yoksa destek iddiası yazılmayacak.
4. “%100 güvenli”, “kusursuz”, “tüm protokoller garantili” gibi ifadeleri kullanma.
5. Eski belgelerdeki yanlış iddiaları düzelt; test sonucu ile pazarlama iddiasını karıştırma.

## REFERANS STANDARTLAR

Kararları aşağıdaki birincil kaynaklarla uyumlu tut:

- OWASP WebSocket Security Cheat Sheet
- OWASP File Upload Cheat Sheet
- RFC 6455
- RFC 8445
- RFC 8656
- RFC 8827
- W3C WebRTC
- XDG Desktop Portal RemoteDesktop
- WCAG 2.2 AA
- Debian Policy
- PyInstaller güncel belgeleri
- Microsoft Authenticode/SignTool
- pytest strict markers
- Playwright + axe erişilebilirlik testi

## ZORUNLU ÇALIŞMA BİÇİMİ

Her fazda şu sırayı uygula:

1. Tehdit veya davranış sözleşmesini yaz.
2. Başarısız olması gereken negatif testi önce ekle.
3. En küçük güvenli uygulamayı yap.
4. Faz testlerini çalıştır.
5. Tam hızlı suite’i çalıştır.
6. Kapsam ve lint farkını raporla.
7. Gate yeşil değilse dur, kök nedeni düzelt; sonraki faza geçme.
8. `docs/verification/PHASE_<n>.md` içine:
   - commit SHA
   - OS/Python/browser
   - komutlar
   - exit code
   - pass/fail/skip
   - bilinen sınırlamalar
   - artefact hash
   yaz.

## FAZ 0 — ADLİ DEVİR ALMA VE KANIT TABANI

### 0.1 Belgeleri oku

Tam oku:

```text
docs/MASTER_PLAN_uzaktan-kontrol.md
.claude/RESUME.md
docs/basvuru/TEKNOFEST_BASVURU_RAPORU_V3.doc
README.md
pyproject.toml
debian/*
.github/workflows/*
.gitlab-ci.yml
```

Eski sohbet veya checklist’i gerçeklik kaynağı sayma.

### 0.2 Çalışma ağacını koru

Üret:

```text
work/baseline/git-status.txt
work/baseline/git-diff.patch
work/baseline/git-diff-staged.patch
work/baseline/untracked-files.txt
work/baseline/file-hashes.sha256
```

Untracked dosyaları içerik türüne göre sınıflandır:

- çekirdek uygulama
- deneysel özellik
- paketleme
- test
- rapor
- geçici/artefact

Kullanıcı değişikliklerini kaybetmeden özel bir çalışma branch’i kullan. Branch değiştirme mevcut dirty tree için riskliyse önce patch ve hash yedeğini doğrula.

### 0.3 Başlangıç komutları

En az şunları çalıştır:

```powershell
py -m compileall -q src
py -m pip check
py -m ruff check src tests --statistics
py -m pytest tests -q
py -m pytest tests --ignore=tests/e2e -q
py -m pytest tests --ignore=tests/e2e --ignore=tests/test_web_viewer.py `
  --cov=pardus_paylasim --cov=pardus_paylasim_agent `
  --cov-report=term-missing --cov-report=xml
node --check data/web-viewer/viewer.js
git diff --check
```

Araç eksikse bunu raporla; kurulum yapmadan “başarılı” sayma.

### 0.4 Kanıt matrisi

`docs/verification/BASELINE.md` üret. Her özellik:

```text
IMPLEMENTED
UNIT_VERIFIED
INTEGRATION_VERIFIED
NATIVE_OS_VERIFIED
PACKAGED_VERIFIED
EXPERIMENTAL
DISABLED
BROKEN
UNVERIFIED
```

durumlarından biri veya birkaçıyla etiketlensin.

### Faz 0 gate

- Yedek dosyaları var ve hash’leri doğrulanmış.
- Güncel test sayısı ve failure listesi raporda.
- Hiçbir dosya kaybolmadı.
- Master plan, RESUME ve gerçek kod farkları yazıldı.

Gate yeşil olmadan kod değiştirme.

## FAZ 1 — ACİL GÜVENLİK CONTAINMENT

Bu faz yeni güvenli pairing’i tamamlamaz; mevcut tehlikeli yolları kapatır.

### 1.1 PIN disclosure’ı kapat

- `/request_pin` PIN döndürmemeli.
- Host UI/agent tray dışında PIN gösterme.
- PIN üretiminde `secrets.randbelow` veya `secrets.choice` kullan.
- TTL, tek kullanım, maksimum deneme ve exponential/capped lockout uygula.
- PIN’i plaintext diske yazma.
- PIN’i loglama.
- Aynı PIN’i farklı peer/IP/session için kabul etme.
- PIN doğrulandıktan sonra tekrar kullanılamasın.

Negatif testler:

- unauthenticated `/request_pin` PIN içermez
- brute force lockout
- expiry
- replay
- başka peer/session
- log capture’da PIN yok

### 1.2 Auto-trust’ı tamamen kapat

Yeni kriptografik pairing tamamlanana kadar:

- `X-Pardus-Device-Id` auth sağlamasın.
- query `device_id` auth sağlamasın.
- başarılı PIN otomatik trust store yazmasın.
- mevcut `trusted_devices.json` kayıtlarını otomatik geçerli sayma.
- migration onları `legacy_unverified` olarak işaretlesin.
- unattended access UI’da kapalı ve açıklamalı olsun.

Negatif test:

- rastgele veya daha önce kayıtlı düz ID hiçbir endpoint’e erişemiyor.

### 1.3 TLS fail-closed

- Production server `require_tls=True`.
- Sertifika/anahtar/context kurulamazsa bind etmeden exception.
- HTTP fallback kaldır.
- Development plaintext yalnız:
  - açık `--insecure-development-only`
  - yalnız `127.0.0.1`
  - release build’de unavailable
  - UI ve logda kırmızı uyarı

Testler:

- crypto unavailable → server başlamıyor
- cert failure → port açılmıyor
- release config → insecure flag reddediliyor
- TLS normal start/stop

### 1.4 Dosya consent fail-closed

- Agent MessageBox/notification hatası → `False`.
- `on_file_request is None` production’da auto-accept etmesin.
- açık policy yoksa reject.
- receiver yalnız secure session ile başlasın; bu sağlanamıyorsa bu fazda disabled.

### 1.5 Deneysel internet erişimini kapat

- Rendezvous/global ID/WOL/WebRTC audio varsayılan build/runtime’da disabled.
- `PARDUS_ENABLE_EXPERIMENTAL=1` bile güvenlik kontrolünü bypass etmesin.
- UI yanlışlıkla “hazır” demesin.

### Faz 1 gate

```text
PIN disclosure testi yeşil
Auto-trust bypass testi yeşil
TLS failure port açmıyor
Consent exception reject ediyor
Tam non-E2E suite 0 fail
Ruff en az değiştirilen güvenlik dosyalarında 0
```

Bu gate geçmeden yeni özellik ekleme.

## FAZ 2 — KİMLİK, PAIRING VE SESSION YETKİ MODELİ

### 2.1 Tehdit modeli

`docs/security/THREAT_MODEL.md` oluştur. En az:

- aynı LAN’daki saldırgan
- kötü niyetli web origin
- MITM
- PIN brute force/replay
- çalınmış cihaz
- NAT arkasında aynı IP’yi paylaşan peer’ler
- kötü niyetli dosya adı/içeriği
- resource exhaustion
- kötü niyetli rendezvous/TURN
- log ve local storage sızıntısı
- symlink/TOCTOU

Her varlık, güven sınırı ve capability’yi çiz.

### 2.2 Gerçek cihaz anahtarları

Bir `DeviceIdentity` arayüzü tasarla:

- Python agent/host için incelenmiş `cryptography` primitive’i
- browser için WebCrypto tarafından desteklenen, non-extractable anahtar
- geniş tarayıcı uyumu için P-256 ECDSA kabul edilebilir
- public key canonical format
- private key sahipliği nonce imzasıyla kanıtlanır
- private key export edilmez veya güvenli biçimde saklanır

Trust store yalnız şunları saklasın:

```text
device_fingerprint
public_key
display_name
created_at
last_used_at
expires_at
revoked_at
allowed_capabilities
pairing_method
schema_version
```

Dosya:

- POSIX `0600`
- Windows user-only ACL
- atomik write
- bozuk JSON fail-closed
- migration yedekli

### 2.3 İlk pairing

İki kabul edilebilir yol:

1. İncelenmiş bir PAKE/SPAKE2+ kütüphanesi ve transcript binding
2. Explicit host consent + her iki uçta görüntülenen transcript-bound Short Authentication String

Kütüphane/uyumluluk yoksa kripto icat etme; unattended access’i kapalı tut ve yalnız her oturum host onayıyla devam et.

Zorunlu özellikler:

- istemci key proof
- hostta peer adı + fingerprint/SAS
- açık “Bir kez izin ver” ve “Bu cihazı güven” ayrımı
- varsayılan yalnız bir kez
- trust yalnız host kullanıcı eyleminden sonra
- capability kapsamı
- expiry/revoke

### 2.4 Oturum token’ları

- kısa ömürlü
- cryptographically random
- session + device fingerprint + capability + expiry’ye bağlı
- IP’ye bağlı değil
- constant-time karşılaştırma
- logout/kill-switch/revoke ile anında geçersiz
- token rotation
- query string’de değil

WebSocket için token:

- handshake header kullanılamıyorsa ilk application message ile
- kısa auth timeout
- auth öncesi hiçbir işlev yok

### Faz 2 testleri

- key generation/load
- secure file permissions
- signed challenge happy path
- wrong key
- replayed signature
- altered transcript
- expired/revoked device
- capability escalation
- corrupted trust store
- legacy ID bypass
- concurrent sessions
- NAT same-IP two peers

### Faz 2 gate

- Düz ID ile auth imkânsız.
- Host eylemi olmadan trust kaydı oluşmuyor.
- Replay ve capability escalation testleri yeşil.
- Trust/auth modülleri ≥%90 coverage.
- Security review notu tamam.

## FAZ 3 — TAŞIMA KATMANINI BİRLEŞTİR

Amaç, ekran/control/dosya/pano için farklı güvenlik seviyelerini ortadan kaldırmak.

### 3.1 Session-aware endpoint modeli

Tek TLS server altında:

```text
/api/v1/session/*
/api/v1/files/*
/api/v1/clipboard/*
/api/v1/webrtc/*
/control
/stream
```

Her endpoint capability kontrolü yapsın.

### 3.2 Raw TCP dosya/pano kanalları

Tercih:

- Bunları deprecate et.
- Native client ve agent’ı authenticated HTTPS/WSS endpoint’lerine geçir.

Geçici geriye uyumluluk gerekiyorsa:

- yalnız explicit legacy flag
- yalnız TLS
- signed session auth
- production default off
- mDNS’de insecure legacy capability reklamı yok

### 3.3 Dosya upload

Zorunlu:

- streaming, sabit sınırlı bellek
- Content-Length ve gerçek alınan byte eşleşmesi
- global/per-session/per-file quota
- kısa timeout ve slowloris koruması
- uygulama tarafından üretilen storage ID
- kullanıcı dosya adı yalnız metadata
- Unicode normalize
- filename length/character policy
- extension/type policy ürün gereksinimine göre
- webroot dışı storage
- geçici dosya → hash/size doğrulama → fsync → atomik rename
- overwrite yok
- malware/CDR hook opsiyonel; başarısızsa politikanın belirlediği reject/quarantine
- açık consent
- iptal ve bağlantı kopmasında temp cleanup

1 GB varsayılanını kaldır; yapılandırılabilir makul limit ve disk free-space kontrolü kullan.

### 3.4 Download/file manager

Path’i istemciden doğrudan kabul etme. Server-generated opaque file ID kullan.

Eğer path tabanlı API geçici olarak kalırsa:

- `realpath` + `commonpath`
- symlink takip etmeme
- POSIX’te mümkünse `openat`/`O_NOFOLLOW`
- open sonrası inode/path yeniden doğrulama
- directory symlink dışlama
- Windows junction/reparse point değerlendirmesi

`Content-Disposition` için güvenli `filename` + RFC 5987 `filename*`.

### 3.5 Bütünlük ve protokol

- TLS bütünlüğüne ek olarak dosya SHA-256 doğrula.
- Response, alınan hash ve byte sayısını içersin.
- Versioned JSON/CBOR metadata; sınırları tanımlı.
- Resume gerekiyorsa chunk index + per-chunk hash ve session binding.
- Kendi ad-hoc “AES bütün dosya RAM’de” tasarımını genişletme.

### 3.6 Pano

- açık ayrı capability: read ve write
- varsayılan kapalı
- boyut limiti
- content type yalnız text/plain başlangıçta
- loop suppression ID
- origin/session
- ACK, OS clipboard write başarılı olduktan sonra
- kullanıcı policy: `block`, `warn`, `mask`, `allow`
- DLP kararını sessizce değiştirme; görünür ve auditli

### Faz 3 negatif testleri

- oversized name
- oversized body
- incorrect Content-Length
- fragmented reads
- slowloris
- disconnect halfway
- disk full
- symlink escape
- junction/reparse simulation
- Unicode confusable name
- overwrite race
- hash mismatch
- unauthorized upload/download
- capability mismatch
- consent reject
- consent UI exception
- clipboard loop
- clipboard oversize
- plaintext connection

### Faz 3 gate

- Büyük dosya testinde bellek kullanımı dosya boyutuyla doğrusal büyümüyor.
- Plaintext file/clipboard production’da reddediliyor.
- Traversal ve symlink corpus yeşil.
- Transfer/path modülleri ≥%90 coverage.
- Tam suite 0 fail.

## FAZ 4 — WEBSOCKET VE UZAK KONTROL HARDENING

### 4.1 RFC 6455 handshake

Doğrula:

- request path tam `/control`
- `Upgrade: websocket`
- `Connection` token listesinde `upgrade`
- `Sec-WebSocket-Version: 13`
- geçerli `Sec-WebSocket-Key`
- method GET
- allowed `Origin`
- authenticated session
- `control` capability

Allowed origin:

- same-origin varsayılan
- explicit exact allowlist
- wildcard yok
- `null` origin varsayılan reject

### 4.2 Per-peer consent

Global toggle yalnız “kontrol isteği kabul edilebilir” anlamına gelsin.

Her bağlantı isteğinde host:

- peer adı/fingerprint
- istenen capability’ler
- süre
- “bir kez izin ver”
- “reddet”

görsün.

### 4.3 Granular capability

Ayrı:

```text
view
mouse
keyboard
clipboard_read
clipboard_write
file_upload
file_download
audio
```

Varsayılan:

```text
view=true
diğerleri=false
```

UI seçimi doğrudan server-side session capability’ye yansısın.

### 4.4 Yaşam döngüsü

- auth timeout
- idle timeout
- absolute expiry
- ping/pong heartbeat
- dead peer cleanup
- connection limit
- per-device rate
- backpressure
- kill-switch bütün bağlantıları anında kapatır
- host ekran kilitlenince veya kullanıcı logout olunca control revoke

### 4.5 Input güvenliği

- backend exception tek olayı reddetsin; server loop kontrollü kapansın
- stuck key/button cleanup
- key allow/deny policy
- dangerous combos geniş tehdit modeli
- Secure Attention Sequence gibi OS tarafından yasaklı olayları iddia etme
- monitor-aware coordinate mapping
- DPI/scaling

### Faz 4 testleri

- bad Upgrade/Connection/version/key
- malicious Origin
- null Origin
- auth timeout
- expired token
- revoked token
- two peers same IP
- permission matrix
- rate flood
- oversized frame
- fragmented/continuation frame policy
- backend exception
- kill-switch latency
- disconnect with key held

### Faz 4 gate

- OWASP WebSocket negatif test listesi yeşil.
- Her input eylemi doğru capability gerektiriyor.
- Origin bypass yok.
- Control server/protocol ≥%90 coverage.
- 10 dakikalık soak testte thread/socket sızıntısı yok.

## FAZ 5 — WEBRTC VİDEO, ICE VE TURN

WebRTC’yi iki alt release’e ayır: önce video, sonra audio.

### 5.1 Signaling

- Authenticated HTTPS/WSS signaling
- offer/answer size ve schema limitleri
- per-session peer mapping
- request timeout
- CSRF/Origin kontrolü
- SDP loglama yok veya redacted

ICE için iki yoldan birini eksiksiz uygula:

1. Trickle ICE: candidate endpoint/message + `addIceCandidate`
2. Non-trickle: `iceGatheringState == complete` bekle ve `pc.localDescription.sdp` gönder

Eski `offer.sdp` gönderme hatasını düzelt.

### 5.2 LAN privacy default

Varsayılan LAN profili:

```text
iceServers=[]
```

Haricî Google STUN sabitlerini kaldır.

STUN kullanımı:

- yapılandırılabilir
- kullanıcıya görünür
- privacy açıklaması

### 5.3 TURN

Internet profili için:

- self-hosted veya kurumsal TURN
- `turns:` tercih
- kısa ömürlü credentials
- realm
- quota/rate
- secret rotation
- relay-only test modu
- credential loglama yok

RFC 8656 long-term credential gereklilikleriyle uyumlu ol.

### 5.4 Peer lifecycle

- Tek sahipli uzun ömürlü asyncio loop/service
- HTTP thread başına event loop oluşturma yok
- per-PC registry
- deterministic close
- failed/disconnected timeout
- ICE restart
- server shutdown’da bütün PC’ler kapanır
- bounded resource count

### 5.5 Video capture

- capture event loop’u bloklamasın
- worker + bounded queue
- drop-oldest backpressure
- gerçek FPS pacing
- monitor discovery
- monitor index doğrulama
- cursor policy
- resolution/quality config
- encoder capability raporu
- hardware acceleration yalnız gerçek probe sonrası

Tarayıcı:

- `<video>` için `videoWidth/videoHeight`
- `loadedmetadata`/`playing`
- aspect-fit coordinate mapping
- reconnect UI
- WebRTC başarısızsa açık, güvenli MJPEG fallback
- fallback auth/TLS aynı güvenlikte

### 5.6 Ölçüm

`getStats()` ile:

- RTT
- packet loss
- bitrate
- frame rate
- dropped frames
- selected candidate type

Topla; hassas IP’leri normal kullanıcı loguna yazma.

“60 FPS” hedef değil, ölçülen sonuçtur. Donanım/çözünürlük matrisi olmadan belgeye yazma.

### Faz 5 testleri

- offer/answer
- candidate gathering complete
- trickle candidate order/replay
- TURN relay-only
- STUN unavailable
- ICE restart
- peer timeout
- 20 concurrent peer resource cap
- capture backpressure
- monitor invalid index
- browser video coordinate mapping
- MJPEG fallback
- signaling auth/origin/oversize

### Faz 5 gate

- LAN testi haricî DNS/STUN erişimi olmadan çalışıyor.
- TURN relay-only E2E geçiyor.
- Chromium ve Firefox gerçek media frame alıyor.
- Peer kapanınca resource registry temiz.
- WebRTC modülleri ≥%85 coverage; signaling/auth ≥%90.

## FAZ 6 — AUDIO

Audio, video gate’i geçmeden başlamaz.

### 6.1 Capability

Pardus:

- PipeWire/PulseAudio monitor source gerçek probe
- kullanıcıya source seçimi

Windows:

- WASAPI loopback gerçek Windows test

### 6.2 Consent ve gizlilik

- audio varsayılan kapalı
- host açıkça etkinleştirir
- kalıcı görünür “ses paylaşılıyor” göstergesi
- mute
- session revoke
- capture failure video session’ı yetkisiz şekilde değiştirmez

### 6.3 Teknik

- 48 kHz stereo/mono policy
- doğru PTS/time_base
- bounded audio buffer
- underflow/overflow
- device change
- cleanup

### Faz 6 gate

- Pardus 23/25 gerçek audio loopback testi
- Windows gerçek WASAPI loopback testi
- mute/revoke
- 30 dakika drift testi
- unsupported sistemde capability false ve audio track eklenmiyor

Gerçek OS kanıtı yoksa audio experimental kalır.

## FAZ 7 — WAYLAND, X11, WINDOWS VE ÇOKLU MONİTÖR

### 7.1 Wayland Portal

XDG RemoteDesktop akışını eksiksiz uygula:

```text
CreateSession
SelectDevices
Start
Response sinyallerini bekle
Verilen device capability’lerini oku
Session handle sakla
Notify* veya Start sonrası ConnectToEIS/libei
Session Close
```

Mutlak pointer için stream/mapping/logical_size kullan.

Portal:

- kullanıcı reddi → backend unavailable
- timeout → unavailable
- session close → control revoke
- izin verilmeyen pointer/keyboard çağrısı yok

Stub’ı auto-select listesinden çıkar.

### 7.2 X11

- XTEST runtime probe
- screen size/DPI/monitor mapping
- stuck input cleanup
- gerçek Xvfb yanında en az bir gerçek X11 oturum testi

### 7.3 Windows

Gerçek Windows runner/VM:

- mss capture
- pynput input
- tray
- MessageBox/notification consent
- clipboard
- key ACL
- EXE launch
- multi-monitor/DPI

Linux mock, Windows doğrulaması sayılmaz.

### 7.4 Multi-monitor

- gerçek monitor list endpoint’i
- stable monitor ID
- hotplug
- primary değişimi
- per-monitor logical/physical resolution
- browser selector dinamik
- invalid/stale ID fail-closed

### Faz 7 gate

- Pardus 23 X11
- Pardus 23 Wayland
- Pardus 25 X11
- Pardus 25 Wayland
- Windows 10/11 destek politikası

Her satırda view/control/file/clipboard ve beklenen backend kanıtı olmalı. Fiziksel teste ulaşılamıyorsa satır `UNVERIFIED`, asla PASS değil.

## FAZ 8 — WEB UI, DOSYA YÖNETİCİSİ VE ERİŞİLEBİLİRLİK

### 8.1 CSP

- Inline script/style kaldır.
- Ayrı `file-manager.js` ve `file-manager.css`.
- Nonce/hash kullanmıyorsan strict self CSP.
- `object-src 'none'`
- `base-uri 'none'`
- `frame-ancestors 'none'`
- uygun `connect-src`, `img-src`, `media-src`
- MIME sniffing kapalı

### 8.2 Kimlik bilgisi

- PIN/token URL’den tamamen kalksın.
- File manager yeni authenticated session üzerinden açılsın.
- History/referrer/cache kontrolleri.

### 8.3 WCAG 2.2 AA

En az:

- semantic HTML
- gerçek `<button>`/`<a>`
- tam klavye kullanımı
- görünür focus
- focus not obscured
- logical focus order
- `role=status`/`aria-live`
- hata bağlantısı ve açıklaması
- drag için buton/file input alternatifi
- minimum target size
- contrast
- 200% zoom
- 320 CSS px reflow
- reduced motion
- forced colors/high contrast
- touch gesture alternatifi
- bağlantı/control/audio durumunun programatik adı

### 8.4 Assistive technology

- Playwright + `@axe-core/playwright`
- Chromium + Firefox; WebKit mümkünse
- keyboard-only senaryolar
- Pardus Orca manuel senaryo
- Windows NVDA manuel senaryo

Automated axe, manuel erişilebilirlik değerlendirmesinin yerine geçmez.

### Faz 8 gate

- axe critical/serious 0
- keyboard E2E geçiyor
- CSP console violation 0
- PIN/token URL’de yok
- dosya yöneticisi symlink/auth testleri geçiyor
- manuel Orca/NVDA sonucu raporlu veya açık `UNVERIFIED`

## FAZ 9 — RENDEZVOUS, INTERNET ERİŞİMİ, SOHBET VE WOL

Bu faz yalnız 1–8 tamamen yeşilse başlar.

### 9.1 Rendezvous

- `wss://`
- server certificate validation
- authenticated device registration
- signed challenge
- target consent
- unguessable opaque rendezvous handle
- predictable 9-digit ID tek başına auth değil
- TTL
- reconnect with exponential backoff + jitter
- message schema/size/rate/connection limits
- abuse/ban/metrics
- no raw SDP/message logging
- persistence gerekiyorsa encrypted/least privilege

### 9.2 TURN

Faz 5 TURN altyapısını kullan; router relay gibi davranmasın.

### 9.3 Sohbet

- ayrı capability ve consent
- message length/rate
- text only
- `textContent`
- no HTML
- içerik audit loguna yazılmaz
- retention varsayılan yok

### 9.4 WOL

- yalnız yerel ağ/explicit trusted device
- doğrulanmış MAC mapping
- broadcast scope
- rate limit
- UI consent
- “cihaz açıldı” yalnız doğrulama sonrası

### Faz 9 gate

- unauthenticated registration/offer reddediliyor
- ID enumeration testi
- rate/oversize
- malicious signaling
- relay-only NAT E2E
- consent reject
- revoked device
- chat XSS corpus
- WOL rate/scope

Gate geçmezse bu modüller release build’de disabled kalır.

## FAZ 10 — TEST MİMARİSİ VE CI

### 10.1 pytest ayrımı

Marker’ları kaydet ve strict yap:

```toml
addopts = [
  "--strict-markers",
  "-ra",
  "--import-mode=importlib"
]
markers = [
  "unit",
  "integration",
  "e2e",
  "docker",
  "native_windows",
  "native_pardus",
  "wayland",
  "x11",
  "network",
  "slow",
  "security",
  "accessibility"
]
```

Normal `pytest` dış DNS/Docker host adı istemesin. E2E yalnız açık ortam doğrulamasıyla toplansın.

### 10.2 Test katmanları

**PR zorunlu:**

- compileall
- Ruff
- unit
- security negative
- coverage
- dependency audit
- web unit

**Platform zorunlu:**

- Windows native agent
- Pardus 23 package/container
- Pardus 25 package/container
- browser E2E

**Nightly:**

- NAT/TURN
- soak
- fault injection
- large file
- multi-monitor
- audio

### 10.3 Gerçek OS matrisi

“Windows mock” adını `linux-protocol-mock` yap. Windows kanıtı için Windows runner/VM kullan.

Pardus:

- resmi `pardus/yirmiuc` ve `pardus/yirmibes` imajlarını digest ile pinle
- Debian image’i Pardus diye adlandırma
- image availability fail ederse required job fail etsin veya açık infrastructure-blocked sonucu üretsin; success olmasın

### 10.4 Network fault tests

En az:

- fragmentation
- latency
- packet loss
- half-close
- abrupt reset
- slow reader/writer
- connection storm
- DNS failure
- STUN failure
- TURN auth failure
- disk full
- clock skew

### 10.5 CI düzeltmeleri

- `master`/`main` branch politikasını tekleştir.
- Ruff required.
- Paket integration required.
- `continue-on-error`/`allow_failure` release gate’lerinden kaldır.
- GitHub ve GitLab aynı kanonik komutları kullansın.
- Test script cleanup `finally`/trap ile her durumda çalışsın.
- fixed sleep yerine healthcheck/readiness.

### Faz 10 gate

- PR pipeline tamamen yeşil.
- E2E yanlışlıkla unit suite’e girmiyor.
- Gerçek Windows ve gerçek Pardus artefact testleri ayrı.
- Beklenmeyen skip = 0.
- Coverage toplam ≥%80; kritik modüller ≥%90.
- Flaky retry ile başarısızlığı gizleme yok.

## FAZ 11 — PAKETLEME VE TEDARİK ZİNCİRİ

Bu faz 1–10 gate’lerinin tamamı yeşil olmadan başlamaz.

### 11.1 Debian/Pardus

Tek kanonik yol seç:

```text
debian/ + dpkg-buildpackage/debuild + pybuild
```

`scripts/build_deb.sh` içindeki stdeb/setup.py yolunu kaldır veya kanonik komuta çevir.

Doğrula:

- gerçek package data
- web viewer assets
- locale
- GSettings
- desktop/metainfo/icon
- agent yalnız ürün kararına göre ayrı paket
- Depends/Recommends gerçek runtime importlarıyla uyumlu
- postinst/prerm/postrm idempotent
- no network during build
- clean chroot build
- lintian error 0
- install/launch/upgrade/remove/purge
- reproducible build: iki temiz build aynı hash veya fark raporu

Pardus 21:

- resmi destek ömrü bitmiş
- Python 3.9 ile mevcut `>=3.10` çelişkisini çözmeden uyum iddia etme
- ya bilinçli backport ya legacy unsupported

Zorunlu hedef Pardus 23 ve 25.

### 11.2 Windows

- PyInstaller build Windows üzerinde
- gerçek module entry point
- web assets
- icon
- version info
- manifest
- hidden imports ve binaries
- aiortc/av/soundcard/numpy yalnız ilgili flavor’da
- tray startup smoke
- frozen resource path test
- Defender/SmartScreen davranışını raporla

Önce `onedir` ile doğrula; sonra gerekliyse `onefile`.

### 11.3 İmzalama

EXE:

- Authenticode SHA-256
- RFC 3161 timestamp
- `signtool verify` gate
- sertifika parolası log/arg listesinde görünmesin

Deb:

- repo/release imzası veya dağıtım politikasına uygun GPG

### 11.4 SBOM ve provenance

Her release için:

```text
SHA256SUMS
SPDX veya CycloneDX SBOM
dependency lock/snapshot
build provenance/attestation
commit SHA
build environment
verification instructions
```

### Faz 11 gate

- Pardus 23 install/launch/remove PASS
- Pardus 25 install/launch/remove PASS
- Windows EXE build/launch/tray PASS
- paket içindeki web assets PASS
- imza doğrulaması PASS
- SBOM/provenance doğrulaması PASS
- artefact hash’leri raporda

## FAZ 12 — SON E2E MATRİSİ

Aşağıdaki kombinasyonların her biri için ayrı sonuç üret:

| Kaynak | Hedef | View | Control | File up | File down | Clipboard | WebRTC | Audio |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Pardus 23 X11 | Pardus 23 X11 | | | | | | | |
| Pardus 23 Wayland | Pardus 25 Wayland | | | | | | | |
| Pardus 25 X11 | Pardus 23 Wayland | | | | | | | |
| Windows 10/11 | Pardus 23 | | | | | | | |
| Pardus 23 | Windows 10/11 | | | | | | | |
| Windows 10/11 | Pardus 25 | | | | | | | |
| Pardus 25 | Windows 10/11 | | | | | | | |
| Chromium web | Pardus 23/25 | | | | | | | |
| Firefox web | Pardus 23/25 | | | | | | | |

Her hücre yalnız:

```text
PASS
FAIL
SKIP(reason)
UNVERIFIED(reason)
NOT_SUPPORTED(reason)
```

olabilir.

Her PASS için:

- test ID
- timestamp
- source/target OS build
- app commit
- transport
- TLS peer identity
- artefact hash
- log bundle

olmalı.

### Zorunlu security E2E

- wrong PIN
- expired PIN
- PIN replay
- MITM/fingerprint mismatch
- untrusted device ID spoof
- revoked device
- unauthorized capability
- malicious Origin
- TLS missing
- upload traversal
- symlink escape
- oversized upload
- interrupted upload
- malicious WebSocket frame
- rate flood
- TURN wrong credential
- signaling impersonation
- kill-switch

### Faz 12 gate

Release kapsamındaki bütün hücreler PASS. `UNVERIFIED` kalan özellik release notunda desteklenmiyor/experimental olarak işaretlenmiş ve varsayılan kapalı.

## FAZ 13 — BELGELERİ DÜRÜSTÇE GÜNCELLE

Güncelle:

```text
docs/MASTER_PLAN_uzaktan-kontrol.md
.claude/RESUME.md veya yerine docs/CURRENT_STATE.md
README.md
TEKNOFEST başvuru raporu için teknik düzeltme listesi
docs/security/THREAT_MODEL.md
docs/security/PAIRING.md
docs/security/PRIVACY.md
docs/verification/FINAL_TEST_REPORT.md
docs/verification/RELEASE_MATRIX.md
docs/packaging/REPRODUCIBLE_BUILD.md
docs/packaging/VERIFY_RELEASE.md
```

Master plan kutusu yalnız:

- kod tamam
- faz testleri yeşil
- tam suite yeşil
- gerekli native test kanıtı var
- commit SHA yazıldı

ise `[x]` yapılabilir.

TEKNOFEST raporundaki şu iddiaları kanıt yoksa kaldır/düzelt:

- “fonksiyonellik %100 güvence”
- “tüm Docker testleri geçti”
- “bütün aktarım şifreli”
- “Luhn ve IBAN checksum”
- “tüm bağımlılıkları içinde”
- “çalışan güncel paket”
- “Pardus 20+”
- “60 FPS”
- “global internet erişimi tamam”

## HER FAZ SONUNDA RAPOR ŞABLONU

```markdown
# Faz N Sonuç Raporu

## Kapsam

## Değişen dosyalar

## Tehdit/bug

## Uygulanan çözüm

## Eklenen negatif testler

## Komutlar ve exit code

## Test sonuçları
- passed:
- failed:
- skipped:
- xfailed:

## Coverage

## Platform kanıtı

## Güvenlik kontrol listesi

## Bilinen sınırlamalar

## Artefactlar ve SHA-256

## Git
- pre SHA:
- post SHA:
- status:

## Gate
PASS / FAIL / BLOCKED
```

## DURMA KOŞULLARI

Aşağıdaki durumlarda sonraki faza geçme:

1. Herhangi bir required test fail.
2. Güvenlik testi skip.
3. TLS/pairing/consent path’i fail-open.
4. Kullanıcı verisini kaybetme riski.
5. Mevcut dirty değişikliğin sahibi veya amacı belirsiz ve değişiklikle çakışıyor.
6. Gerçek OS gerektiren bir sonucun mock ile “geçmiş” sayılması.
7. Paketleme girdisi commitlenmemiş.
8. Artefact hangi committen üretildiği bilinmiyor.
9. Doküman iddiası kanıttan daha geniş.

Blocker varsa:

- aynı blocker’ı somut kanıtla yaz
- güvenli alternatifleri dene
- eksik olan insan/OS/donanım adımını açık belirt
- ilgili feature’ı disabled bırak
- genel sistemi “tamamlandı” ilan etme

## BİTİŞ TANIMI

Görev yalnız şu durumda tamam:

1. P0 ve P1 bulguları kapanmış.
2. Release kapsamındaki özellikler fail-closed.
3. Tam required CI yeşil.
4. Pardus 23/25 ve Windows native matris kanıtlı.
5. Web browser E2E ve WCAG gate’leri yeşil.
6. `.deb` ve `.exe` güncel committen, doğrulanmış, hashli ve imzalı.
7. SBOM/provenance var.
8. Master plan ve raporlar gerçek test kanıtıyla uyumlu.
9. Varsayılan açık hiçbir experimental/güvensiz yol yok.
10. Final raporda başarısız, atlanan ve doğrulanmayan şeyler açıkça yazılmış.

İlk yanıtında kod yazmaya başlama. Önce Faz 0 kanıt özetini, önerdiğin güvenli branch/commit stratejisini ve Faz 1’de değiştireceğin kesin dosyaları göster. Ardından Faz 0 gate’i yeşilse uygulamaya geç.

---
