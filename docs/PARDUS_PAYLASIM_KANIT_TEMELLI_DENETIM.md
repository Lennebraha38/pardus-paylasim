# Pardus Paylaşım — Kanıt Temelli Teknik Denetim

**Denetim tarihi:** 30 Temmuz 2026  
**İncelenen depo:** `D:\Müşteri İşleri\Pardus app\pardus-paylasim`  
**İncelenen belgeler:** `docs/MASTER_PLAN_uzaktan-kontrol.md`, `docs/basvuru/TEKNOFEST_BASVURU_RAPORU_V3.doc` (denetim sırasında repo kökündeydi; 2026-08-02'de taşındı), `.claude/RESUME.md`

## 1. Yönetici özeti

Mevcut proje önemli miktarda çalışan temel kod ve birim test içeriyor; fakat **yayına hazır, kusursuz, bütün protokolleri çapraz platformda doğrulanmış veya güvenli bir AnyDesk/TeamViewer alternatifi değildir**. Mevcut durumda yayın kararı **NO-GO** olmalıdır.

En kritik nedenler:

1. `/request_pin` uç noktası bağlantıyı isteyen tarafa PIN’i kendisi veriyor. Bu, PIN’i bant dışı kullanıcı onayı olmaktan çıkarıyor.
2. “Güvenilen cihaz” doğrulaması kriptografik değil. Tarayıcının ürettiği, taklit edilebilir bir metin kimliği bir başarılı PIN’den sonra kalıcı erişim anahtarına dönüşüyor.
3. TLS kurulamazsa sunucu düz HTTP ile devam ediyor. Güvenlik özelliği başarısız olduğunda servis kapanmadığı için davranış fail-closed değil.
4. Normal dosya aktarımı ve bağımsız pano aktarımı varsayılan olarak şifresiz ve eş kimliği doğrulanmadan çalışıyor.
5. WebRTC teklif/yanıt kodu ICE aday değişimini eksik yapıyor; TURN yok, STUN sunucuları sabit ve haricî. İnternet üzerinden güvenilir bağlantı iddiası doğrulanmış değil.
6. Wayland Portal backend’i tamamlanmış bir backend değil; oturum oluşturma/izin alma/başlatma yapmayan bir stub.
7. Docker düzeni gerçek Windows’u test etmiyor, bir imaj Pardus değil Debian, konteynerlerin çalıştırdığı giriş dosyası mevcut değil ve “Windows agent” uygulamayı hiç başlatmıyor.
8. Güncel test sonucu yeşil değil: tam koleksiyonda **392 testin 382’si geçti, 6’sı atlandı, 4’ü başarısız oldu**. Kapsama yaklaşık **%42**. Ruff **110 hata** raporluyor.
9. Güncel Faz 6–9 kodunun büyük bölümü commit edilmemiş veya izlenmeyen dosya durumunda. Master plan bu fazları içermiyor.
10. `.deb` ve Windows paketleme betikleri güncel kaynak ağacı için kanıt oluşturmuyor; betiklerden bazıları olmayan dosyalara başvuruyor.

Kısa hüküm: Faz 0–1’in önemli bir bölümü ile eski dosya aktarım çekirdeğinde yararlı ve testli bileşenler var. Faz 2’nin fiziksel doğrulaması açık; Faz 3’ün Windows çalışma kanıtı yok; Faz 4 Portal iddiası yanlış; Faz 6–9 için “entegre ve kusursuz” iddiaları kanıtsız.

## 2. Denetim yöntemi

Bu çalışma, önceki sohbet anlatımını kanıt olarak kabul etmedi. Aşağıdaki kaynaklar ayrı ayrı karşılaştırıldı:

- Üç belgenin güncel içeriği ve TEKNOFEST raporunun dört sayfalık PDF görünümü
- Git durumu, commit geçmişi, değişmiş ve izlenmeyen dosyalar
- Kaynak kodda güvenlik ve protokol akışları
- Birim, web ve E2E test koleksiyonu
- Kod kapsamı, sözdizimi, lint ve kurulu bağımlılık tutarlılığı
- Paketleme, CI ve Docker dosyaları
- OWASP, IETF/RFC, W3C, XDG Desktop Portal, Debian, PyInstaller, Microsoft, pytest, Playwright ve Pardus’un birincil belgeleri

Denetimde kullanılan başlıca yerel doğrulamalar:

```text
Git: master, HEAD 769f70f, origin/master'ın 53 commit önünde
Çalışma ağacı: 11 değiştirilmiş + 28 izlenmeyen girdi
compileall: geçti
pip check: geçti
Ruff: 110 hata
Temel suite (E2E ve bozulan web testi hariç): 369 geçti, 6 atlandı
Web viewer testi: 13 geçti, 1 başarısız
Tam koleksiyon: 382 geçti, 6 atlandı, 4 başarısız
Coverage: toplam %42
```

Bu sonuçlar yalnız bu makinedeki mevcut çalışma ağacına aittir. Gerçek Pardus/Windows donanım doğrulaması değildir.

## 3. Belge tutarlılığı

### 3.1 `MASTER_PLAN_uzaktan-kontrol.md`

Belge, erken fazlarda commit hash’leri ve test sayılarıyla güçlü bir iz bırakıyor. Faz 0 ve Faz 1’in pek çok maddesi bu nedenle görece güvenilir.

Ancak:

- Faz 2.2 hâlâ `[ ]`: Windows Chrome ile canlı görüntü ve kontrol doğrulanmamış.
- Faz 1.11 notu, gerçek iki Pardus cihazında X11/Wayland sürüşünün beklediğini açıkça söylüyor.
- Faz 3.4 ve sonraki bazı maddeler commit hash’i olmadan “%100” gibi ifadelerle kapatılmış.
- Faz 6–9 bu güncel master planda yok.
- Belgenin devralma kuralı ilk açık kutudan devam etmeyi söylüyor; bu durumda ilk açık iş Faz 2.2’dir.

Sonuç: Master plan “tüm fazlar tamamlandı” iddiasını desteklemiyor.

### 3.2 `.claude/RESUME.md`

RESUME güncel değil:

- 95 testten ve 45 değişmiş dosyadan söz ediyor.
- i18n, bağımlılık, `.gitignore`, doğrulama ve commit işlerini açık bırakıyor.
- Güncel depo bundan çok daha ileride ve farklı durumda.

Bu belge yalnız tarihsel bağlam olarak tutulmalı; devralma kaynağı olarak kullanılmamalı. Güncel bir `CURRENT_STATE.md` ile değiştirilmesi gerekir.

### 3.3 `docs/basvuru/TEKNOFEST_BASVURU_RAPORU_V3.doc`

Rapor düzgün açılıyor ve dört sayfalık başvuru belgesi olarak görsel bütünlüğe sahip. Fakat teknik iddiaları güncel kaynakla uyuşmuyor.

| Rapordaki iddia | Güncel kanıt | Hüküm |
|---|---|---|
| Dosya ve ekran verisi şifreli P2P aktarılır | Normal dosya modu ve bağımsız pano TCP kanalı TLS olmadan oluşturuluyor | Yanlış/genelleyici |
| PIN kriptografik ve tek kullanımlık güvenlik sağlar | PIN `random.randint` ile üretiliyor ve `/request_pin` ile isteyene dönüyor | Güvenlik modeli bozuk |
| PIN HTTP header ile taşınır | Native istemci header kullanıyor; web viewer birçok akışta PIN’i query string’e koyuyor | Kısmen doğru |
| Kredi kartı Luhn, IBAN doğrulaması yapılır | Kod kart için regex, IBAN için biçim kontrolü yapıyor; Luhn/IBAN mod-97 yok | Yanlış |
| DLP arka planda panoyu otomatik maskeler | Ağ pano gönderimi ham metni gönderiyor; maskeleme ayrı, kullanıcı tarafından çağrılan özellik | Yanlış |
| Tüm mimari Docker Alice–Bob testlerinden geçti | Eski test bazı temel akışları sınar; yeni üç yönlü düzen çalışabilir değil ve protokollerin çoğunu test etmiyor | Kanıtsız |
| Fonksiyonellik %100 güvence altındadır | 4 başarısız test, %42 kapsam, sıfır kapsamlı yeni modüller var | Yanlış ve kaldırılmalı |
| Çalışan güncel `.deb` hazırlanmıştır | Mevcut 44 KB paket 26 Temmuz tarihli ve güncel Faz 6–9’dan önce; web viewer paket girdileri eksik | Güncel kaynak için kanıtsız |
| Tüm bağımlılıkları içeren paket | `Depends` ile sistem paketlerine dayanıyor; self-contained değil | Yanlış ifade |

Rapor, yayın veya başvuru öncesi doğrulanmış özelliklerle yeniden yazılmalı. “%100 güvence”, “tamamen şifreli”, “Luhn/IBAN doğrulama” ve “tüm Docker testleri geçti” ifadeleri mevcut hâliyle kullanılmamalı.

## 4. Doğrulanmış durum

Aşağıdakiler, sınırları belirtilmek koşuluyla doğrulanmıştır:

| Alan | Doğrulanan şey | Kanıt sınırı |
|---|---|---|
| Python kaynakları | Güncel `src/` sözdizimsel olarak derleniyor | Çalışma zamanı/OS doğrulaması değil |
| Bağımlılıklar | Mevcut sanal ortamda `pip check` temiz | Paketleme ortamlarını kapsamaz |
| Eski temel suite | E2E ve web viewer regresyonu hariç 369 test geçiyor | 6 ortam bağımlı test atlandı |
| Kontrol protokol codec’i | Mesaj doğrulama, 512 bayt çerçeve sınırı, maskeli istemci çerçevesi gibi saf parçalar testli | Gerçek fare/klavye sürüşü değil |
| Kontrol consent çekirdeği | Varsayılan kapalı toggle, token, rate cap, tehlikeli VT tuş filtresi mevcut | Per-peer kullanıcı onayı ve granular UI yok |
| Gizli dosya modu | AES-GCM/PBKDF2 tabanlı eski “secret” mod için testler mevcut | Büyük dosyada tüm dosyayı RAM’e alıyor; normal mod plaintext |
| mDNS ve konfigürasyon | Sahte peer temizliği ve TXT alanları için birim testler var | Gerçek çoklu ağ/VLAN doğrulaması değil |
| Windows agent iskeleti | Capability, capture adapter ve bildirim gibi parçalar için headless testler var | Gerçek Windows masaüstü, tray, ACL, input ve EXE testi değil |
| Hassas veri maskeleme | TCKN checksum ve belirli regex maskeleri çalışıyor | Otomatik ağ DLP’si değil; Luhn ve IBAN checksum yok |
| JavaScript | `viewer.js` sözdizimi Node tarafından kabul ediliyor | Tarayıcı davranışı ve CSP uyumu değil |

## 5. Şüpheli veya kanıtsız iddialar

### 5.1 “Tüm testler tamam”

Yanlış. Güncel tam koleksiyon:

- 382 passed
- 6 skipped
- 4 failed

Başarısızlıklar:

1. Web varlık allowlist testi, yeni `file-manager.html` nedeniyle eski “tam üç dosya” beklentisini karşılamıyor.
2. İki E2E test yerel suite içinde Docker DNS adlarını çözmeye çalışıyor.
3. Async E2E testi gerekli plugin/marker ayrımı olmadan toplanıyor.

Ek olarak Ruff 110 hata veriyor ve CI lint adımı bilerek non-gating.

### 5.2 “Windows ↔ Pardus ve Pardus ↔ Pardus Docker’da test edildi”

Kanıtlanmadı:

- `Dockerfile.windows_mock`, Linux tabanlı `python:3.10-slim` imajıdır.
- Bu imaj Windows API, WASAPI, Win32 pano, pynput sürüşü, tray veya EXE’yi doğrulayamaz.
- `windows-agent` servisi `tail -f /dev/null` çalıştırıyor; agent çalışmıyor.
- `Dockerfile.pardus`, yeni düzende `debian:bookworm-slim` kullanıyor.
- Her iki imaj da olmayan `src/pardus_paylasim/agent_main.py` dosyasını çalıştırmaya çalışıyor.
- E2E testleri yalnız iki `/info` isteği ve bir router kayıt mesajı içeriyor.
- Testlerin beklediği `/info` şeması güncel sunucu şemasıyla uyuşmuyor.

Eski iki konteynerli Alice–Bob düzeni bazı mDNS, ekran auth ve dosya aktarım adımlarını deniyor; ancak kendi “Turing” betiği başarısız alt testlerden sonra da sonunda “tümü başarılı” yazabiliyor. Bu da release kanıtı değildir.

### 5.3 “WebRTC, ses ve 60 FPS”

Kanıtlanmadı:

- WebRTC/audio modülleri %0 test kapsamına sahip.
- Tarayıcı `setLocalDescription` sonrasında ICE tamamlanmasını beklemeden eski `offer.sdp` değerini gönderiyor.
- Trickle ICE için aday uç noktası yok.
- TURN yok; Google STUN adresleri sabit.
- Sunucu her HTTP isteğinde event-loop köprüsü kuruyor; peer yaşam döngüsü güvenli biçimde sunucu kapanışına bağlı değil.
- Ekran yakalama event loop üzerinde senkron çalışıyor.
- Audio backend’in Pardus PipeWire/PulseAudio ve Windows WASAPI davranışı doğrulanmamış.
- WebRTC `<video>` öğesinin kontrol koordinatı için `naturalWidth/naturalHeight` kullanılıyor; doğru özellikler `videoWidth/videoHeight`.

### 5.4 “Güvenilen cihazlar ve katılımsız erişim”

Mevcut tasarım güvenli değildir:

- Cihaz “public_key” alanı gerçekte doğrulanmamış bir metin ID’dir.
- Tarayıcı ID’yi `Math.random()` ve `localStorage` ile üretir.
- Bir başarılı PIN’den sonra istemcinin verdiği ID otomatik olarak kalıcı güven listesine eklenir.
- Sonraki erişimde imza veya özel anahtar sahipliği ispatı yoktur.
- Süre sonu, yetki kapsamı, güvenli anahtar saklama ve kapsamlı iptal akışı yoktur.

Bu özellik düzeltilene kadar tamamen kapalı olmalıdır.

### 5.5 “Wayland Portal backend tamam”

Yanlış. `PortalBackend` yalnız portal nesnesini buluyor:

- `CreateSession` yok
- `SelectDevices` yok
- `Start` yok
- portal response sinyalleri yok
- session handle hiçbir zaman oluşturulmuyor
- `close()` oturumu kapatmıyor

Bu backend seçildiğinde sessizce hiçbir şey yapmama riski taşıyor.

### 5.6 “Global ID / internet erişimi”

Rendezvous bileşenleri:

- Uygulamanın normal yaşam döngüsüne bağlı değil.
- `ws://` plaintext çalışıyor.
- Kimlik doğrulama ve eş onayı yok.
- 9 haneli ID `random.randint` ile üretiliyor.
- Mesaj boyutu, hız, kayıt süresi ve abuse kontrolleri yok.
- TURN/relay yok.

Bu kod yalnız deneysel prototip olarak etiketlenmeli ve varsayılan build’den çıkarılmalıdır.

## 6. Güvenlik bulguları

### P0 — Yayını engelleyen bulgular

#### P0.1 PIN’in istemciye geri verilmesi

`stream_server.py` içindeki unauthenticated `/request_pin`, aynı istemci için PIN üretip yanıtlıyor. PIN’i isteyen ile PIN’i alan aynı taraf olduğu için doğrulamanın güvenlik değeri kalmıyor.

Gerekli davranış:

- PIN yalnız host ekranında gösterilmeli.
- Bağlantı talebi hostta açıkça onaylanmalı.
- PIN `secrets` ile, kısa TTL ve tek kullanım ile üretilmeli.
- PIN eş kimliğine ve pairing transcript’ine bağlanmalı.
- Sunucu PIN’i hiçbir API yanıtında döndürmemeli.

#### P0.2 Kriptografik olmayan trusted-device geçişi

`X-Pardus-Device-Id` sahibi olmak unattended erişim için yeterli. Bu kimlik imzalı challenge ile kanıtlanmıyor.

Gerekli davranış:

- İstemci gerçek anahtar çifti üretmeli.
- Sunucu nonce göndermeli; istemci nonce + transcript’i imzalamalı.
- Host explicit pairing onayı vermeden kayıt yapılmamalı.
- Saklanan kayıt yalnız public key/fingerprint, izin kapsamı, oluşturma/son kullanım/süre sonu olmalı.
- Özel anahtar OS güvenli deposunda veya en az güvenli dosya ACL’lerinde tutulmalı.

#### P0.3 TLS başarısızken plaintext devam

TLS kurulumu hata verdiğinde `tls_enabled=False` ile HTTP devam ediyor. Uygulama güvenli modda açılmışsa servis başlamamalı.

Gerekli davranış:

- `require_tls=True` varsayılanı
- sertifika/anahtar kurulamazsa bind etmeden hata
- plaintext yalnız açıkça adlandırılmış `--insecure-development-only`, loopback bind ve belirgin uyarıyla
- production paketinde insecure mod kapalı

#### P0.4 Dosya ve pano kanallarında plaintext/kimliksiz erişim

Ana pencere `FileReceiverServer(...)` ve `ClipboardSyncServer()` nesnelerini TLS context olmadan kuruyor. Agent dosya alıcısı da TLS’siz. Agent onay penceresinde istisna olursa `True` dönerek otomatik kabul ediyor.

Gerekli davranış:

- güvenli session dışında dinleme yok
- TLS ve eş kimliği zorunlu
- onay UI hatası = red
- ayrı ham TCP protokolleri ya kaldırılmalı ya da aynı kimlikli session katmanına bağlanmalı
- normal ve “secret” mod ayrımı güvenli/tehlikeli mod ayrımına dönüşmemeli

#### P0.5 Güvensiz rendezvous etkinleştirme riski

Plaintext, auth’suz router internete açılırsa kontrol/SDP yönlendirme saldırı yüzeyi oluşturur. Release build’de kapalı tutulmalı.

### P1 — Yüksek öncelikli bulgular

#### P1.1 WebSocket handshake ve oturum

İyi taraflar: masked frame zorunluluğu, küçük payload tavanı, token, rate cap ve kill-switch çekirdeği var.

Eksikler:

- `Origin` allowlist doğrulaması yok.
- `Upgrade`, `Connection`, `Sec-WebSocket-Version: 13` kontrolleri eksik.
- Token IP’ye bağlı; NAT arkasındaki istemciler çakışabilir.
- idle ve absolute session expiry yok.
- her gelen bağlantı için host tarafında eş kimliğiyle consent yok; global toggle açıkken grant otomatik.
- granular izinler kodda var ama UI tarafından ayarlanmıyor; hepsi varsayılan açık.
- enjeksiyon exception’ı event loop’u düşürebilir.

#### P1.2 Dosya aktarımında DoS ve bütünlük

- `name_len` ve `payload_size` için yeterli üst sınır yok.
- Alıcı tüm payload’ı RAM’e alıyor.
- Web upload 1 GB’a kadar tüm içeriği RAM’e alıyor.
- atomik geçici dosya + fsync + rename yok.
- normal modda authenticated integrity yok.
- version/magic/session ID/hash/replay bilgisi yok.
- symlink/TOCTOU güvenliği tamam değil.
- ACK tek bayt ve kimliksiz.

#### P1.3 Dosya yöneticisinde sandbox ve CSP

- Yol kontrolü `normpath` + string prefix kullanıyor; symlink kök dışına çıkabilir.
- Dizin taraması symlink takip edebilir.
- `file-manager.html` inline `<style>` ve `<script>` içeriyor; sunucunun `style-src 'self'; script-src 'self'` CSP’si bunları bloklar.
- PIN URL query’sinde.
- Dosya adları `Content-Disposition` içinde güvenli RFC biçimiyle kodlanmıyor.

#### P1.4 WebRTC sinyalleşme/ICE/lifecycle

- ICE candidate exchange tamamlanmalı.
- LAN modu varsayılan haricî STUN’sız olmalı.
- Internet modu için yapılandırılabilir, kimlik doğrulamalı TURN gerekir.
- Peer’ler tek sahipli event loop ve deterministik teardown altında yönetilmeli.
- capture/audio bounded queue ve backpressure ile event loop dışına alınmalı.
- başarı yalnız `connected` durumu ve gerçek media akışı ile raporlanmalı.

#### P1.5 Paketleme ve CI

- `scripts/build_deb.sh`, olmayan `setup.py` dosyasını çağırıyor.
- `scripts/build_exe.ps1`, olmayan `agent_main.py` ve ikon dosyasına başvuruyor.
- `agent.spec` web assets, aiortc/av/soundcard/numpy ve yeni modülleri toplamıyor.
- Debian paketleme web viewer’ı `/usr/share/pardus-paylasim/web-viewer` altına kurmuyor.
- mevcut `.deb` güncel kaynak öncesi.
- GitHub workflow yalnız `main` branch’ini dinliyor; depo `master`.
- Ruff non-gating; Debian integration `continue-on-error`/`allow_failure`.

### P2 — Orta öncelikli bulgular

#### P2.1 Erişilebilirlik

Ana viewer’da bazı ARIA etiketleri eklenmiş; ancak tam WCAG kanıtı yok.

Eksikler:

- Dosya yöneticisinde tıklanabilir `<span>` öğeleri klavye erişilebilir değil.
- Durum ve hata mesajları `role=status`/`aria-live` ile sunulmuyor.
- Drag-and-drop için eşdeğer klavye yolu doğrulanmamış.
- Odak sırası, focus-not-obscured, kontrast, zoom/reflow ve 24 CSS px target testleri yok.
- Uzak ekran kontrol alanının ekran okuyucu açıklaması ve mod değişikliği anonsları sınırlı.
- GTK uygulaması Orca ile, Windows agent ise NVDA ile test edilmemiş.

#### P2.2 Audit ve gizlilik

Yeni audit logger:

- yalnız birkaç olayı yazıyor
- dosya izinleri, rotation, retention ve tamper evidence yok
- başarısız auth, consent, revoke, download, clipboard ve trusted-device değişimlerini bütünlüklü kaydetmiyor
- sohbet içeriğini loglayabiliyor

Loglarda PIN, token, pano içeriği, sohbet içeriği ve tam dosya yolu bulunmamalı.

#### P2.3 DLP iddiası

TCKN doğrulaması faydalı. Ancak:

- kartta Luhn yok
- IBAN mod-97 yok
- otomatik gönderim öncesi maskeleme/engelleme yok
- politika “uyar / maskele / gönderme” şeklinde seçilebilir değil
- yanlış pozitif/negatif corpus testleri yetersiz

## 7. Güncel iyi uygulamalarla karşılaştırma

| Alan | Güncel iyi uygulama | Mevcut durum | Öncelikli değişiklik |
|---|---|---|---|
| WebSocket | WSS, Origin allowlist, handshake doğrulama, auth, session expiry, rate/size/backpressure, hassas içeriksiz audit | Kısmi | Origin + session + per-peer consent |
| WebRTC | DTLS-SRTP; güvenli signaling; ICE aday değişimi; consent freshness; doğrulanabilir eş kimliği; gerektiğinde auth’lu TURN | Eksik | Sinyalleşmeyi ve kimliği yeniden kur |
| Dosya yükleme | Yetkili kullanıcı, boyut/ad/tür allowlist, generated storage name, webroot dışı, streaming, malware/CDR opsiyonu, CSRF | Eksik | Stream-to-temp + quota + atomik commit |
| Dosya indirme | Sandbox, symlink-safe open, opaque ID, authorization, rate limit | Eksik | Path yerine sunucu üretimli dosya ID |
| Wayland | Portal `CreateSession → SelectDevices → Start`; yalnız verilen capability ile event; session close | Stub | Gerçek portal/libei veya unavailable |
| Erişilebilirlik | WCAG 2.2 AA; keyboard; focus; status; target; drag alternatifi; axe + manuel test | Kısmi | Playwright+axe ve Orca/NVDA matrisi |
| Debian paket | Debian Policy, gerçek bağımlılıklar, install/upgrade/remove testleri, reproducible build | Eksik | Tek kanonik debhelper yolu |
| Windows paket | Windows’ta native build/test, data ve hidden import toplama, Authenticode + timestamp | Eksik | Windows runner/VM ve imzalı artefact |
| CI | Zorunlu lint/unit/security/package/E2E gate; marker ayrımı; gerçek OS matrisi | Eksik | Soft gate’leri kaldır |
| Supply chain | SBOM, SHA-256, provenance/attestation, doğrulama talimatı | Yok | Release pipeline’a ekle |

Birincil kaynaklar:

- [OWASP WebSocket Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html)
- [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)
- [RFC 8827 — WebRTC Security Architecture](https://www.rfc-editor.org/rfc/rfc8827.html)
- [RFC 8445 — ICE](https://www.rfc-editor.org/rfc/rfc8445.html)
- [RFC 8656 — TURN](https://www.rfc-editor.org/rfc/rfc8656.html)
- [W3C WebRTC](https://www.w3.org/TR/webrtc/)
- [XDG Desktop Portal RemoteDesktop](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.RemoteDesktop.html)
- [W3C WCAG 2.2](https://www.w3.org/TR/WCAG22/)
- [Playwright Accessibility Testing](https://playwright.dev/docs/accessibility-testing)
- [pytest markers](https://docs.pytest.org/en/latest/how-to/mark.html)
- [Debian Policy Manual](https://www.debian.org/doc/debian-policy/)
- [SOURCE_DATE_EPOCH](https://reproducible-builds.org/docs/source-date-epoch/)
- [PyInstaller Usage](https://pyinstaller.org/en/stable/usage.html)
- [Microsoft Authenticode/SignTool](https://learn.microsoft.com/en-us/windows/win32/seccrypto/using-signtool-to-sign-a-file)
- [Windows container compatibility](https://learn.microsoft.com/en-us/virtualization/windowscontainers/deploy-containers/version-compatibility)
- [GitHub artifact attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations)
- [Pardus sürüm yönetimi](https://pardus.org.tr/en/version-management/)

## 8. Pardus destek matrisi

“Pardus 20 ve üstü” teknik olarak doğru bir sürüm hedefi değil; resmi ana sürüm çizgisi 19, 21, 23 ve 25 şeklinde ilerliyor.

30 Temmuz 2026 itibarıyla Pardus’un resmi tablosu:

- Pardus 25: destekli
- Pardus 23: destekli
- Pardus 21: 1 Mayıs 2025’te ömrünü tamamlamış

Ayrıca Pardus 21’in Debian 11/Bullseye tabanı varsayılan Python 3.9 sağlıyor; proje `requires-python = ">=3.10"` diyor. Debian’ın resmi paket kayıtlarında [Bullseye `python3` paketi 3.9.x](https://packages.debian.org/bullseye/python3), [Bookworm `python3` paketi ise 3.11.x](https://packages.debian.org/bookworm/python3) çizgisinde. Bu nedenle mevcut paket Pardus 21 ile doğal olarak uyumlu değildir.

Önerilen ürün politikası:

1. Zorunlu release matrisi: Pardus 23 ve Pardus 25, XFCE + GNOME.
2. X11 ve Wayland ayrı doğrulama satırları.
3. Pardus 21 yalnız “legacy/best effort”; ya Python 3.9’a bilinçli backport ya da bağımsız runtime paketi gerekir.
4. Destek dışı sürümler için “tam uyumlu” iddiası kullanılmamalı.

## 9. Önerilen hedef mimari

### 9.1 İki ayrı çalışma profili

**LAN güvenli profil — varsayılan**

- Haricî STUN/TURN/rendezvous yok
- TLS zorunlu
- İlk eşleşmede host onayı ve kısa kimlik doğrulama dizisi
- Ekran, kontrol, dosya ve pano aynı authenticated session kapsamına bağlı

**Internet erişim profili — açıkça opt-in**

- TLS/WSS güvenli signaling
- Kimliği doğrulanmış cihaz anahtarları
- Yapılandırılabilir STUN
- Kısa ömürlü kimlik bilgili TURN/TLS
- Abuse/rate/quota/retention
- Eşin ve relay kullanımının görünür UI göstergesi

### 9.2 Tek kimlik ve oturum modeli

- Host/agent kalıcı cihaz anahtar çifti
- Browser için WebCrypto non-extractable anahtar
- İlk pairing’de explicit host consent
- Transcript’e bağlı kısa doğrulama dizisi veya incelenmiş PAKE yaklaşımı
- Sonraki bağlantıda nonce imzasıyla özel anahtar sahipliği
- Kısa ömürlü session capability token’ları
- Her capability ayrı: `view`, `mouse`, `keyboard`, `clipboard-read`, `clipboard-write`, `file-upload`, `file-download`, `audio`
- Tokenlar IP’ye değil bağlantı/cihaz/session kimliğine bağlı
- Anlık iptal + idle/absolute expiry

### 9.3 Aktarım birleştirmesi

Ayrı plaintext TCP dosya/pano servisleri yerine:

- Aynı TLS sunucusu üzerinde authenticated HTTPS/WSS
- Streaming request/response
- Server-generated opaque file ID
- Geçici dosyaya yazma, boyut/hash doğrulama, atomik rename
- Bounded memory
- Consent ve quota
- Pano için açık yön ve boyut politikası

### 9.4 Deneysel özellik izolasyonu

Şu özellikler güvenlik ve E2E gate’leri geçene kadar varsayılan kapalı:

- trusted/unattended access
- rendezvous/global ID
- Internet/TURN
- WebRTC audio
- Wayland Portal backend
- remote file browser
- WOL

`/info` ve UI, özelliği “available / unavailable / experimental / verified” olarak dürüstçe göstermeli.

## 10. Uygulama önceliği

1. **P0 containment:** PIN uç noktası, auto-trust, plaintext fallback ve fail-open consent’i kapat.
2. **Kimlik modeli:** gerçek anahtar sahipliği ve explicit pairing.
3. **Transport birleştirme:** dosya/pano dahil TLS + session auth.
4. **WebSocket/control hardening:** Origin, expiry, per-peer consent, granular capability.
5. **Dosya sistemi güvenliği:** streaming, quota, symlink-safe open, atomik yazma.
6. **WebRTC signaling/ICE/TURN/lifecycle:** önce video; audio ayrı gate.
7. **Gerçek Wayland ve Windows backend doğrulaması.**
8. **WCAG 2.2 AA ve native assistive technology testleri.**
9. **Paketleme ve supply-chain.**
10. **Gerçek OS/E2E matrisi ve yalnız kanıta dayalı dokümantasyon.**

## 11. Release için asgari çıkış kriterleri

Bir release adayı ancak aşağıdakilerin tamamında yeşil olabilir:

- Çalışma ağacı kontrollü ve tüm release girdileri commitli
- `compileall`, Ruff, security scan ve dependency audit başarılı
- Unit/integration suite sıfır fail, beklenmeyen skip yok
- Toplam kapsam en az %80; auth/control/transfer/path modüllerinde en az %90
- PIN hiçbir response/query/log içinde yok
- TLS yoksa production servis başlamıyor
- Trusted access imzalı challenge olmadan çalışmıyor
- Dosya/pano plaintext kabul etmiyor
- WebSocket Origin negatif testleri geçiyor
- Oversize, traversal, symlink, replay, brute force ve disconnect testleri geçiyor
- Pardus 23 ve 25 paketleri gerçek imaj/VM üzerinde install-launch-upgrade-remove testini geçiyor
- Windows agent gerçek Windows runner/VM üzerinde build, launch, tray, capture ve dosya consent testini geçiyor
- Chromium + Firefox web E2E ve axe sonuçları temiz
- X11 ve Wayland doğrulaması ayrı raporlanıyor
- `.deb` ve `.exe` için SHA-256, SBOM ve provenance üretiliyor
- EXE Authenticode ile imzalanıp timestamp doğrulanıyor
- Test raporu commit SHA, ortam, komut, exit code ve artefact hash içeriyor
- Manuel testler otomatik test gibi gösterilmiyor
- “%100 güvenli/kusursuz” gibi kanıtlanamaz ifadeler belgelerden çıkarılmış

## 12. Nihai karar

Proje çöpe atılacak durumda değildir; güçlü bir prototip ve testli çekirdek barındırıyor. Fakat son fazlarda hızla eklenen özellikler, güvenlik ve doğrulama mimarisinin önüne geçmiş. En doğru yaklaşım yeni özellik eklemeyi durdurmak, deneysel modülleri varsayılan kapatmak ve önce P0 kimlik/transport sorunlarını çözmektir.

Yanındaki `CLAUDE_CODE_FAIL_CLOSED_UYGULAMA_PROMPTU.md` dosyası bu denetimi aşamalı, test-gated ve fail-closed bir uygulama planına dönüştürür.
