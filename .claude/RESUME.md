# RESUME — Pardus Paylaşım kalan iş

**Durum:** İş bitmiş, commit'siz. 45 dosya değişik (+1867/−387) + ~15 yeni dosya. Test: 95 pass, 5 skip (Windows GTK/qrcode yok). Yeni modüller entegre.
**Python:** `py` (3.14 + pytest 9.1.1). NOT `python` (=Inkscape, pytest yok).
**Elektrik kesintisi:** veri kaybı yok, dosyalar diskte.

## Kalan adımlar (sıra)

- [ ] **1. i18n sarma** — window.py 14 ham TR string `_()` sar. Satır ~887,974,978,987,1053,1487,1490,1502,1507,1525,1542,1554,1559,1565. Emoji dışta metin içte. Davranış-koruyucu. Kontrol: `grep -rn -E 'set_(label|title|text|tooltip_text|placeholder_text)\("[^"]*[çğıöşüÇĞİÖŞÜ]' src/ | grep -v '_('` → 0.
- [ ] **2. katalog** (blok: 1) — .pot güncelle + tr.po (kaynak birebir) + en.po (İng). .mo derle → locale/{tr,en}/LC_MESSAGES/. xgettext yoksa `py -m msgfmt` / msgfmt.py fallback.
- [ ] **3. packaging dep** — debian/control Recommends'e `python3-qrcode`. build_deb.py Recommends'e ekle. bleak src'de YOK (kaldırılmış, dep senkron).
- [ ] **4. gitignore** — __pycache__, *.pyc, .claude/, tests/docker_integration/shared/received.json ignore kontrol/ekle.
- [ ] **5. doğrulama** (blok: 1,2,3,4) — `py -m pytest tests/ -q` → 95 pass 5 skip. Regresyon yok.
- [ ] **6. commit** (blok: 5) — A: altyapı (logging/i18n/config/debian/gschema/locale/CI/pyproject). B: özellik (clipboard_sync/history/qr/notifications/progress/tls + 9 test + window/transfer/ui). Doküman ayrı ya da B.

## Pardus host (kullanıcı koşar, Windows imkansız)
- [ ] 7. `dpkg-buildpackage -b` → deb. `tests/run_docker_test.sh`. `gsettings get tr.org.pardus.paylasim mdns-visible`. `LANG=en_US.UTF-8` İng UI.
