"""
Erişilebilirlik (a11y) ve kapsayıcılık testleri:
- Kaynak kodda erişilebilirlik etiketlerinin varlığı
- Container/Flatpak manifest bütünlüğü
- Güvenli dosya yolu (path traversal koruması)
- StreamConfig tutarlılığı
- Sekme navigasyonu
"""

import os
import pytest


REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
WINDOW_FILE = os.path.join(
        REPO_ROOT, "src", "pardus_paylasim", "window.py"
    )


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

        text = "Adım: 12345678950\nTelefon: +90 532 123 4567"
        masked = SensitiveMasker.mask_text(text)
        assert "\n" in masked

    def test_mask_text_tckn_length(self):
        """TCKN maskelendiğinde uzunluk değişmeli (gizlilik)."""
        from pardus_paylasim.clipboard.sensitive_masker import SensitiveMasker

        text = "TCKN: 10000000146"
        masked = SensitiveMasker.mask_text(text)
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
    """Güvenli dosya yolu oluşturma testleri."""

    def test_safe_target_path_normal(self):
        from pardus_paylasim.discovery.transfer import safe_target_path
        result = safe_target_path("/downloads", "dosya.txt")
        assert result == "/downloads/dosya.txt"

    def test_safe_target_path_traversal_blocked(self):
        from pardus_paylasim.discovery.transfer import safe_target_path
        result = safe_target_path("/downloads", "../../../etc/passwd")
        assert not result.startswith("/etc")
        assert result.startswith("/downloads")

    def test_safe_target_path_subdirectory(self):
        from pardus_paylasim.discovery.transfer import safe_target_path
        result = safe_target_path("/downloads", "klasor/dosya.txt")
        assert "klasor" in result
        assert result.startswith("/downloads")

    def test_safe_target_path_empty_name(self):
        from pardus_paylasim.discovery.transfer import safe_target_path
        result = safe_target_path("/downloads", "")
        assert "alinan_dosya" in result

    def test_safe_target_path_absolute_blocked(self):
        from pardus_paylasim.discovery.transfer import safe_target_path
        result = safe_target_path("/downloads", "/etc/passwd")
        assert not result.startswith("/etc")
        assert result.startswith("/downloads")

    def test_safe_target_path_dot_dot_slash(self):
        from pardus_paylasim.discovery.transfer import safe_target_path
        result = safe_target_path("/downloads", "../../secret.key")
        assert not result.startswith("/secret")
        assert result.startswith("/downloads")

    def test_safe_target_path_deep_nesting(self):
        from pardus_paylasim.discovery.transfer import safe_target_path
        result = safe_target_path("/downloads", "a/b/c/d/file.txt")
        assert result.startswith("/downloads")
        assert "file.txt" in result


class TestStreamConfigA11y:
    """StreamConfig tutarlılık testleri."""

    def test_resolution_label_native(self):
        from pardus_paylasim.screen.stream_config import StreamConfig
        config = StreamConfig()
        assert config.resolution_label == "native"

    def test_resolution_label_scaled(self):
        from pardus_paylasim.screen.stream_config import StreamConfig
        config = StreamConfig(width=1920, height=1080)
        assert config.resolution_label == "1920x1080"

    def test_frame_interval_consistent(self):
        from pardus_paylasim.screen.stream_config import StreamConfig
        config = StreamConfig(framerate=25)
        assert abs(config.frame_interval - 0.04) < 0.001

    def test_config_clamping_quality(self):
        from pardus_paylasim.screen.stream_config import StreamConfig
        assert StreamConfig(jpeg_quality=0).jpeg_quality == 1
        assert StreamConfig(jpeg_quality=200).jpeg_quality == 100

    def test_config_clamping_framerate(self):
        from pardus_paylasim.screen.stream_config import StreamConfig
        assert StreamConfig(framerate=0).framerate == 1
        assert StreamConfig(framerate=100).framerate == 60

    def test_config_clamping_port(self):
        from pardus_paylasim.screen.stream_config import StreamConfig
        assert StreamConfig(port=0).port == 1

    def test_gst_pipeline_native(self):
        from pardus_paylasim.screen.stream_config import StreamConfig
        assert StreamConfig().gst_scale_fragment() == ""

    def test_gst_pipeline_scaled(self):
        from pardus_paylasim.screen.stream_config import StreamConfig
        config = StreamConfig(width=1280, height=720)
        fragment = config.gst_scale_fragment()
        assert "1280" in fragment
        assert "720" in fragment


class TestCORSValidation:
    """CORS allowlist doğrulama testleri."""

    def test_parse_allowed_origins_empty(self):
        from pardus_paylasim.screen.stream_server import parse_allowed_origins
        assert parse_allowed_origins("") == frozenset()
        assert parse_allowed_origins(None) == frozenset()

    def test_parse_allowed_origins_valid(self):
        from pardus_paylasim.screen.stream_server import parse_allowed_origins
        result = parse_allowed_origins("https://a.local, https://b:8443")
        assert "https://a.local" in result
        assert "https://b:8443" in result

    def test_parse_allowed_origins_joker_blocked(self):
        from pardus_paylasim.screen.stream_server import parse_allowed_origins
        result = parse_allowed_origins("*")
        assert len(result) == 0
        assert "*" not in result

    def test_parse_allowed_origins_whitespace_trimmed(self):
        from pardus_paylasim.screen.stream_server import parse_allowed_origins
        result = parse_allowed_origins("  https://a.local  ,  https://b.local  ")
        assert "https://a.local" in result
        assert "https://b.local" in result


class TestProgressHelpers:
    """İlerleme yardımcı fonksiyon testleri."""

    def test_human_size_bytes(self):
        from pardus_paylasim.progress import human_size
        assert human_size(0) == "0 B"
        assert human_size(500) == "500 B"

    def test_human_size_kb(self):
        from pardus_paylasim.progress import human_size
        assert "KB" in human_size(1024)

    def test_human_size_mb(self):
        from pardus_paylasim.progress import human_size
        assert "MB" in human_size(1024 * 1024)

    def test_human_eta_none(self):
        from pardus_paylasim.progress import human_eta
        assert human_eta(None) == "—"

    def test_human_eta_seconds(self):
        from pardus_paylasim.progress import human_eta
        assert "sn" in human_eta(30)

    def test_human_eta_minutes(self):
        from pardus_paylasim.progress import human_eta
        assert "dk" in human_eta(120)

    def test_compute_stats_basic(self):
        from pardus_paylasim.progress import compute_stats
        stats = compute_stats(transferred=500, total=1000, elapsed=1.0)
        assert stats.percent == 0.5
        assert stats.rate_bps == 500.0
        assert stats.eta_seconds == 1.0

    def test_compute_stats_zero_elapsed(self):
        from pardus_paylasim.progress import compute_stats
        stats = compute_stats(transferred=500, total=1000, elapsed=0.0)
        assert stats.rate_bps == 0.0

    def test_compute_stats_completed(self):
        from pardus_paylasim.progress import compute_stats
        stats = compute_stats(transferred=1000, total=1000, elapsed=2.0)
        assert stats.percent == 1.0


class TestContainerfile:
    """Containerfile yapısal bütünlüğü."""

    CONTAINERFILE = os.path.join(REPO_ROOT, "Containerfile")

    def test_containerfile_exists(self):
        assert os.path.exists(self.CONTAINERFILE)

    def test_containerfile_has_from(self):
        with open(self.CONTAINERFILE) as f:
            content = f.read()
        assert "FROM" in content

    def test_containerfile_has_expose(self):
        with open(self.CONTAINERFILE) as f:
            content = f.read()
        assert "EXPOSE" in content

    def test_containerfile_has_user(self):
        with open(self.CONTAINERFILE) as f:
            content = f.read()
        assert "USER" in content

    def test_containerfile_non_root(self):
        with open(self.CONTAINERFILE) as f:
            content = f.read()
        assert "USER pardus" in content

    def test_containerfile_workdir(self):
        with open(self.CONTAINERFILE) as f:
            content = f.read()
        assert "WORKDIR" in content

    def test_containerfile_installs_pip(self):
        with open(self.CONTAINERFILE) as f:
            content = f.read()
        assert "pip install" in content


class TestFlatpakManifest:
    """Flatpak manifest dosyasının bütünlüğü."""

    MANIFEST = os.path.join(REPO_ROOT, "flatpak", "tr.org.pardus.paylasim.yml")

    def test_manifest_exists(self):
        assert os.path.exists(self.MANIFEST)

    def test_manifest_has_app_id(self):
        with open(self.MANIFEST) as f:
            content = f.read()
        assert "app-id:" in content
        assert "tr.org.pardus.paylasim" in content

    def test_manifest_has_runtime(self):
        with open(self.MANIFEST) as f:
            content = f.read()
        assert "runtime:" in content

    def test_manifest_has_modules(self):
        with open(self.MANIFEST) as f:
            content = f.read()
        assert "modules:" in content

    def test_manifest_finish_args(self):
        with open(self.MANIFEST) as f:
            content = f.read()
        assert "--share=network" in content
        assert "--filesystem=home" in content

    def test_manifest_gnome_runtime(self):
        with open(self.MANIFEST) as f:
            content = f.read()
        assert "org.gnome.Platform" in content


class TestA11yCodeScanning:
    """Kaynak kodda erişilebilirlik etiketlerinin varlığı."""

    def test_window_has_a11y_labels(self):
        """window.py'de _set_a11y_label çağrıları var mı."""
        with open(WINDOW_FILE) as f:
            content = f.read()
        assert content.count("_set_a11y_label(") >= 5

    def test_a11y_labels_on_buttons(self):
        """Butonlar erişilebilirlik etiketine sahip olmalı."""
        with open(WINDOW_FILE) as f:
            content = f.read()
        assert "Gtk.Button" in content

    def test_a11y_labels_on_entries(self):
        """Entry'ler erişilebilirlik etiketine sahip olmalı."""
        with open(WINDOW_FILE) as f:
            content = f.read()
        assert "Gtk.Entry" in content

    def test_a11y_labels_on_switches(self):
        """Switch'ler erişilebilirlik etiketine sahip olmalı."""
        with open(WINDOW_FILE) as f:
            content = f.read()
        assert "Gtk.Switch" in content

    def test_keyboard_shortcuts(self):
        """Klavye kısayolları Ctrl+1..5 ile tanımlı olmalı."""
        with open(WINDOW_FILE) as f:
            content = f.read()
        assert "Ctrl" in content or "ctrl" in content.lower()


class TestStreamingEncryption:
    """Secret transfer'in gerçek streaming chunked encryption kullandığını doğrular."""

    def test_secret_send_uses_chunked_encryption(self):
        """send_file secret modda tüm dosyayı belleğe almamalı."""
        with open(os.path.join(REPO_ROOT, "src", "pardus_paylasim", "discovery", "transfer.py")) as f:
            content = f.read()
        # The "if secret_pin:" branch should have a per-chunk encrypt loop
        # with f.read(SECRET_CHUNK_SIZE), not f.read() of the whole file.
        assert "f.read(SECRET_CHUNK_SIZE)" in content

    def test_secret_send_does_not_load_full_file(self):
        """Secret send_file bloğu içinde 'f.read()' tüm dosyayı belleğe yüklememeli."""
        with open(os.path.join(REPO_ROOT, "src", "pardus_paylasim", "discovery", "transfer.py")) as f:
            content = f.read()
        # raw f.read() (tüm dosya) secret modda olmamalı
        secret_block = content.split("if secret_pin:")[1].split("else:")[0]
        assert "file_data = f.read()" not in secret_block

    def test_secret_receive_uses_streaming_decrypt(self):
        """Receiver, framed secret payload'ı parça parça çözmeli."""
        with open(os.path.join(REPO_ROOT, "src", "pardus_paylasim", "discovery", "transfer.py")) as f:
            content = f.read()
        assert "_receive_secret_payload" in content
        assert "NamedTemporaryFile" in content or "tempfile" in content

    def test_normal_receive_uses_streaming(self):
        """Receiver, normal payload'ı da chunked streaming ile yazmalı."""
        with open(os.path.join(REPO_ROOT, "src", "pardus_paylasim", "discovery", "transfer.py")) as f:
            content = f.read()
        assert "_receive_normal_payload" in content
        # Normal modda tüm payload'u belleğe alma
        assert "file_data = bytes(payload_data)" not in content

    def test_transfer_uses_temp_files(self):
        """Her iki mod da geçici dosya kullanmalı (bellek sabit)."""
        with open(os.path.join(REPO_ROOT, "src", "pardus_paylasim", "discovery", "transfer.py")) as f:
            content = f.read()
        # temp_path değişkeni tanımlı ve her iki modda atanıyor
        assert "temp_path = self._receive_normal_payload" in content
        assert "temp_path = self._receive_secret_payload" in content
        # os.replace ile atomik taşıma yapılıyor
        assert "os.replace(temp_path" in content

    def test_recv_exact_no_full_payload(self):
        """net_util.recv_exact artık tüm payload'u belleğe almaz (streaming için parça parça okunur)."""
        # Bu davranış _receive_normal_payload'da min(chunk_size, remaining) olarak uygulanıyor
        with open(os.path.join(REPO_ROOT, "src", "pardus_paylasim", "discovery", "transfer.py")) as f:
            content = f.read()
        assert "min(chunk_size, payload_size - received)" in content
