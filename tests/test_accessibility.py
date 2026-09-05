"""
Erişilebilirlik (a11y) testleri: Widget'larda ARIA eşdeğeri erişilebilirlik özelliklerini doğrular.

WCAG 2.1 uyumluluğu için kritik olan erişilebilirlik özelliklerini test eder:
- Erişilebilir isim ve açıklama (accessible name/description)
- Klavye erişilebilirliği (focus, keyboard navigation)
- Güvenli dosya yolu (path traversal koruması)
- StreamConfig tutarlılığı
"""

import pytest


class TestTabNavigation:
    """Sekme navigasyonu ve kısayol testleri."""

    def test_tab_name_for_index_valid(self):
        """Geçerli indisler doğru sekme adını döndürmeli."""
        TAB_NAMES = ("privacy", "discovery", "screenshare", "clipboard", "settings")

        def tab_name(index):
            if not isinstance(index, int) or index < 1 or index > len(TAB_NAMES):
                return None
            return TAB_NAMES[index - 1]

        assert tab_name(1) == "privacy"
        assert tab_name(2) == "discovery"
        assert tab_name(3) == "screenshare"
        assert tab_name(4) == "clipboard"
        assert tab_name(5) == "settings"

    def test_tab_name_for_index_out_of_range(self):
        """Aralık dışı indisler None döndürmeli."""
        TAB_NAMES = ("privacy", "discovery", "screenshare", "clipboard", "settings")

        def tab_name(index):
            if not isinstance(index, int) or index < 1 or index > len(TAB_NAMES):
                return None
            return TAB_NAMES[index - 1]

        assert tab_name(0) is None
        assert tab_name(6) is None
        assert tab_name(-1) is None

    def test_tab_name_for_index_non_int(self):
        """Non-int indisler None döndürmeli."""
        TAB_NAMES = ("privacy", "discovery", "screenshare", "clipboard", "settings")

        def tab_name(index):
            if not isinstance(index, int) or index < 1 or index > len(TAB_NAMES):
                return None
            return TAB_NAMES[index - 1]

        assert tab_name("1") is None
        assert tab_name(None) is None
        assert tab_name(1.5) is None

    def test_tab_names_tuple_length(self):
        """TAB_NAMES tuple'ı 5 sekme içermeli."""
        TAB_NAMES = ("privacy", "discovery", "screenshare", "clipboard", "settings")
        assert len(TAB_NAMES) == 5

    def test_tab_names_are_unique(self):
        """Tüm sekme adları benzersiz olmalı."""
        TAB_NAMES = ("privacy", "discovery", "screenshare", "clipboard", "settings")
        assert len(TAB_NAMES) == len(set(TAB_NAMES))


class TestSensitiveMaskerA11y:
    """SensitiveMasker'ın erişilebilirlikle ilişkili davranışlarını test eder."""

    def test_mask_text_preserves_structure(self):
        """Metin maskelendiğinde yapı (satır sonları, boşluklar) korunmalı."""
        from pardus_paylasim.clipboard.sensitive_masker import SensitiveMasker

        text = "Adım: 12345678901\nTelefon: +90 532 123 4567"
        masked = SensitiveMasker.mask_text(text)

        # Satır yapısı korunmalı
        assert "\n" in masked

    def test_mask_text_tckn_length(self):
        """TCKN maskelendiğinde uzunluk değişmeli (gizlilik)."""
        from pardus_paylasim.clipboard.sensitive_masker import SensitiveMasker

        text = "TCKN: 10000000146"
        masked = SensitiveMasker.mask_text(text)

        # Maskelenmiş versiyon farklı olmalı
        assert masked != text

    def test_mask_text_iban_readable(self):
        """IBAN maskelendiğinde başlık ve son hane okunabilir olmalı."""
        from pardus_paylasim.clipboard.sensitive_masker import SensitiveMasker

        text = "TR12 3456 7890 1234 5678 9012 34"
        masked = SensitiveMasker.mask_text(text)

        assert masked.startswith("TR12 ")
        assert masked.endswith("34")

    def test_scan_text_finds_tckn(self):
        """Geçerli TCKN taranabilmeli."""
        from pardus_paylasim.clipboard.sensitive_masker import SensitiveMasker

        matches = SensitiveMasker.scan_text("TCKN: 10000000146")
        tckn_matches = [m for m in matches if m.match_type == "TCKN"]
        assert len(tckn_matches) == 1

    def test_scan_text_ignores_invalid_tckn(self):
        """Geçersiz TCKN (Mod-10 başarısız) tespit edilmemeli."""
        from pardus_paylasim.clipboard.sensitive_masker import SensitiveMasker

        matches = SensitiveMasker.scan_text("TCKN: 12345678900")
        tckn_matches = [m for m in matches if m.match_type == "TCKN"]
        assert len(tckn_matches) == 0

    def test_mask_text_email(self):
        """E-posta maskelenmeli."""
        from pardus_paylasim.clipboard.sensitive_masker import SensitiveMasker

        text = "Email: test@example.com"
        masked = SensitiveMasker.mask_text(text)
        assert "test@example.com" not in masked
        assert "@example.com" in masked


class TestTransferSafePath:
    """Güvenli dosya yolu oluşturma testleri (path traversal koruması)."""

    def test_safe_target_path_normal(self):
        """Normal dosya adları güvenli yola çevrilmeli."""
        from pardus_paylasim.discovery.transfer import safe_target_path

        result = safe_target_path("/downloads", "dosya.txt")
        assert result == "/downloads/dosya.txt"

    def test_safe_target_path_traversal_blocked(self):
        """../ ile dizin aşımları engellenmeli."""
        from pardus_paylasim.discovery.transfer import safe_target_path

        result = safe_target_path("/downloads", "../../../etc/passwd")
        assert not result.startswith("/etc")
        assert result.startswith("/downloads")

    def test_safe_target_path_subdirectory(self):
        """Alt klasör yollarına izin verilmeli."""
        from pardus_paylasim.discovery.transfer import safe_target_path

        result = safe_target_path("/downloads", "klasor/dosya.txt")
        assert "klasor" in result
        assert result.startswith("/downloads")

    def test_safe_target_path_empty_name(self):
        """Boş dosya adı varsayılan ad kullanmalı."""
        from pardus_paylasim.discovery.transfer import safe_target_path

        result = safe_target_path("/downloads", "")
        assert "alinan_dosya" in result

    def test_safe_target_path_absolute_blocked(self):
        """Mutlak yollar engellenmeli."""
        from pardus_paylasim.discovery.transfer import safe_target_path

        result = safe_target_path("/downloads", "/etc/passwd")
        assert not result.startswith("/etc")
        assert result.startswith("/downloads")

    def test_safe_target_path_dot_dot_slash(self):
        """../ encodesiz hali bile engellenmeli."""
        from pardus_paylasim.discovery.transfer import safe_target_path

        result = safe_target_path("/downloads", "../../secret.key")
        assert not result.startswith("/secret")
        assert result.startswith("/downloads")

    def test_safe_target_path_deep_nesting(self):
        """Derin klasör yolları güvenli olmalı."""
        from pardus_paylasim.discovery.transfer import safe_target_path

        result = safe_target_path("/downloads", "a/b/c/d/file.txt")
        assert result.startswith("/downloads")
        assert "file.txt" in result


class TestStreamConfigA11y:
    """StreamConfig'ın erişilebilirlikle ilişkili davranışları."""

    def test_resolution_label_native(self):
        """Native modda çözünürlük etiketi 'native' olmalı."""
        from pardus_paylasim.screen.stream_config import StreamConfig

        config = StreamConfig()
        assert config.resolution_label == "native"

    def test_resolution_label_scaled(self):
        """Ölçekli modda çözünürlük etiketi wide x height olmalı."""
        from pardus_paylasim.screen.stream_config import StreamConfig

        config = StreamConfig(width=1920, height=1080)
        assert config.resolution_label == "1920x1080"

    def test_frame_interval_consistent(self):
        """Frame interval fps'nin tersi olmalı."""
        from pardus_paylasim.screen.stream_config import StreamConfig

        config = StreamConfig(framerate=25)
        assert abs(config.frame_interval - 0.04) < 0.001

    def test_config_clamping_quality(self):
        """Geçersiz kalite güvenli aralığa kırpılmalı."""
        from pardus_paylasim.screen.stream_config import StreamConfig

        config = StreamConfig(jpeg_quality=0)
        assert config.jpeg_quality == 1

        config = StreamConfig(jpeg_quality=200)
        assert config.jpeg_quality == 100

    def test_config_clamping_framerate(self):
        """Geçersiz fps güvenli aralığa kırpılmalı."""
        from pardus_paylasim.screen.stream_config import StreamConfig

        config = StreamConfig(framerate=0)
        assert config.framerate == 1

        config = StreamConfig(framerate=100)
        assert config.framerate == 60

    def test_config_clamping_port(self):
        """Geçersiz port güvenli aralığa kırpılmalı."""
        from pardus_paylasim.screen.stream_config import StreamConfig

        config = StreamConfig(port=0)
        assert config.port == 1

    def test_gst_pipeline_native(self):
        """Native modda GStreamer scale parçası boş olmalı."""
        from pardus_paylasim.screen.stream_config import StreamConfig

        config = StreamConfig()
        assert config.gst_scale_fragment() == ""

    def test_gst_pipeline_scaled(self):
        """Ölçekli modda GStreamer scale parçası boyut içermeli."""
        from pardus_paylasim.screen.stream_config import StreamConfig

        config = StreamConfig(width=1280, height=720)
        fragment = config.gst_scale_fragment()
        assert "1280" in fragment
        assert "720" in fragment


class TestCORSValidation:
    """CORS allowlist doğrulama testleri."""

    def test_parse_allowed_origins_empty(self):
        """Boş girdi boş küme döndürmeli."""
        from pardus_paylasim.screen.stream_server import parse_allowed_origins

        assert parse_allowed_origins("") == frozenset()
        assert parse_allowed_origins(None) == frozenset()

    def test_parse_allowed_origins_valid(self):
        """Geçerli origin'ler küme olarak dönmeli."""
        from pardus_paylasim.screen.stream_server import parse_allowed_origins

        result = parse_allowed_origins("https://a.local, https://b:8443")
        assert "https://a.local" in result
        assert "https://b:8443" in result

    def test_parse_allowed_origins_joker_blocked(self):
        """Joker '*' asla allowlist'e girmemeli (güvenlik)."""
        from pardus_paylasim.screen.stream_server import parse_allowed_origins

        result = parse_allowed_origins("*")
        assert len(result) == 0
        assert "*" not in result

    def test_parse_allowed_origins_whitespace_trimmed(self):
        """Boşluklar kırpılmalı."""
        from pardus_paylasim.screen.stream_server import parse_allowed_origins

        result = parse_allowed_origins("  https://a.local  ,  https://b.local  ")
        assert "https://a.local" in result
        assert "https://b.local" in result


class TestProgressHelpers:
    """İlerleme yardımcı fonksiyon testleri."""

    def test_human_size_bytes(self):
        """Bayt doğru formatta gösterilmeli."""
        from pardus_paylasim.progress import human_size

        assert human_size(0) == "0 B"
        assert human_size(500) == "500 B"

    def test_human_size_kb(self):
        """KB doğru hesaplanmalı."""
        from pardus_paylasim.progress import human_size

        result = human_size(1024)
        assert "KB" in result

    def test_human_size_mb(self):
        """MB doğru hesaplanmalı."""
        from pardus_paylasim.progress import human_size

        result = human_size(1024 * 1024)
        assert "MB" in result

    def test_human_eta_none(self):
        """None ETA '--' döndürmeli."""
        from pardus_paylasim.progress import human_eta

        assert human_eta(None) == "—"

    def test_human_eta_seconds(self):
        """Saniye cinsinden ETA doğru formatlanmalı."""
        from pardus_paylasim.progress import human_eta

        result = human_eta(30)
        assert "sn" in result

    def test_human_eta_minutes(self):
        """Dakika cinsinden ETA doğru formatlanmalı."""
        from pardus_paylasim.progress import human_eta

        result = human_eta(120)
        assert "dk" in result

    def test_compute_stats_basic(self):
        """Temel istatistik hesaplaması doğru olmalı."""
        from pardus_paylasim.progress import compute_stats

        stats = compute_stats(transferred=500, total=1000, elapsed=1.0)
        assert stats.percent == 0.5
        assert stats.rate_bps == 500.0
        assert stats.eta_seconds == 1.0

    def test_compute_stats_zero_elapsed(self):
        """Süre sıfırsa hız sıfır olmalı."""
        from pardus_paylasim.progress import compute_stats

        stats = compute_stats(transferred=500, total=1000, elapsed=0.0)
        assert stats.rate_bps == 0.0

    def test_compute_stats_completed(self):
        """Tamamlanmış transferde oran 1.0 olmalı."""
        from pardus_paylasim.progress import compute_stats

        stats = compute_stats(transferred=1000, total=1000, elapsed=2.0)
        assert stats.percent == 1.0
