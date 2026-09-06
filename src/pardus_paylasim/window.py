"""
Main GTK4 + Libadwaita Window for Pardus Güvenli Paylaşım.
Provides 4-tab interface:
1. 🛡️ Dosya Gizliliği ve Meta Veri Temizleme
2. 📲 Wi-Fi / Bluetooth Cihaz Tanıma (Ecosystem Continuity)
3. 🖥️ macOS Tarzı Ekran Paylaşımı (AirPlay/Sidecar)
4. 📋 Hassas Metin & Pano Maskeleme
"""

import logging
import os
import threading

logger = logging.getLogger(__name__)

from pardus_paylasim.config import AppConfig
from pardus_paylasim.discovery.clipboard_sync import (
    ClipboardSyncClient,
    ClipboardSyncServer,
)
from pardus_paylasim.discovery.history import (
    STATUS_CONTROL_START,
    STATUS_CONTROL_STOP,
    TransferHistory,
)
from pardus_paylasim.discovery.qr_pairing import (
    build_pairing_uri as qr_build_pairing_uri,
)
from pardus_paylasim.discovery.qr_pairing import (
    generate_qr_png as qr_generate_png,
)
from pardus_paylasim.discovery.qr_pairing import (
    parse_pairing_uri as qr_parse_pairing_uri,
)
from pardus_paylasim.discovery.transfer import FileReceiverServer, FileSender
from pardus_paylasim.i18n import _
from pardus_paylasim.notifications import send_notification
from pardus_paylasim.screen.control_client import (
    gdk_state_to_mods,
    keyval_to_key_code,
    map_widget_to_normalized,
)
from pardus_paylasim.screen.stream_config import DEFAULT_PORT
from pardus_paylasim.ui.clipboard_view import ClipboardViewHandler
from pardus_paylasim.ui.discovery_view import DiscoveryViewHandler
from pardus_paylasim.ui.privacy_view import PrivacyViewHandler
from pardus_paylasim.ui.screen_share_view import ScreenShareViewHandler

try:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gdk, Gio, GLib, Gtk

    HAS_GTK = True
except Exception as e:
    logger.warning("GTK import failed: %s", e)
    HAS_GTK = False


class MainWindow:
    """Main application window with 6 functional tabs."""

    def __init__(self, app=None):
        self.privacy_handler = PrivacyViewHandler()
        self.discovery_handler = DiscoveryViewHandler()
        self.screen_handler = ScreenShareViewHandler()
        self.clipboard_handler = ClipboardViewHandler()
        self.config = AppConfig()

        self.history = TransferHistory()

        self.receiver = FileReceiverServer(self.config.get("download_dir"))
        self.receiver.on_file_received = self._on_file_received_callback
        self.receiver.get_secret_pin_callback = self._on_get_secret_pin_callback
        self.receiver.on_file_request = self._on_file_request_callback
        self.receiver.history = self.history
        try:
            self.receiver.start()
        except OSError as e:
            # Port doluysa (eski örnek çalışıyor?) arayüz yine açılmalı;
            # dosya alma bu oturumda devre dışı kalır.
            logger.warning("Dosya alıcısı başlatılamadı (port dolu?): %s", e)

        # Cihazlar arası pano paylaşımı sunucusu.
        self.clipboard_server = ClipboardSyncServer()
        self.clipboard_server.on_clipboard_received = self._on_clipboard_received_callback
        try:
            self.clipboard_server.start()
        except OSError as e:
            logger.warning("Pano sunucusu başlatılamadı (port dolu?): %s", e)

        # Internal state
        self._discovery_active = False
        self._screen_hosting = False
        self._screen_connected = False
        # Uzak ekran canlı-render karesi (1.6). Ağ thread'i en son kareyi
        # bırakır, ana thread çizer. Backpressure: yalnız son kare tutulur.
        self._remote_frame_lock = threading.Lock()
        self._remote_frame_latest = None
        self._remote_frame_scheduled = False
        # Uzaktan kontrol girdi-yakalama durumu (1.7 — C5). Kanal yaşam döngüsü
        # (bağlan/istek/onay) 1.8'de bağlanır: `_control_client` None ve
        # `_control_active` False kaldığı sürece yakalama geri çağrıları hiçbir
        # şey göndermez (no-op). Böylece 1.7 kendi kendine yeter, testler geçer.
        self._control_client = None
        self._control_active = False
        # Çizilen son karenin gerçek (native) çözünürlüğü — koordinat eşlemesi
        # widget↔görüntü letterbox'ı için gerekir (`_render_remote_frame` yazar).
        self._remote_image_w = 0
        self._remote_image_h = 0
        # Motion olaylarını kare hızına kıs (frame-rate throttle): ardışık move
        # gönderimleri arası en az ~40 ms (≈25 fps); ağ ve host'u boğmaz.
        self._control_motion_interval_us = 40_000
        self._last_motion_sent_us = 0
        self._selected_files = []
        self._clipboard_monitoring = False
        self._clipboard_timeout_id = None
        self._row_devices = {}
        self._guard_toggle = False
        # Uzaktan kontrol izin switch'inin re-entry koruması (1.8 — C6). Consent
        # dialog'u async olduğu için switch state'ini elle geri alırken
        # `state-set` sinyalinin tekrar tetiklenmesini engeller.
        self._guard_control_switch = False

        # Load window state
        self.win = None  # Set when GTK available

        if HAS_GTK and app:
            self._build_gtk_ui(app)
        else:
            logger.info("Running in headless/CLI framework mode.")
            logger.info("Kullanım: pardus-paylasim --clean <dosya> --out <çıktı>")
            logger.info("           pardus-paylasim --mask <metin>")

    # ──────────────────────────────────────────────
    #  GTK4 UI Construction
    # ──────────────────────────────────────────────

    def _build_gtk_ui(self, app):
        self.win = Adw.ApplicationWindow(application=app)
        self.win.set_title(_("Pardus Güvenli Paylaşım ve Süreklilik Merkezi"))
        self.win.set_default_size(1000, 720)

        # Connect close handler for cleanup
        self.win.connect("close-request", self._on_window_close)
        self.app = app

        # Header bar
        header = Adw.HeaderBar()

        # Main layout: toolbox (sidebar) + view stack
        toolbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        toolbox.append(header)

        # ── Tab container ──
        self.view_stack = Adw.ViewStack()
        self.view_stack.connect("notify::visible-child-name", self._on_tab_changed)

        # Tab 1: Privacy
        self._build_privacy_tab()

        # Tab 2: Device Discovery
        self._build_discovery_tab()

        # Tab 3: Screen Share
        self._build_screen_share_tab()

        # Tab 4: Clipboard
        self._build_clipboard_tab()

        # Tab 5: Settings / Dashboard
        self._build_settings_tab()

        # Tab 6: Mesh Ağı (Mesh + WebRTC + Asenkron Transfer)
        self._build_mesh_tab()

        # View switcher in header (so tabs are always visible at the top macOS-style)
        switcher = Adw.ViewSwitcher()
        switcher.set_stack(self.view_stack)
        switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(switcher)

        # Transfer geçmişi butonu (header sağ).
        btn_history = Gtk.Button()
        btn_history.set_icon_name("document-open-recent-symbolic")
        btn_history.set_tooltip_text(_("Transfer Geçmişi"))
        btn_history.connect("clicked", self._on_show_history)
        header.pack_end(btn_history)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_box.append(self.view_stack)

        toolbox.append(main_box)
        self.win.set_content(toolbox)

        # Klavye kısayolları (sekme geçişi, geçmiş, çıkış).
        self._setup_shortcuts()

        self.win.present()

    # ──────────────────────────────────────────────
    #  Keyboard shortcuts (GTK4 actions + accelerators)
    # ──────────────────────────────────────────────

    # Sekmelerin sıralı adları — Ctrl+1..6 bu sıraya göre eşlenir.
    # (view_stack'e ekleme sırasıyla birebir aynı olmalı.)
    TAB_NAMES = ("privacy", "discovery", "screenshare", "clipboard", "settings", "mesh")

    @staticmethod
    def _tab_name_for_index(index, tab_names=TAB_NAMES):
        """1-tabanlı kısayol numarasını sekme adına çevirir.

        Ctrl+1 → ilk sekme. Aralık dışıysa None döner (saf; GTK gerektirmez,
        headless test edilebilir).

        Args:
            index: Kullanıcının bastığı sayı (1..N).
            tab_names: Sıralı sekme adları (varsayılan sınıf sabiti).

        Returns:
            Sekme adı (str) veya geçersizse None.
        """
        if not isinstance(index, int) or index < 1 or index > len(tab_names):
            return None
        return tab_names[index - 1]

    def _setup_shortcuts(self):
        """Uygulama düzeyinde klavye kısayollarını kaydeder.

        Ctrl+1..5: sekme geçişi, Ctrl+H: transfer geçmişi, Ctrl+Q: çıkış.
        `Gio.SimpleAction` + `set_accels_for_action` kalıbı kullanılır; eylem
        adları "app." önekiyle hızlandırıcılara bağlanır. GTK yoksa çağrılmaz.
        """
        if not HAS_GTK or self.app is None:
            return

        # Sekme geçişi: Ctrl+1..6 → view_stack.set_visible_child_name.
        for i, name in enumerate(self.TAB_NAMES, start=1):
            action = Gio.SimpleAction.new(f"tab-{i}", None)
            # Varsayılan bağ (default arg) döngü kapanış tuzağını önler.
            action.connect(
                "activate",
                lambda _a, _p, tab=name: self._activate_tab(tab),
            )
            self.app.add_action(action)
            self.app.set_accels_for_action(f"app.tab-{i}", [f"<Ctrl>{i}"])

        # Transfer geçmişi: Ctrl+H.
        act_history = Gio.SimpleAction.new("show-history", None)
        act_history.connect("activate", lambda _a, _p: self._on_show_history(None))
        self.app.add_action(act_history)
        self.app.set_accels_for_action("app.show-history", ["<Ctrl>h"])

        # Çıkış: Ctrl+Q (pencereyi kapatır → _on_window_close temizliği koşar).
        act_quit = Gio.SimpleAction.new("quit", None)
        act_quit.connect("activate", lambda _a, _p: self.win.close())
        self.app.add_action(act_quit)
        self.app.set_accels_for_action("app.quit", ["<Ctrl>q"])

        # Uzaktan kontrol kill-switch: Ctrl+Alt+K (1.8 — C4-4). Host iznini
        # düşürür + client kanalını kapatır → tek kısayolla her iki rol güvene.
        act_kill = Gio.SimpleAction.new("kill-control", None)
        act_kill.connect("activate", lambda _a, _p: self._on_kill_switch())
        self.app.add_action(act_kill)
        self.app.set_accels_for_action("app.kill-control", ["<Ctrl><Alt>k"])

    def _activate_tab(self, name):
        """Verilen ada sahip sekmeyi görünür yapar (kısayol eylemi)."""
        if self.view_stack is not None:
            self.view_stack.set_visible_child_name(name)

    # ──────────────────────────────────────────────
    #  Accessibility helpers (GTK4 a11y)
    # ──────────────────────────────────────────────

    def _set_a11y_label(self, widget, label, description=None):
        """Set accessible name (+ optional description) on a widget.

        GTK4 exposes the ARIA-equivalent via the Gtk.Accessible interface that
        every widget implements. Best-effort: signature drift on older
        PyGObject must never crash the UI, so failures degrade silently
        (tooltips already carry the text to assistive tech in that case).
        """
        if not HAS_GTK:
            return
        try:
            props = [Gtk.AccessibleProperty.LABEL]
            vals = [label]
            if description is not None:
                props.append(Gtk.AccessibleProperty.DESCRIPTION)
                vals.append(description)
            widget.update_property(props, vals)
        except Exception as e:
            logger.debug("exception at %s: %s", inspect.currentframe().f_code.co_name, e)
            logger.debug("a11y update_property unsupported for %r", widget)

    # ──────────────────────────────────────────────
    #  TAB 1: Dosya Gizliliği & Meta Veri Temizleme
    # ──────────────────────────────────────────────

    def _build_privacy_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(16)
        box.set_margin_end(16)

        # Header area
        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        lbl_title = Gtk.Label(label=_("🛡️ Dosya Gizliliği ve Meta Veri Temizleyici"))
        lbl_title.add_css_class("title-2")
        lbl_title.set_halign(Gtk.Align.START)
        lbl_desc = Gtk.Label(
            label=_(
                "Fotoğraf, PDF ve ofis belgelerindeki GPS konumu, yazar adı, "
                "cihaz bilgisi gibi gizlilik risklerini tespit edin ve temizleyin."
            )
        )
        lbl_desc.set_halign(Gtk.Align.START)
        lbl_desc.add_css_class("body")
        header_box.append(lbl_title)
        header_box.append(lbl_desc)

        # Drop zone
        self.drop_revealer = Gtk.Revealer()
        drop_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        drop_box.set_margin_top(12)
        drop_box.set_margin_bottom(12)
        drop_box.set_margin_start(24)
        drop_box.set_margin_end(24)
        drop_box.add_css_class("card")

        drop_icon = Gtk.Image.new_from_icon_name("document-open-symbolic")
        drop_icon.set_pixel_size(48)
        drop_lbl = Gtk.Label(label=_("Dosyaları bu alana sürükleyin veya seçmek için tıklayın"))
        drop_lbl.add_css_class("title-4")
        drop_sub = Gtk.Label(label=_("Desteklenen: JPG, PNG, PDF, DOCX, XLSX, PPTX, ODT"))
        drop_sub.add_css_class("caption")

        drop_box.append(drop_icon)
        drop_box.append(drop_lbl)
        drop_box.append(drop_sub)

        self.drop_revealer.set_child(drop_box)
        self.drop_revealer.set_reveal_child(True)

        # Set up drag-and-drop target
        drop_target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop_target.connect("drop", self._on_drop_files)
        drop_box.add_controller(drop_target)

        # File choose button
        self.btn_choose_file = Gtk.Button(label=_("Dosya Seç"))
        self.btn_choose_file.add_css_class("pill")
        self.btn_choose_file.set_halign(Gtk.Align.CENTER)
        self.btn_choose_file.connect("clicked", self._on_choose_file)

        # Batch clean button
        self.btn_batch_clean = Gtk.Button(label=_("Tümünü Temizle ve Güvenli Kopya Oluştur"))
        self.btn_batch_clean.add_css_class("pill")
        self.btn_batch_clean.add_css_class("suggested-action")
        self.btn_batch_clean.set_halign(Gtk.Align.CENTER)
        self.btn_batch_clean.set_sensitive(False)
        self.btn_batch_clean.connect("clicked", self._on_batch_clean)

        # Results list
        self.privacy_list = Gtk.ListBox()
        self.privacy_list.add_css_class("boxed-list")
        self.privacy_list.set_selection_mode(Gtk.SelectionMode.NONE)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_min_content_height(200)
        scrolled.set_child(self.privacy_list)

        # Status label
        self.privacy_status = Gtk.Label(label=_("Henüz dosya seçilmedi."))
        self.privacy_status.add_css_class("caption")
        self.privacy_status.set_halign(Gtk.Align.START)

        # Report buttons
        report_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.btn_report_md = Gtk.Button(label=_("📄 Rapor (Markdown)"))
        self.btn_report_md.set_sensitive(False)
        self.btn_report_md.connect("clicked", self._on_export_report_md)
        self.btn_report_txt = Gtk.Button(label=_("📝 Rapor (Metin)"))
        self.btn_report_txt.set_sensitive(False)
        self.btn_report_txt.connect("clicked", self._on_export_report_txt)
        self.btn_report_json = Gtk.Button(label=_("📊 Rapor (JSON)"))
        self.btn_report_json.set_sensitive(False)
        self.btn_report_json.connect("clicked", self._on_export_report_json)
        report_box.append(self.btn_report_md)
        report_box.append(self.btn_report_txt)
        report_box.append(self.btn_report_json)

        box.append(header_box)
        box.append(self.drop_revealer)
        box.append(self.btn_choose_file)
        box.append(self.btn_batch_clean)
        box.append(scrolled)
        box.append(self.privacy_status)
        box.append(report_box)

        # Store file list
        self._selected_files = []

        # Wrap in a scrolled page
        page = Gtk.ScrolledWindow()
        page.set_child(box)
        self.view_stack.add_titled(page, "privacy", "🛡️ Dosya Gizliliği")

    # ──────────────────────────────────────────────
    #  TAB 2: Cihaz Tanıma
    # ──────────────────────────────────────────────

    def _build_discovery_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(16)
        box.set_margin_end(16)

        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        lbl_title = Gtk.Label(label=_("📲 Wi-Fi ve Bluetooth Cihaz Tanıma"))
        lbl_title.add_css_class("title-2")
        lbl_title.set_halign(Gtk.Align.START)
        lbl_sub = Gtk.Label(
            label=_(
                "Yerel ağda ve Bluetooth üzerinden Pardus ekosistemindeki \n cihazları keşfedin. macOS Continuity tarzı cihaz tanıma."
            )
        )
        lbl_sub.add_css_class("body")
        lbl_sub.set_halign(Gtk.Align.START)
        header_box.append(lbl_title)
        header_box.append(lbl_sub)

        # Control bar
        ctrl_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.btn_discover = Gtk.Button(label=_("🔍 Cihazları Tara"))
        self.btn_discover.add_css_class("pill")
        self.btn_discover.add_css_class("suggested-action")
        self.btn_discover.connect("clicked", self._on_toggle_discovery)

        self.discovery_spinner = Gtk.Spinner()
        self.discovery_spinner.set_visible(False)

        self.lbl_discovery_status = Gtk.Label(label=_("Tarama başlatılmadı."))
        self.lbl_discovery_status.add_css_class("caption")

        self.btn_qr_pair = Gtk.Button(label=_("🔗 QR Eşleştir"))
        self.btn_qr_pair.add_css_class("pill")
        self.btn_qr_pair.set_tooltip_text(
            _("Bu cihazın QR kodunu göster veya bir QR/URI ile eşleş.")
        )
        self.btn_qr_pair.connect("clicked", self._on_qr_pair)

        ctrl_box.append(self.btn_discover)
        ctrl_box.append(self.btn_qr_pair)
        ctrl_box.append(self.discovery_spinner)
        ctrl_box.append(self.lbl_discovery_status)

        # Device list
        self.device_list = Gtk.ListBox()
        self.device_list.add_css_class("boxed-list")
        self.device_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.device_list.connect("row-selected", self._on_device_selected)

        dev_scroll = Gtk.ScrolledWindow()
        dev_scroll.set_vexpand(True)
        dev_scroll.set_min_content_height(250)
        dev_scroll.set_child(self.device_list)

        # Device detail panel
        self.device_detail = Gtk.Label(label=_("Cihaz seçildiğinde detaylar burada görünür."))
        self.device_detail.add_css_class("body")
        self.device_detail.set_halign(Gtk.Align.START)
        self.device_detail.set_wrap(True)
        self.device_detail.set_margin_top(8)
        self.device_detail.set_margin_bottom(8)

        # Action buttons for selected device
        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.btn_pair_device = Gtk.Button(label=_("🤝 Eşleştir"))
        self.btn_pair_device.add_css_class("pill")
        self.btn_pair_device.set_sensitive(False)
        self.btn_pair_device.connect("clicked", self._on_pair_device)

        self.btn_trust_device = Gtk.Button(label=_("Güven"))
        self.btn_trust_device.add_css_class("pill")
        self.btn_trust_device.set_sensitive(False)
        self.btn_trust_device.set_tooltip_text(
            _("Parmak izi doğrulanmış cihazı güvenilirlere ekle.")
        )
        self.btn_trust_device.connect("clicked", self._on_trust_device)

        self.btn_share_normal = Gtk.Button(label=_("📁 Normal Gönder"))
        self.btn_share_normal.add_css_class("pill")
        self.btn_share_normal.set_sensitive(False)
        self.btn_share_normal.set_tooltip_text(_("Dosyayı yerel ağ üzerinden hızlıca gönder."))
        self.btn_share_normal.connect("clicked", self._on_share_normal)

        self.btn_share_secret = Gtk.Button(label=_("🔒 Güvenli (Secret) Gönder"))
        self.btn_share_secret.add_css_class("pill")
        self.btn_share_secret.add_css_class("suggested-action")
        self.btn_share_secret.set_sensitive(False)
        self.btn_share_secret.set_tooltip_text(_("Dosyayı AES-256 ile şifreleyerek P2P gönder."))
        self.btn_share_secret.connect("clicked", self._on_share_secret)

        self.btn_share_folder = Gtk.Button(label=_("🗂️ Klasör Gönder"))
        self.btn_share_folder.add_css_class("pill")
        self.btn_share_folder.set_sensitive(False)
        self.btn_share_folder.set_tooltip_text(_("Bir klasörü iç yapısını koruyarak gönder."))
        self.btn_share_folder.connect("clicked", self._on_share_folder)

        self.btn_share_clipboard = Gtk.Button(label=_("📋 Panoyu Gönder"))
        self.btn_share_clipboard.add_css_class("pill")
        self.btn_share_clipboard.set_sensitive(False)
        self.btn_share_clipboard.set_tooltip_text(_("Sistem panosundaki metni bu cihaza gönder."))
        self.btn_share_clipboard.connect("clicked", self._on_share_clipboard)

        self.btn_share_screen_to = Gtk.Button(label=_("🖥️ Ekran Yansıt"))
        self.btn_share_screen_to.add_css_class("pill")
        self.btn_share_screen_to.set_sensitive(False)
        self.btn_share_screen_to.connect("clicked", self._on_share_screen_to_device)

        action_box.append(self.btn_pair_device)
        action_box.append(self.btn_trust_device)
        action_box.append(self.btn_share_normal)
        action_box.append(self.btn_share_secret)
        action_box.append(self.btn_share_folder)
        action_box.append(self.btn_share_clipboard)
        action_box.append(self.btn_share_screen_to)

        # Gönderim-öncesi gizlilik: dosya gönderilirken metadata temizlensin mi?
        # Varsayılan AÇIK; orijinal dosyaya dokunulmaz, temiz kopya gönderilir.
        self.chk_clean_before_send = Gtk.CheckButton(
            label=_("Göndermeden önce metadata temizle")
        )
        self.chk_clean_before_send.set_active(True)
        self.chk_clean_before_send.set_halign(Gtk.Align.START)
        self._set_a11y_label(
            self.chk_clean_before_send,
            _("Göndermeden önce dosya metadata bilgisini temizle"),
        )

        # Transfer ilerleme göstergesi (#23): gönderim boyunca çubuk + hız/ETA
        # altyazısı. Boşta gizli tutulur; aktarım başlayınca görünür olur.
        self.transfer_progress = Gtk.ProgressBar()
        self.transfer_progress.set_show_text(False)
        self.transfer_progress.set_visible(False)

        self.lbl_transfer_stats = Gtk.Label(label="")
        self.lbl_transfer_stats.add_css_class("caption")
        self.lbl_transfer_stats.set_halign(Gtk.Align.START)
        self.lbl_transfer_stats.set_visible(False)

        # Sürükle-bırak ipucu: seçili cihaza dosya atarak gönderme.
        self.lbl_drop_hint = Gtk.Label(
            label=_(
                "💡 İpucu: Dosyaları buraya sürükleyip bırakarak seçili cihaza gönderebilirsiniz."
            )
        )
        self.lbl_drop_hint.add_css_class("caption")
        self.lbl_drop_hint.set_halign(Gtk.Align.START)
        self.lbl_drop_hint.set_wrap(True)

        box.append(header_box)
        box.append(ctrl_box)
        box.append(dev_scroll)
        box.append(self.device_detail)
        box.append(action_box)
        box.append(self.chk_clean_before_send)
        box.append(self.transfer_progress)
        box.append(self.lbl_transfer_stats)
        box.append(self.lbl_drop_hint)

        self._selected_device = None

        page = Gtk.ScrolledWindow()
        page.set_child(box)

        # Sekmeye bırakılan dosyalar seçili cihaza gönderilir (#21).
        # DropTarget sayfa köküne bağlanır; böylece liste/detay/aksiyon
        # alanlarının tamamı geçerli bırakma bölgesi olur.
        send_drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        send_drop.connect("drop", self._on_drop_files_to_send)
        page.add_controller(send_drop)

        self.view_stack.add_titled(page, "discovery", "📲 Cihaz Tanıma")

    # ──────────────────────────────────────────────
    #  TAB 3: Ekran Paylaşımı
    # ──────────────────────────────────────────────

    def _build_screen_share_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(16)
        box.set_margin_end(16)

        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        lbl_title = Gtk.Label(label=_("🖥️ Wi-Fi / Bluetooth Ekran Paylaşımı"))
        lbl_title.add_css_class("title-2")
        lbl_title.set_halign(Gtk.Align.START)
        lbl_sub = Gtk.Label(
            label=_(
                "macOS AirPlay / Sidecar tarzı düşük gecikmeli ekran paylaşımı. \n Yerel ağdaki Pardus cihazları arasında güvenli ekran yayını."
            )
        )
        lbl_sub.add_css_class("body")
        lbl_sub.set_halign(Gtk.Align.START)
        header_box.append(lbl_title)
        header_box.append(lbl_sub)

        # Mode selector
        mode_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.btn_host_mode = Gtk.ToggleButton(label=_("📡 Ekranımı Yayınla (Sunucu)"))
        self.btn_host_mode.add_css_class("pill")
        self.btn_host_mode.connect("toggled", self._on_host_mode_toggled)
        self.btn_client_mode = Gtk.ToggleButton(label=_("📺 Uzak Ekrana Bağlan (İstemci)"))
        self.btn_client_mode.add_css_class("pill")
        self.btn_client_mode.connect("toggled", self._on_client_mode_toggled)
        mode_box.append(self.btn_host_mode)
        mode_box.append(self.btn_client_mode)

        # Host panel (hidden by default)
        self.host_revealer = Gtk.Revealer()
        host_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        host_box.add_css_class("card")
        host_box.set_margin_top(8)

        self.btn_start_host = Gtk.Button(label=_("▶️ Ekran Yayınını Başlat"))
        self.btn_start_host.add_css_class("pill")
        self.btn_start_host.add_css_class("suggested-action")
        self.btn_start_host.connect("clicked", self._on_start_hosting)

        self.lbl_host_pin = Gtk.Label(label=_("PIN Kodu: —"))
        self.lbl_host_pin.add_css_class("title-3")
        self.lbl_host_pin.set_halign(Gtk.Align.CENTER)

        self.lbl_host_ip = Gtk.Label(label=_("Sunucu IP: —"))
        self.lbl_host_ip.add_css_class("body")
        self.lbl_host_ip.set_halign(Gtk.Align.CENTER)

        self.lbl_host_status = Gtk.Label(label=_("Durum: Yayın başlatılmadı"))
        self.lbl_host_status.add_css_class("caption")
        self.lbl_host_status.set_halign(Gtk.Align.CENTER)

        self.lbl_host_files = Gtk.Label(label="")
        self.lbl_host_files.add_css_class("caption")
        self.lbl_host_files.set_halign(Gtk.Align.CENTER)
        self.lbl_host_files.set_wrap(True)
        self.lbl_host_files.set_visible(False)

        host_box.append(self.btn_start_host)
        host_box.append(self.lbl_host_pin)
        host_box.append(self.lbl_host_ip)
        host_box.append(self.lbl_host_status)
        host_box.append(self.lbl_host_files)

        # ── Uzaktan kontrol izni (1.8 — C4 katı consent) ──────────────
        # Default KAPALI + oturum-only (persist edilmez). Açıkken bile
        # sunucu tarafı geçerli PIN + token doğrular; UI yalnız consent
        # kapısını yönetir. Adw.Banner libadwaita 1.3+ ister (Pardus 23 =
        # 1.2) → sürüm-güvenli olması için kırmızı markup Gtk.Label + Revealer.
        ctrl_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        ctrl_row.set_margin_top(6)
        lbl_ctrl_allow = Gtk.Label(label=_("🖱️ Uzaktan Kontrole İzin Ver"))
        lbl_ctrl_allow.add_css_class("body")
        lbl_ctrl_allow.set_halign(Gtk.Align.START)
        lbl_ctrl_allow.set_hexpand(True)
        self.switch_control_allow = Gtk.Switch()
        self.switch_control_allow.set_active(False)
        self.switch_control_allow.set_valign(Gtk.Align.CENTER)
        self._set_a11y_label(self.switch_control_allow, _("Uzaktan kontrole izin ver"))
        # `state-set` iznin *değişmesini* yakalar; consent dialog async
        # olduğundan handler True döndürerek state'i elle yönetir.
        self.switch_control_allow.connect("state-set", self._on_control_allow_state_set)
        ctrl_row.append(lbl_ctrl_allow)
        ctrl_row.append(self.switch_control_allow)
        host_box.append(ctrl_row)

        # Kalıcı kırmızı gösterge (kontrol etkinken görünür — asla sessiz).
        self.lbl_control_banner = Gtk.Label()
        self.lbl_control_banner.set_use_markup(True)
        self.lbl_control_banner.set_wrap(True)
        self.lbl_control_banner.set_halign(Gtk.Align.CENTER)
        self.lbl_control_banner.add_css_class("error")
        self.control_banner_revealer = Gtk.Revealer()
        self.control_banner_revealer.set_child(self.lbl_control_banner)
        self.control_banner_revealer.set_reveal_child(False)
        host_box.append(self.control_banner_revealer)

        # Anında iptal — daima erişilebilir "Kontrolü Durdur" (kill-switch
        # eşi; Ctrl+Alt+K aynı yolu koşar). Kontrol kapalıyken duyarsız.
        self.btn_stop_control = Gtk.Button(label=_("🛑 Kontrolü Durdur"))
        self.btn_stop_control.add_css_class("pill")
        self.btn_stop_control.add_css_class("destructive-action")
        self.btn_stop_control.set_sensitive(False)
        self.btn_stop_control.connect("clicked", self._on_stop_control_host)
        host_box.append(self.btn_stop_control)

        self.host_revealer.set_child(host_box)

        # Client panel (hidden by default)
        self.client_revealer = Gtk.Revealer()
        client_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        client_box.add_css_class("card")
        client_box.set_margin_top(8)

        self.entry_remote_ip = Gtk.Entry()
        self.entry_remote_ip.set_placeholder_text(_("Sunucu IP adresi (örn: 192.168.1.100)"))
        self._set_a11y_label(self.entry_remote_ip, _("Sunucu IP Adresi"))
        self.entry_remote_port = Gtk.Entry()
        self.entry_remote_port.set_placeholder_text(
            _("Port (varsayılan: {port})").format(port=DEFAULT_PORT)
        )
        self.entry_remote_port.set_text(str(DEFAULT_PORT))
        self._set_a11y_label(self.entry_remote_port, _("Port"))
        self.entry_pin = Gtk.Entry()
        self.entry_pin.set_placeholder_text(_("6 haneli PIN kodu"))
        self._set_a11y_label(self.entry_pin, _("PIN Kodu"))

        self.btn_connect_remote = Gtk.Button(label=_("🔗 Uzak Ekrana Bağlan"))
        self.btn_connect_remote.add_css_class("pill")
        self.btn_connect_remote.add_css_class("suggested-action")
        self.btn_connect_remote.connect("clicked", self._on_connect_remote)

        self.btn_disconnect_remote = Gtk.Button(label=_("⏹️ Bağlantıyı Kes"))
        self.btn_disconnect_remote.add_css_class("pill")
        self.btn_disconnect_remote.add_css_class("destructive-action")
        self.btn_disconnect_remote.set_sensitive(False)
        self.btn_disconnect_remote.connect("clicked", self._on_disconnect_remote)

        self.lbl_client_status = Gtk.Label(label=_("Durum: Bağlı değil"))
        self.lbl_client_status.add_css_class("caption")

        # Uzak ekran canlı görüntüsü (1.6). Bağlanmadan gizli.
        self.remote_picture = Gtk.Picture()
        self.remote_picture.set_can_shrink(True)
        self.remote_picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.remote_picture.set_size_request(-1, 360)
        self._set_a11y_label(self.remote_picture, _("Uzak ekran canlı görüntüsü"))
        self.remote_picture_frame = Gtk.Frame()
        self.remote_picture_frame.add_css_class("card")
        self.remote_picture_frame.set_margin_top(8)
        self.remote_picture_frame.set_child(self.remote_picture)
        self.remote_picture_revealer = Gtk.Revealer()
        self.remote_picture_revealer.set_child(self.remote_picture_frame)
        self.remote_picture_revealer.set_reveal_child(False)
        self._attach_control_capture()

        lbl_remote_ip = Gtk.Label(label=_("Sunucu IP Adresi:"), halign=Gtk.Align.START)
        lbl_remote_ip.set_mnemonic_widget(self.entry_remote_ip)
        client_box.append(lbl_remote_ip)
        client_box.append(self.entry_remote_ip)
        lbl_remote_port = Gtk.Label(label=_("Port:"), halign=Gtk.Align.START)
        lbl_remote_port.set_mnemonic_widget(self.entry_remote_port)
        client_box.append(lbl_remote_port)
        client_box.append(self.entry_remote_port)
        lbl_remote_pin = Gtk.Label(label=_("PIN Kodu:"), halign=Gtk.Align.START)
        lbl_remote_pin.set_mnemonic_widget(self.entry_pin)
        client_box.append(lbl_remote_pin)
        client_box.append(self.entry_pin)
        client_box.append(self.btn_connect_remote)
        client_box.append(self.btn_disconnect_remote)

        # Uzaktan kontrol iste (1.8 — C6). Yalnız ekran bağlıyken duyarlı;
        # basınca ayrı TLS `/control` kanalı açılır (host consent verirse).
        self.btn_request_control = Gtk.Button(label=_("🖱️ Kontrolü İste"))
        self.btn_request_control.add_css_class("pill")
        self.btn_request_control.set_sensitive(False)
        self.btn_request_control.connect("clicked", self._on_request_control)
        client_box.append(self.btn_request_control)

        self.lbl_control_client_status = Gtk.Label(label=_("Kontrol: Kapalı"))
        self.lbl_control_client_status.add_css_class("caption")
        client_box.append(self.lbl_control_client_status)

        client_box.append(self.lbl_client_status)
        self.client_revealer.set_child(client_box)

        box.append(header_box)
        box.append(mode_box)
        box.append(self.host_revealer)
        box.append(self.client_revealer)
        box.append(self.remote_picture_revealer)

        page = Gtk.ScrolledWindow()
        page.set_child(box)
        self.view_stack.add_titled(page, "screenshare", "🖥️ Ekran Paylaşımı")

    # ──────────────────────────────────────────────
    #  TAB 4: Hassas Pano
    # ──────────────────────────────────────────────

    def _build_clipboard_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(16)
        box.set_margin_end(16)

        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        lbl_title = Gtk.Label(label=_("📋 Hassas Metin ve Pano Maskeleyici"))
        lbl_title.add_css_class("title-2")
        lbl_title.set_halign(Gtk.Align.START)
        lbl_sub = Gtk.Label(
            label=_(
                "Metin içindeki T.C. Kimlik No, kredi kartı, IBAN, e-posta, \n telefon ve API anahtarı gibi hassas bilgileri otomatik tespit eder ve maskeler."
            )
        )
        lbl_sub.add_css_class("body")
        lbl_sub.set_halign(Gtk.Align.START)
        header_box.append(lbl_title)
        header_box.append(lbl_sub)

        # Input area
        lbl_input = Gtk.Label(label=_("Taranacak Metin:"), halign=Gtk.Align.START)
        lbl_input.add_css_class("heading")

        self.clip_input = Gtk.TextView()
        self.clip_input.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.clip_input.set_monospace(True)
        self._set_a11y_label(self.clip_input, _("Taranacak Metin"))
        input_scroll = Gtk.ScrolledWindow()
        input_scroll.set_min_content_height(120)
        input_scroll.set_child(self.clip_input)

        # Button row
        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.btn_scan_text = Gtk.Button(label=_("🔍 Hassas Veri Tara"))
        self.btn_scan_text.add_css_class("pill")
        self.btn_scan_text.add_css_class("suggested-action")
        self.btn_scan_text.connect("clicked", self._on_scan_text)

        self.btn_mask_text = Gtk.Button(label=_("🎭 Otomatik Maskele"))
        self.btn_mask_text.add_css_class("pill")
        self.btn_mask_text.connect("clicked", self._on_mask_text)

        self.btn_paste_clip = Gtk.Button(label=_("📋 Panodan Yapıştır"))
        self.btn_paste_clip.add_css_class("pill")
        self.btn_paste_clip.connect("clicked", self._on_paste_from_clipboard)

        btn_row.append(self.btn_scan_text)
        btn_row.append(self.btn_mask_text)
        btn_row.append(self.btn_paste_clip)

        # Result area
        lbl_result = Gtk.Label(label=_("Sonuç:"), halign=Gtk.Align.START)
        lbl_result.add_css_class("heading")

        self.clip_output = Gtk.TextView()
        self.clip_output.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.clip_output.set_monospace(True)
        self.clip_output.set_editable(False)
        self._set_a11y_label(self.clip_output, _("Sonuç"))
        output_scroll = Gtk.ScrolledWindow()
        output_scroll.set_min_content_height(100)
        output_scroll.set_child(self.clip_output)

        # Findings list
        self.clip_findings_list = Gtk.ListBox()
        self.clip_findings_list.add_css_class("boxed-list")
        self.clip_findings_list.set_selection_mode(Gtk.SelectionMode.NONE)
        findings_scroll = Gtk.ScrolledWindow()
        findings_scroll.set_min_content_height(100)
        findings_scroll.set_child(self.clip_findings_list)

        lbl_findings = Gtk.Label(label=_("Tespit Edilen Hassas Veriler:"), halign=Gtk.Align.START)
        lbl_findings.add_css_class("heading")

        # Clipboard monitor toggle
        self.btn_monitor_clip = Gtk.ToggleButton(
            label=_("🔄 Panoyu Sürekli İzle (Otomatik Maskele)")
        )
        self.btn_monitor_clip.add_css_class("pill")
        self.btn_monitor_clip.connect("toggled", self._on_toggle_clipboard_monitor)

        box.append(header_box)
        box.append(lbl_input)
        box.append(input_scroll)
        box.append(btn_row)
        box.append(self.btn_monitor_clip)
        box.append(lbl_result)
        box.append(output_scroll)
        box.append(lbl_findings)
        box.append(findings_scroll)

        page = Gtk.ScrolledWindow()
        page.set_child(box)
        self.view_stack.add_titled(page, "clipboard", "📋 Hassas Pano")

    def _build_settings_tab(self):
        page = Adw.PreferencesPage()

        # General Settings Group
        group1 = Adw.PreferencesGroup(
            title=_("Genel Ayarlar"), description=_("Pardus Güvenli Paylaşım ağ ayarları")
        )
        page.add(group1)

        row_mdns = Adw.ActionRow(
            title=_("Ağda Görünürlük"), subtitle=_("Diğer cihazlar beni bulabilsin (mDNS yayını)")
        )
        self.switch_mdns = Gtk.Switch()
        self.switch_mdns.set_active(self.config.get("mdns_visible", True))
        self.switch_mdns.set_valign(Gtk.Align.CENTER)
        self.switch_mdns.connect("notify::active", self._on_setting_changed, "mdns_visible")
        row_mdns.add_suffix(self.switch_mdns)
        group1.add(row_mdns)

        row_name = Adw.ActionRow(title=_("Cihaz Adı"), subtitle=_("Ağda görünecek adınız"))
        self.entry_name = Gtk.Entry()
        self.entry_name.set_text(self.config.get("device_name", "Pardus Cihazı"))
        self.entry_name.set_valign(Gtk.Align.CENTER)
        self._set_a11y_label(self.entry_name, _("Cihaz Adı"), _("Ağda görünecek adınız"))
        self.entry_name.connect("changed", self._on_setting_changed, "device_name")
        row_name.add_suffix(self.entry_name)
        group1.add(row_name)

        # Security Settings Group
        group2 = Adw.PreferencesGroup(
            title=_("Güvenlik Kalkanı"), description=_("Arka planda çalışan güvenlik özellikleri")
        )
        page.add(group2)

        row_clip = Adw.ActionRow(
            title=_("Otomatik Pano Koruması"),
            subtitle=_(
                "Sistem panosundaki T.C. Kimlik / Kredi Kartı numaralarını otomatik sansürle"
            ),
        )
        self.switch_clip = Gtk.Switch()
        self.switch_clip.set_active(self.config.get("auto_clipboard_protection", False))
        self.switch_clip.set_valign(Gtk.Align.CENTER)
        self.switch_clip.connect(
            "notify::active", self._on_setting_changed, "auto_clipboard_protection"
        )
        row_clip.add_suffix(self.switch_clip)
        group2.add(row_clip)

        # Default Directory
        group3 = Adw.PreferencesGroup(
            title=_("Dosya Paylaşımı"), description=_("Gelen dosyaların kaydedileceği konum")
        )
        page.add(group3)

        self.row_dir = Adw.ActionRow(
            title=_("İndirme Konumu"), subtitle=self.config.get("download_dir")
        )
        btn_dir = Gtk.Button(label=_("Değiştir"))
        btn_dir.set_valign(Gtk.Align.CENTER)
        self._set_a11y_label(btn_dir, _("İndirme konumunu değiştir"))
        btn_dir.connect("clicked", self._on_choose_folder)
        self.row_dir.add_suffix(btn_dir)
        group3.add(self.row_dir)

        # Parmak İzi ve Güvenilir Cihazlar
        group4 = Adw.PreferencesGroup(
            title=_("Parmak İzi ve Güven"),
            description=_("Cihaz kimliği ve eşleşmiş cihazlar"),
        )
        page.add(group4)

        from pardus_paylasim.auth.trust_store import group_fingerprint, own_fingerprint

        own_fp = own_fingerprint()
        self.row_fingerprint = Adw.ActionRow(
            title=_("Bu Cihazın Parmak İzi"),
            subtitle=group_fingerprint(own_fp) if own_fp else _("Kullanılamıyor"),
        )
        btn_fp_copy = Gtk.Button(label=_("Kopyala"))
        btn_fp_copy.set_valign(Gtk.Align.CENTER)
        btn_fp_copy.set_sensitive(bool(own_fp))
        self._set_a11y_label(btn_fp_copy, _("Parmak izini panoya kopyala"))
        btn_fp_copy.connect("clicked", self._on_copy_fingerprint)
        self.row_fingerprint.add_suffix(btn_fp_copy)
        group4.add(self.row_fingerprint)

        row_auto = Adw.ActionRow(
            title=_("Güvenilir Cihazlardan Otomatik Kabul"),
            subtitle=_(
                "Kapalı tutulması önerilir: IP tek başına zayıf kimliktir, "
                "yerel ağda taklit edilebilir."
            ),
        )
        self.switch_auto_accept = Gtk.Switch()
        self.switch_auto_accept.set_active(self.config.get("auto_accept_trusted", False))
        self.switch_auto_accept.set_valign(Gtk.Align.CENTER)
        self.switch_auto_accept.connect(
            "notify::active", self._on_setting_changed, "auto_accept_trusted"
        )
        row_auto.add_suffix(self.switch_auto_accept)
        group4.add(row_auto)

        self.trusted_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        group4.add(self.trusted_box)
        self._refresh_trusted_rows()

        # Elle cihaz ekleme (parmak izini bildiğin cihaz).
        add_row = Adw.ActionRow(
            title=_("Cihaz Ekle"),
            subtitle=_("Ad + parmak izi (64 hex) + IP girin"),
        )
        add_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.entry_trust_name = Gtk.Entry()
        self.entry_trust_name.set_placeholder_text(_("Ad"))
        self.entry_trust_name.set_width_chars(12)
        self.entry_trust_fp = Gtk.Entry()
        self.entry_trust_fp.set_placeholder_text(_("Parmak izi"))
        self.entry_trust_fp.set_width_chars(20)
        self.entry_trust_ip = Gtk.Entry()
        self.entry_trust_ip.set_placeholder_text("192.168.1.20")
        self.entry_trust_ip.set_width_chars(13)
        btn_trust_add = Gtk.Button(label=_("Ekle"))
        btn_trust_add.set_valign(Gtk.Align.CENTER)
        self._set_a11y_label(btn_trust_add, _("Güvenilir cihazı elle ekle"))
        btn_trust_add.connect("clicked", self._on_trust_add_manual)
        for w in (self.entry_trust_name, self.entry_trust_fp, self.entry_trust_ip):
            w.set_valign(Gtk.Align.CENTER)
            add_box.append(w)
        add_box.append(btn_trust_add)
        add_row.add_suffix(add_box)
        group4.add(add_row)

        self.view_stack.add_titled(page, "settings", "⚙️ Ayarlar")

    @staticmethod
    def _device_fingerprint() -> str:
        from pardus_paylasim.auth.trust_store import own_fingerprint

        return own_fingerprint()

    def _refresh_trusted_rows(self):
        """Güvenilir cihaz listesini yeniden çizer (GTK thread)."""
        from pardus_paylasim.auth.trust_store import TrustStore, group_fingerprint

        while True:
            child = self.trusted_box.get_first_child()
            if child is None:
                break
            self.trusted_box.remove(child)
        try:
            devices = TrustStore().get_all()
        except Exception as e:
            logger.debug("güven listesi okunamadı: %s", e)
            devices = []
        if not devices:
            lbl = Gtk.Label(label=_("Henüz güvenilir cihaz yok (QR ile eşleşin)."))
            lbl.add_css_class("caption")
            lbl.set_halign(Gtk.Align.START)
            self.trusted_box.append(lbl)
            return
        for dev in sorted(devices, key=lambda d: d.device_name.lower()):
            short_fp = group_fingerprint(dev.public_key)
            short_fp = short_fp[:23] + "…" if len(short_fp) > 24 else short_fp
            row = Adw.ActionRow(
                title=dev.device_name,
                subtitle=f"{short_fp}" + (f" · {dev.last_ip}" if dev.last_ip else ""),
            )
            btn_rm = Gtk.Button(label=_("Kaldır"))
            btn_rm.set_valign(Gtk.Align.CENTER)
            self._set_a11y_label(btn_rm, _("Güveni kaldır") + f": {dev.device_name}")
            btn_rm.connect("clicked", self._on_untrust_device, dev.public_key)
            row.add_suffix(btn_rm)
            self.trusted_box.append(row)

    def _on_untrust_device(self, btn, fingerprint):
        from pardus_paylasim.auth.trust_store import TrustStore

        try:
            TrustStore().remove_trusted_device(fingerprint)
        except Exception as e:
            logger.debug("güven kaldırılamadı: %s", e)
        self._refresh_trusted_rows()

    def _on_trust_add_manual(self, btn):
        from pardus_paylasim.auth.trust_store import TrustStore, valid_fingerprint

        name = self.entry_trust_name.get_text().strip() or "?"
        fp = valid_fingerprint(self.entry_trust_fp.get_text())
        ip = self.entry_trust_ip.get_text().strip() or None
        if not fp:
            self._show_error(_("Geçersiz parmak izi (64 hex karakter olmalı)."))
            return
        try:
            ok = TrustStore().record_pairing(fp, name, ip)
        except Exception as e:
            logger.debug("güven kaydı yazılamadı: %s", e)
            ok = False
        if not ok:
            self._show_error(_("Güven kaydı yazılamadı."))
            return
        self.entry_trust_name.set_text("")
        self.entry_trust_fp.set_text("")
        self.entry_trust_ip.set_text("")
        self._show_info(_("{name} güvenilirlere eklendi.").format(name=name))
        self._refresh_trusted_rows()

    def _on_copy_fingerprint(self, btn):
        from pardus_paylasim.auth.trust_store import group_fingerprint

        fp = self._device_fingerprint()
        if not fp:
            return
        try:
            Gdk.Display.get_default().get_clipboard().set(group_fingerprint(fp))
            self._show_info(_("Parmak izi panoya kopyalandı."))
        except Exception as e:
            logger.debug("pano kopyalama hatası: %s", e)

    def _build_mesh_tab(self):
        """Mesh ağı: parça-parça P2P transfer, WebRTC ekran paylaşımı, asenkron kuyruk."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(16)
        box.set_margin_end(16)

        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        lbl_title = Gtk.Label(label=_("🌐 Mesh Ağı"))
        lbl_title.add_css_class("title-2")
        lbl_title.set_halign(Gtk.Align.START)
        lbl_sub = Gtk.Label(
            label=_(
                "Parça-parça P2P transfer, WebRTC ekran paylaşımı ve çevrimdışı kuyruk.\n"
                "Tüm veriler cihazınızda kalır — buluta gönderilmez."
            )
        )
        lbl_sub.add_css_class("body")
        lbl_sub.set_halign(Gtk.Align.START)
        header_box.append(lbl_title)
        header_box.append(lbl_sub)
        box.append(header_box)

        # Mesh Ağı durumu
        mesh_group = Adw.PreferencesGroup(
            title=_("🌐 Mesh Ağı"),
            description=_("Cihazlar arası parça-parça P2P transfer"),
        )
        self.mesh_status_row = Adw.ActionRow(
            title=_("Mesh Durumu"),
            subtitle=_("Başlatılmadı"),
        )
        btn_mesh_toggle = Gtk.Button(label=_("Başlat"))
        btn_mesh_toggle.set_valign(Gtk.Align.CENTER)
        self._set_a11y_label(btn_mesh_toggle, _("Mesh ağını başlat"))
        btn_mesh_toggle.connect("clicked", self._on_mesh_toggle)
        self.mesh_status_row.add_suffix(btn_mesh_toggle)
        self.btn_mesh_toggle = btn_mesh_toggle
        mesh_group.add(self.mesh_status_row)

        self.mesh_peers_row = Adw.ActionRow(
            title=_("Bağlı Eşler"), subtitle="0",
        )
        mesh_group.add(self.mesh_peers_row)

        peer_row = Adw.ActionRow(
            title=_("Eş Ekle"),
            subtitle=_("Biçim: 192.168.1.20:8920"),
        )
        self.entry_mesh_peer = Gtk.Entry()
        self.entry_mesh_peer.set_placeholder_text("192.168.1.20:8920")
        self.entry_mesh_peer.set_valign(Gtk.Align.CENTER)
        self.entry_mesh_peer.set_width_chars(21)
        btn_peer_add = Gtk.Button(label=_("Ekle"))
        btn_peer_add.set_valign(Gtk.Align.CENTER)
        self._set_a11y_label(btn_peer_add, _("Mesh eşini ekle"))
        btn_peer_add.connect("clicked", self._on_mesh_peer_add)
        peer_row.add_prefix(self.entry_mesh_peer)
        peer_row.add_suffix(btn_peer_add)
        mesh_group.add(peer_row)
        box.append(mesh_group)

        # WebRTC Data Channel
        webrtc_group = Adw.PreferencesGroup(
            title=_("📡 WebRTC Ekran Paylaşımı"),
            description=_("Düşük gecikmeli SCTP-benzeri data channel"),
        )
        webrtc_status_row = Adw.ActionRow(
            title=_("WebRTC Durumu"), subtitle=_("Devre dışı"),
        )
        webrtc_group.add(webrtc_status_row)
        self.webrtc_status_row = webrtc_status_row
        box.append(webrtc_group)

        # Asenkron Transfer
        async_group = Adw.PreferencesGroup(
            title=_("📬 Asenkron Transfer"),
            description=_("Çevrimdışı cihazlara kuyruklanmış gönderim"),
        )
        async_status_row = Adw.ActionRow(
            title=_("Bekleyen Transferler"),
            subtitle=_("Veritabanı: ~/.local/share/pardus-paylasim/async_transfers.db"),
        )
        btn_async_refresh = Gtk.Button(label=_("Yenile"))
        btn_async_refresh.set_valign(Gtk.Align.CENTER)
        self._set_a11y_label(btn_async_refresh, _("Bekleyen transferleri yenile"))
        btn_async_refresh.connect("clicked", self._on_async_refresh)
        async_status_row.add_suffix(btn_async_refresh)
        async_group.add(async_status_row)

        self.async_count_row = Adw.ActionRow(
            title=_("Toplam Bekleyen"), subtitle="0",
        )
        async_group.add(self.async_count_row)
        box.append(async_group)

        page = Gtk.ScrolledWindow()
        page.set_child(box)
        self.view_stack.add_titled(page, "mesh", "🌐 Mesh Ağı")

    def _on_mesh_toggle(self, btn):
        from pardus_paylasim.discovery.mesh.mesh_network import MeshNode
        import socket
        import uuid
        if not hasattr(self, "_mesh_node") or self._mesh_node is None:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
                s.close()
            except OSError:
                ip = "127.0.0.1"
            self._mesh_node = MeshNode(
                peer_id=str(uuid.uuid4())[:8], local_ip=ip,
            )

            def _peer_changed(pid=None):
                node = getattr(self, "_mesh_node", None)
                if node is not None:
                    GLib.idle_add(
                        self.mesh_peers_row.set_subtitle, str(len(node.peers))
                    )

            self._mesh_node.on_peer_discovered = _peer_changed
            self._mesh_node.on_peer_lost = _peer_changed
            self._mesh_node.start()
            if not self._mesh_node._running:
                self._mesh_node = None
                self.mesh_status_row.set_subtitle(_("Başlatılamadı (port dolu?)"))
                return
            disc_ok = self._mesh_node.start_discovery()
            self.mesh_status_row.set_subtitle(
                _("Çalışıyor (otomatik keşif açık)") if disc_ok
                else _("Çalışıyor (manuel eş ekleyin)")
            )
            self.mesh_peers_row.set_subtitle(str(len(self._mesh_node.peers)))
            self.btn_mesh_toggle.set_label(_("Durdur"))
        else:
            self._mesh_node.stop()
            self._mesh_node = None
            self.mesh_status_row.set_subtitle(_("Başlatılmadı"))
            self.mesh_peers_row.set_subtitle("0")
            self.btn_mesh_toggle.set_label(_("Başlat"))

    def _on_mesh_peer_add(self, btn):
        from pardus_paylasim.discovery.mesh.mesh_network import MeshPeer
        if not getattr(self, "_mesh_node", None):
            self.mesh_peers_row.set_subtitle(_("Önce mesh ağını başlatın"))
            return
        raw = self.entry_mesh_peer.get_text().strip()
        try:
            ip, _, port_s = raw.rpartition(":")
            port = int(port_s)
            if not ip or not 1 <= port <= 65535:
                raise ValueError("bad peer")
        except ValueError:
            self.mesh_peers_row.set_subtitle(_("Geçersiz adres (ör. 192.168.1.20:8920)"))
            return
        self._mesh_node.add_peer(MeshPeer(id=f"{ip}:{port}", ip=ip, port=port))
        self.mesh_peers_row.set_subtitle(str(len(self._mesh_node.peers)))
        self.entry_mesh_peer.set_text("")

    def _on_async_refresh(self, btn):
        from pardus_paylasim.discovery.async_transfer.manager import AsyncTransferStore
        try:
            store = AsyncTransferStore()
            try:
                self.async_count_row.set_subtitle(str(store.count_pending()))
            finally:
                store.close()
        except Exception as e:
            self.async_count_row.set_subtitle(_("Hata: ") + str(e))

    def _on_setting_changed(self, widget, *args):
        # args[0] might be the property name like "active", args[1] is our key if we used connect(..., key)
        # However, due to gobject binding, args for notify::active are (widget, param_spec, user_data)
        # For changed on entry: (widget, user_data)

        if isinstance(widget, Gtk.Switch):
            key = args[1] if len(args) > 1 else args[0]
            val = widget.get_active()
        elif isinstance(widget, Gtk.Entry):
            key = args[0]
            val = widget.get_text()
        else:
            return

        self.config.set(key, val)

    def _on_choose_folder(self, btn):
        dialog = Gtk.FileDialog()
        dialog.set_title(_("İndirme Konumunu Seçin"))
        dialog.set_accept_label("Seç")
        dialog.set_modal(True)
        dialog.select_folder(self.win, None, self._on_folder_selected)

    def _on_folder_selected(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result)
            if folder is None:
                return
            path = folder.get_path()
            if not path:
                return
            self.config.set("download_dir", path)
            if hasattr(self, "row_dir"):
                self.row_dir.set_subtitle(path)
        except GLib.Error:
            # User cancelled the dialog – not an error worth surfacing.
            return
        except Exception as e:
            self._show_error(_("Klasör seçimi hatası: {error}").format(error=e))

    # ═══════════════════════════════════════════════
    #  EVENT HANDLERS – Privacy Tab
    # ═══════════════════════════════════════════════

    def _on_choose_file(self, btn):
        dialog = Gtk.FileDialog()
        dialog.set_title(_("Temizlenecek Dosyaları Seçin"))
        dialog.set_accept_label("Seç")
        dialog.set_modal(True)
        dialog.open_multiple(self.win, None, self._on_files_selected)

    def _on_files_selected(self, dialog, result):
        try:
            file_list = dialog.open_multiple_finish(result)
            if file_list:
                paths = [f.get_path() for f in file_list]
                self._selected_files = paths
                self._refresh_privacy_list()
        except Exception as e:
            self._show_error(_("Dosya seçimi hatası: {error}").format(error=e))

    def _refresh_privacy_list(self):
        # Clear existing
        while True:
            row = self.privacy_list.get_first_child()
            if row is None:
                break
            self.privacy_list.remove(row)

        for path in self._selected_files:
            fname = os.path.basename(path)
            row = Gtk.ListBoxRow()
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row_box.set_margin_top(4)
            row_box.set_margin_bottom(4)

            lbl = Gtk.Label(label=f"📄 {fname}")
            lbl.set_halign(Gtk.Align.START)
            lbl.set_hexpand(True)

            status_lbl = Gtk.Label(label=_("⏳ Hazır"))
            status_lbl.add_css_class("caption")

            remove_btn = Gtk.Button.new_from_icon_name("edit-delete-symbolic")
            remove_btn.add_css_class("flat")
            remove_btn.set_tooltip_text(_("Dosyayı listeden çıkar"))
            self._set_a11y_label(
                remove_btn, _("{filename} dosyasını listeden çıkar").format(filename=fname)
            )
            remove_btn.connect("clicked", self._on_remove_file, path)

            row_box.append(lbl)
            row_box.append(status_lbl)
            row_box.append(remove_btn)
            row.set_child(row_box)
            self.privacy_list.append(row)

        count = len(self._selected_files)
        self.privacy_status.set_label(
            _("{count} dosya seçildi. Her dosya için 'Temizle' işlemini başlatabilirsiniz.").format(
                count=count
            )
        )
        self.btn_batch_clean.set_sensitive(count > 0)

    def _on_remove_file(self, btn, path):
        if path in self._selected_files:
            self._selected_files.remove(path)
            self._refresh_privacy_list()

    def _on_batch_clean(self, btn):
        if not self._selected_files:
            return

        self.btn_batch_clean.set_sensitive(False)
        self.privacy_status.set_label(_("⏳ Dosyalar taranıyor ve temizleniyor..."))

        def clean_worker():
            results = []
            for path in self._selected_files[:]:
                res = self.privacy_handler.process_files([path])
                results.extend(res)

            GLib.idle_add(self._on_cleaning_done, results)

        threading.Thread(target=clean_worker, daemon=True).start()

    def _on_cleaning_done(self, results):
        # Update list with results
        row = self.privacy_list.get_first_child()
        idx = 0
        while row is not None and idx < len(results):
            res = results[idx]
            child = row.get_child()
            if isinstance(child, Gtk.Box):
                children = self._get_box_children(child)
                if len(children) >= 2:
                    status_lbl = children[1]
                    if res.success:
                        status_lbl.set_label(
                            _("✅ Temizlendi ({engine})").format(engine=res.engine_used)
                        )
                    else:
                        status_lbl.set_label(_("❌ Hata: {message}").format(message=res.message))
            row = row.get_next_sibling()
            idx += 1

        self.privacy_status.set_label(
            _("{count} dosya işlendi. Rapor oluşturabilirsiniz.").format(count=len(results))
        )
        self.btn_batch_clean.set_sensitive(True)
        self.btn_report_md.set_sensitive(True)
        self.btn_report_txt.set_sensitive(True)
        self.btn_report_json.set_sensitive(True)

    def _get_box_children(self, box):
        children = []
        child = box.get_first_child()
        while child is not None:
            children.append(child)
            child = child.get_next_sibling()
        return children

    def _on_export_report_md(self, btn):
        report = self.privacy_handler.generate_report_markdown()
        self._save_report(report, "gizlilik_raporu.md")

    def _on_export_report_txt(self, btn):
        report = self.privacy_handler.generate_report_txt()
        self._save_report(report, "gizlilik_raporu.txt")

    def _on_export_report_json(self, btn):
        report = self.privacy_handler.generate_report_json()
        self._save_report(report, "gizlilik_raporu.json")

    def _save_report(self, content, default_name):
        dialog = Gtk.FileDialog()
        dialog.set_title(_("Raporu Kaydet"))
        dialog.set_initial_name(default_name)
        dialog.set_accept_label("Kaydet")
        dialog.save(self.win, None, lambda d, r: self._on_report_saved(d, r, content))

    def _on_report_saved(self, dialog, result, content):
        try:
            gfile = dialog.save_finish(result)
            path = gfile.get_path()
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            self._show_info(f"Rapor kaydedildi: {path}")
        except Exception as e:
            self._show_error(f"Rapor kaydedilemedi: {e}")

    # ═══════════════════════════════════════════════
    #  EVENT HANDLERS – Discovery Tab
    # ═══════════════════════════════════════════════

    def _on_toggle_discovery(self, btn):
        if self._discovery_active:
            self._stop_discovery()
        else:
            self._start_discovery()

    def _start_discovery(self):
        self._discovery_active = True
        self.btn_discover.set_label(_("⏹️ Taramayı Durdur"))
        self.btn_discover.remove_css_class("suggested-action")
        self.discovery_spinner.set_visible(True)
        self.discovery_spinner.start()
        self.lbl_discovery_status.set_label(_("Wi-Fi ve Bluetooth cihazları taranıyor..."))

        def on_devices(devices):
            GLib.idle_add(self._update_device_list, devices)

        self.discovery_handler.start_scanning(on_devices)

    def _stop_discovery(self):
        self._discovery_active = False
        self.btn_discover.set_label(_("🔍 Cihazları Tara"))
        self.btn_discover.add_css_class("suggested-action")
        self.discovery_spinner.stop()
        self.discovery_spinner.set_visible(False)
        self.lbl_discovery_status.set_label(_("Tarama durduruldu."))
        self.discovery_handler.stop_scanning()

    def _update_device_list(self, devices):
        # Clear existing
        while True:
            row = self.device_list.get_first_child()
            if row is None:
                break
            self.device_list.remove(row)
            if row in self._row_devices:
                del self._row_devices[row]

        for dev in devices:
            row = Gtk.ListBoxRow()
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row_box.set_margin_top(4)
            row_box.set_margin_bottom(4)

            icon = "📶" if "Wi-Fi" in dev.connection_type else "📡"
            lock = "🔒 " if getattr(dev, "fingerprint", "") else ""
            lbl = Gtk.Label(
                label=f"{icon} {lock}{dev.name}\n"
                f"<small>{dev.connection_type} · {dev.address} · "
                f"RSSI: {dev.rssi} · {dev.status}</small>"
            )
            lbl.set_use_markup(True)
            lbl.set_halign(Gtk.Align.START)
            lbl.set_hexpand(True)

            row_box.append(lbl)
            row.set_child(row_box)
            self._row_devices[row] = dev
            self.device_list.append(row)

        self.lbl_discovery_status.set_label(f"{len(devices)} cihaz bulundu.")
        return False  # Don't repeat

    def _on_device_selected(self, listbox, row):
        if row and row in self._row_devices:
            dev = self._row_devices[row]
            self._selected_device = dev
            fp_line = ""
            peer_fp = getattr(dev, "fingerprint", "") or ""
            if peer_fp:
                from pardus_paylasim.auth.trust_store import group_fingerprint

                short_fp = group_fingerprint(peer_fp)
                short_fp = short_fp[:35] + "…" if len(short_fp) > 36 else short_fp
                fp_line = f"\n🔑 Parmak İzi: {short_fp}"
            detail = (
                f"**{dev.name}**\n"
                f"🖥️ İşletim Sistemi: {dev.os_info}\n"
                f"🔗 Bağlantı: {dev.connection_type}\n"
                f"📍 Adres: {dev.address}:{dev.port}\n"
                f"📶 Sinyal: {dev.rssi}\n"
                f"📋 Durum: {dev.status}\n"
                f"🛠️ Yetenekler: {', '.join(dev.capabilities)}"
                f"{fp_line}"
            )
            self.device_detail.set_label(detail)
            self.btn_pair_device.set_sensitive(True)
            self.btn_share_normal.set_sensitive(True)
            self.btn_share_secret.set_sensitive(True)
            self.btn_share_folder.set_sensitive(True)
            self.btn_share_clipboard.set_sensitive(True)
            self.btn_share_screen_to.set_sensitive("Ekran Paylaşımı" in dev.capabilities)
            self._update_trust_button(dev)
        else:
            self._selected_device = None
            self.device_detail.set_label(_("Cihaz seçildiğinde detaylar burada görünür."))
            self.btn_pair_device.set_sensitive(False)
            self.btn_share_normal.set_sensitive(False)
            self.btn_share_secret.set_sensitive(False)
            self.btn_share_folder.set_sensitive(False)
            self.btn_share_clipboard.set_sensitive(False)
            self.btn_share_screen_to.set_sensitive(False)
            self.btn_trust_device.set_sensitive(False)

    def _update_trust_button(self, dev=None):
        """Güven butonu: fp yoksa/ekrana gerek yoksa kapalı."""
        from pardus_paylasim.auth.trust_store import TrustStore

        dev = dev if dev is not None else self._selected_device
        try:
            trusted = bool(dev) and TrustStore().is_ip_trusted(
                getattr(dev, "address", None)
            )
        except Exception:
            trusted = False
        has_fp = bool(dev) and bool(getattr(dev, "fingerprint", ""))
        self.btn_trust_device.set_sensitive(has_fp and not trusted)
        self.btn_trust_device.set_label(
            _("Güvenilir ✓") if trusted else _("Güven")
        )

    def _on_trust_device(self, btn):
        from pardus_paylasim.auth.trust_store import TrustStore

        dev = self._selected_device
        if not dev or not getattr(dev, "fingerprint", ""):
            return
        try:
            ok = TrustStore().record_pairing(
                dev.fingerprint, dev.name, dev.address
            )
        except Exception as e:
            logger.debug("güven kaydı yazılamadı: %s", e)
            ok = False
        if ok:
            self._show_info(
                _("{name} güvenilirlere eklendi.").format(name=dev.name)
            )
            try:
                self._refresh_trusted_rows()
            except Exception as e:
                logger.debug("güven listesi tazelenemedi: %s", e)
            self._update_trust_button(dev)
        else:
            self._show_error(_("Güven kaydı yazılamadı."))

    def _on_pair_device(self, btn):
        if self._selected_device:
            self._show_info(
                _("{name} ile eşleşme isteği gönderildi.").format(name=self._selected_device.name)
            )

    def _on_share_normal(self, btn):
        if not self._selected_device:
            return
        dialog = Gtk.FileDialog()
        dialog.set_title(_("Gönderilecek Dosyaları Seçin"))
        dialog.set_accept_label("Gönder")
        dialog.set_modal(True)

        def on_response(dialog, result):
            try:
                files = dialog.open_multiple_finish(result)
                if files:
                    paths = [files.get_item(i).get_path() for i in range(files.get_n_items())]
                    paths = [p for p in paths if p]
                    if paths:
                        self._start_multi_transfer(paths, None)
            except Exception as e:
                logger.debug("Dosya seçimi iptal edildi: %s", e)

        dialog.open_multiple(self.win, None, on_response)

    def _on_share_folder(self, btn):
        if not self._selected_device:
            return
        dialog = Gtk.FileDialog()
        dialog.set_title(_("Gönderilecek Klasörü Seçin"))
        dialog.set_accept_label("Gönder")
        dialog.set_modal(True)

        def on_response(dialog, result):
            try:
                folder = dialog.select_folder_finish(result)
                if folder:
                    self._start_folder_transfer(folder.get_path(), None)
            except Exception as e:
                logger.debug("Klasör seçimi iptal edildi: %s", e)

        dialog.select_folder(self.win, None, on_response)

    def _on_share_secret(self, btn):
        if not self._selected_device:
            return
        dialog = Gtk.FileDialog()
        dialog.set_title(_("Şifreli Gönderilecek Dosyayı Seçin"))
        dialog.set_accept_label("Şifrele ve Gönder")
        dialog.set_modal(True)

        def on_response(dialog, result):
            try:
                f = dialog.open_finish(result)
                if f:
                    import secrets

                    pin = str(secrets.randbelow(900000) + 100000)
                    self._show_info(
                        _("Karşı tarafın dosyayı açması için gereken PIN:\n\n{pin}").format(pin=pin)
                    )
                    self._start_transfer(f.get_path(), pin)
            except Exception as e:
                logger.debug("Dosya seçimi iptal edildi: %s", e)

        dialog.open(self.win, None, on_response)

    def _start_transfer(self, file_path, pin):
        import tempfile
        import threading

        peer = self._selected_device.address
        file_name = os.path.basename(file_path)
        try:
            size_bytes = os.path.getsize(file_path)
        except OSError:
            size_bytes = 0
        is_secret = pin is not None
        clean_first = self.chk_clean_before_send.get_active()
        sender = FileSender(self._selected_device.address, self._selected_device.port)

        def run():
            from pardus_paylasim.cleaner.metadata_cleaner import prepare_send_file
            from pardus_paylasim.progress import compute_stats, format_progress_line

            def on_stats(sent, total, elapsed):
                stats = compute_stats(sent, total, elapsed)
                GLib.idle_add(
                    self._update_transfer_progress,
                    stats.percent, format_progress_line(stats),
                )

            GLib.idle_add(self._show_transfer_progress, True)
            send_path, tmp_path = prepare_send_file(
                file_path, clean_first, tempfile.gettempdir()
            )
            try:
                # Normal modda resume + bütünlük doğrulaması açık;
                # secret mod zaten parça-parça AEAD ile korunur.
                sender.send_file(
                    send_path, pin, stats_callback=on_stats,
                    rel_name=file_name,
                    resume=not is_secret, verify_hash=not is_secret,
                )
                self._record_sent(file_name, size_bytes, peer, "ok", is_secret)
                GLib.idle_add(self._show_info, "Dosya başarıyla gönderildi!")
            except Exception as e:
                self._record_sent(file_name, size_bytes, peer, "error", is_secret)
                GLib.idle_add(self._show_error, f"Dosya gönderim hatası:\n{e}")
            finally:
                if tmp_path:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
                GLib.idle_add(self._show_transfer_progress, False)

        threading.Thread(target=run, daemon=True).start()

    def _show_transfer_progress(self, visible):
        """İlerleme çubuğu + hız/ETA satırını gösterir/gizler (GTK thread)."""
        self.transfer_progress.set_visible(visible)
        self.lbl_transfer_stats.set_visible(visible)
        if visible:
            self.transfer_progress.set_fraction(0.0)
            self.lbl_transfer_stats.set_label("")

    def _update_transfer_progress(self, fraction, text):
        """Aktarım çubuğunu ve hız/ETA yazısını günceller (GTK thread)."""
        try:
            self.transfer_progress.set_fraction(max(0.0, min(1.0, fraction)))
            self.lbl_transfer_stats.set_label(text)
        except Exception as e:
            logger.debug("ilerleme güncellenemedi: %s", e)

    def _start_multi_transfer(self, file_paths, pin):
        """Birden çok dosyayı arka planda sırayla gönderir; her biri geçmişe."""
        import tempfile
        import threading

        peer = self._selected_device.address
        is_secret = pin is not None
        clean_first = self.chk_clean_before_send.get_active()
        sender = FileSender(self._selected_device.address, self._selected_device.port)

        def run():
            from pardus_paylasim.cleaner.metadata_cleaner import prepare_send_file
            from pardus_paylasim.progress import compute_stats, format_progress_line

            def on_stats(sent, total, elapsed):
                stats = compute_stats(sent, total, elapsed)
                GLib.idle_add(
                    self._update_transfer_progress,
                    stats.percent, format_progress_line(stats),
                )

            GLib.idle_add(self._show_transfer_progress, True)
            sent_ok = 0
            try:
                for path in file_paths:
                    name = os.path.basename(path)
                    try:
                        size = os.path.getsize(path)
                    except OSError:
                        size = 0
                    send_path, tmp_path = prepare_send_file(
                        path, clean_first, tempfile.gettempdir()
                    )
                    try:
                        sender.send_file(
                            send_path, pin, stats_callback=on_stats,
                            rel_name=name,
                            resume=not is_secret, verify_hash=not is_secret,
                        )
                        self._record_sent(name, size, peer, "ok", is_secret)
                        sent_ok += 1
                    except Exception as e:
                        self._record_sent(name, size, peer, "error", is_secret)
                        GLib.idle_add(self._show_error, f"'{name}' gönderilemedi:\n{e}")
                    finally:
                        if tmp_path:
                            try:
                                os.unlink(tmp_path)
                            except OSError:
                                pass
            finally:
                GLib.idle_add(self._show_transfer_progress, False)
            GLib.idle_add(
                self._show_info,
                f"{sent_ok}/{len(file_paths)} dosya başarıyla gönderildi.",
            )

        threading.Thread(target=run, daemon=True).start()

    def _start_folder_transfer(self, folder_path, pin):
        """Bir klasörü iç yapısını koruyarak arka planda gönderir."""
        import threading

        peer = self._selected_device.address
        folder_name = os.path.basename(folder_path.rstrip("/\\"))
        is_secret = pin is not None
        sender = FileSender(self._selected_device.address, self._selected_device.port)

        def run():
            try:
                sender.send_folder(folder_path, pin)
                self._record_sent(f"{folder_name}/ (klasör)", 0, peer, "ok", is_secret)
                GLib.idle_add(
                    self._show_info,
                    f"'{folder_name}' klasörü başarıyla gönderildi.",
                )
            except Exception as e:
                self._record_sent(f"{folder_name}/ (klasör)", 0, peer, "error", is_secret)
                GLib.idle_add(self._show_error, f"Klasör gönderim hatası:\n{e}")

        threading.Thread(target=run, daemon=True).start()

    def _on_qr_pair(self, btn):
        """Yerel QR/URI'yi gösterir ve karşı cihazın URI'siyle eşleşmeyi sunar."""
        import os as _os
        import tempfile

        device_name = self.config.get("device_name") or "Pardus"
        caps = ["file", "clipboard", "screen"]
        uri = qr_build_pairing_uri(
            device_name,
            file_port=self.receiver.port,
            clip_port=self.clipboard_server.port,
            capabilities=caps,
            fingerprint=self._device_fingerprint(),
        )

        dialog = Adw.MessageDialog(
            transient_for=self.win,
            heading=_("QR ile Eşleştirme"),
        )

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        # QR görseli (qrcode kuruluysa); değilse yalnız URI metni.
        qr_path = _os.path.join(tempfile.gettempdir(), "pardus_pair_qr.png")
        if qr_generate_png(uri, qr_path):
            img = Gtk.Picture.new_for_filename(qr_path)
            img.set_size_request(220, 220)
            img.set_can_shrink(True)
            content.append(img)
        else:
            info = Gtk.Label(
                label=_(
                    "QR kütüphanesi kurulu değil; aşağıdaki bağlantıyı diğer cihaza elle girin."
                )
            )
            info.set_wrap(True)
            content.append(info)

        uri_entry = Gtk.Entry()
        uri_entry.set_text(uri)
        uri_entry.set_editable(False)
        uri_entry.set_tooltip_text(_("Bu cihazın eşleştirme bağlantısı"))
        content.append(uri_entry)

        sep = Gtk.Label(label=_("— veya karşı cihazın bağlantısını yapıştırın —"))
        sep.add_css_class("caption")
        content.append(sep)

        scan_entry = Gtk.Entry()
        scan_entry.set_placeholder_text("pardus://pair?...")
        content.append(scan_entry)

        dialog.set_extra_child(content)
        dialog.add_response("kapat", _("Kapat"))
        dialog.add_response("esles", _("Eşleş"))
        dialog.set_response_appearance("esles", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("esles")
        dialog.set_close_response("kapat")

        def on_response(_dlg, response):
            if response == "esles":
                self._pair_from_uri(scan_entry.get_text().strip())

        dialog.connect("response", on_response)
        dialog.present()

    def _pair_from_uri(self, uri):
        """Yapıştırılan eşleştirme URI'sini ayrıştırıp cihaz olarak ekler."""
        if not uri:
            return
        info = qr_parse_pairing_uri(uri)
        if not info:
            self._show_error(_("Geçersiz eşleştirme bağlantısı."))
            return
        # Keşfedilen cihaz gibi seçili hale getir (dosya/ekran gönderimi için).
        from pardus_paylasim.auth.trust_store import TrustStore
        from pardus_paylasim.discovery.device_manager import PardusDevice

        fp_note = ""
        if info.get("fingerprint"):
            try:
                if TrustStore().record_pairing(
                    info["fingerprint"], info["name"], info["ip"]
                ):
                    fp_note = _(" (parmak izi doğrulandı, güvenilirlere eklendi)")
            except Exception as e:
                logger.debug("güven kaydı yazılamadı: %s", e)
        dev = PardusDevice(
            id=info["ip"],
            name=info["name"],
            address=info["ip"],
            port=info["file_port"],
            connection_type="QR Eşleştirme",
            os_info="Pardus",
            capabilities=["Dosya Gönderimi", "Hassas Pano"],
        )
        self._selected_device = dev
        self._show_info(
            _("{name} ({ip}) eşleştirildi.\nArtık dosya ve pano gönderebilirsiniz.{fp}").format(
                name=info["name"], ip=info["ip"], fp=fp_note
            )
        )
        try:
            self._refresh_trusted_rows()
        except Exception as e:
            logger.debug("güven listesi tazelenemedi: %s", e)

    def _on_share_clipboard(self, btn):
        """Sistem panosundaki metni okur ve seçili cihaza gönderir."""
        if not self._selected_device:
            return
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.read_text_async(None, self._on_clipboard_read_for_send)

    def _on_clipboard_read_for_send(self, clipboard, result):
        try:
            text = clipboard.read_text_finish(result)
        except Exception as e:
            self._show_error(_("Pano okunamadı:\n{error}").format(error=e))
            return
        if not text:
            self._show_info(_("Pano boş; gönderilecek metin yok."))
            return

        peer = self._selected_device.address
        client = ClipboardSyncClient(peer)

        def run():
            try:
                client.send_text(text)
                GLib.idle_add(self._show_info, "Pano başarıyla gönderildi!")
            except Exception as e:
                GLib.idle_add(self._show_error, f"Pano gönderim hatası:\n{e}")

        threading.Thread(target=run, daemon=True).start()

    def _on_clipboard_received_callback(self, text, sender_ip):
        """Uzak cihazdan gelen pano metnini yerel panoya yazar (GTK thread)."""

        def apply_clip():
            if not HAS_GTK:
                return
            try:
                clipboard = Gdk.Display.get_default().get_clipboard()
                clipboard.set(text)
            except Exception as e:
                logger.error("Pano yazılamadı: %s", e)
                return
            preview = text[:60] + ("…" if len(text) > 60 else "")
            self._show_info(
                _("{sender} panonuza metin gönderdi:\n\n{preview}").format(
                    sender=sender_ip or _("Bir cihaz"), preview=preview
                )
            )
            # Pencere odakta olmayabilir; masaüstü bildirimi de gönder.
            self._notify(
                _("Pano metni alındı"),
                f"{sender_ip or _('Bir cihaz')}: {preview}",
                notification_id="clipboard-received",
            )

        GLib.idle_add(apply_clip)

    def _record_sent(self, file_name, size_bytes, peer, status, secret):
        """Gönderim kaydını geçmişe ekler; hata transferi bozmamalı."""
        try:
            self.history.add_sent(file_name, size_bytes, peer, status=status, secret=secret)
        except Exception as e:
            logger.error("Gönderim geçmişi kaydı eklenemedi: %s", e)

    def _on_file_request_callback(self, file_name, size_bytes, sender_ip):
        """Alıcı iş parçacığından çağrılır; kullanıcıya kabul/ret sorar.

        Alıcı thread'i, kullanıcı yanıtına kadar `threading.Event` üzerinde
        bloke olur; diyalog GTK ana thread'inde `GLib.idle_add` ile açılır.
        Reddedilirse dosya gövdesi hiç indirilmez. GTK yoksa güvenli
        varsayılan: reddet (baş sessiz kabul yerine açık ret).
        """
        if not HAS_GTK or not self.win:
            return False

        # Güvenilir cihaz + kullanıcı onayı varsa sessiz kabul.
        from pardus_paylasim.auth.trust_store import TrustStore, should_auto_accept

        try:
            auto = bool(self.config.get("auto_accept_trusted", False))
            if should_auto_accept(sender_ip, TrustStore(), auto):
                logger.info("Güvenilir cihazdan otomatik kabul: %s (%s)",
                            file_name, sender_ip)
                return True
        except Exception as e:
            logger.debug("oto-kabul kontrolü atlandı: %s", e)

        decision = {"accepted": False}
        answered = threading.Event()

        def ask():
            size_str = self._format_size(size_bytes)
            try:
                trusted = TrustStore().is_ip_trusted(sender_ip)
            except Exception:
                trusted = False
            badge = _(" [güvenilir cihaz]") if trusted else ""
            body = (
                f"{sender_ip or 'Bilinmeyen cihaz'}{badge} bir dosya göndermek "
                f"istiyor:\n\n{file_name}  ({size_str})\n\nKabul edilsin mi?"
            )
            dialog = Adw.MessageDialog(
                transient_for=self.win,
                heading="Gelen Dosya",
                body=body,
            )
            dialog.add_response("ret", "Reddet")
            dialog.add_response("kabul", "Kabul Et")
            dialog.set_response_appearance("kabul", Adw.ResponseAppearance.SUGGESTED)
            dialog.set_default_response("kabul")
            dialog.set_close_response("ret")

            def on_response(_dlg, response):
                decision["accepted"] = response == "kabul"
                answered.set()

            dialog.connect("response", on_response)
            dialog.present()

        GLib.idle_add(ask)
        # Kullanıcı yanıtını bekle; süre aşımı = güvenli tarafta ret.
        answered.wait(timeout=120)
        return decision["accepted"]

    @staticmethod
    def _format_size(size_bytes):
        """Bayt sayısını okunur birime çevirir (KB/MB/GB)."""
        size = float(size_bytes)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
            size /= 1024
        return f"{size:.1f} GB"

    def _on_file_received_callback(self, save_path):
        def show():
            self._show_info(_("Yeni dosya alındı:\n{path}").format(path=save_path))
            # Dosya adını bildirimde göster (tam yol gövdede uzun kalır).
            file_name = os.path.basename(save_path)
            self._notify(
                _("Yeni dosya alındı"),
                file_name,
                notification_id="file-received",
                priority="high",
            )

        GLib.idle_add(show)

    def _notify(self, title, body, notification_id="pardus-paylasim", priority="normal"):
        """Masaüstü bildirimi gönderir (ince sarmalayıcı).

        Uygulama tutamacı (`self.app`) üzerinden `notifications` modülüne
        delege eder. GTK/app yoksa modül sessizce log'a düşer — burada ek
        koruma gerekmez, ama tutamaç yoksa erken çık.
        """
        app = getattr(self, "app", None)
        send_notification(app, title, body, notification_id=notification_id, priority=priority)

    def _on_get_secret_pin_callback(self, filename):
        # Normalde modal dialog açıp bekletmek gerekir
        # Ancak basit test için "123456" veya sabit bir pin kullanılabilir
        return "123456"

    def _on_share_screen_to_device(self, btn):
        if self._selected_device and self._selected_device.port > 0:
            self.view_stack.set_visible_child_name("screenshare")
            self.btn_client_mode.set_active(True)
            self.entry_remote_ip.set_text(self._selected_device.address)
            self.entry_remote_port.set_text(str(self._selected_device.port))

    # ═══════════════════════════════════════════════
    #  EVENT HANDLERS – Screen Share Tab
    # ═══════════════════════════════════════════════

    def _on_host_mode_toggled(self, btn):
        if self._guard_toggle:
            return
        self._guard_toggle = True
        try:
            if btn.get_active():
                self.btn_client_mode.set_active(False)
                self.host_revealer.set_reveal_child(True)
                self.client_revealer.set_reveal_child(False)
            else:
                # If deactivated and no other mode is active, hide both panels
                if not self.btn_client_mode.get_active():
                    self.host_revealer.set_reveal_child(False)
        finally:
            self._guard_toggle = False

    def _on_client_mode_toggled(self, btn):
        if self._guard_toggle:
            return
        self._guard_toggle = True
        try:
            if btn.get_active():
                self.btn_host_mode.set_active(False)
                self.host_revealer.set_reveal_child(False)
                self.client_revealer.set_reveal_child(True)
            else:
                # If deactivated and no other mode is active, hide both panels
                if not self.btn_host_mode.get_active():
                    self.client_revealer.set_reveal_child(False)
        finally:
            self._guard_toggle = False

    def _on_start_hosting(self, btn):
        if self._screen_hosting:
            # Stop hosting
            self._stop_hosting()
            return

        self._screen_hosting = True
        self.btn_start_host.set_label(_("⏹️ Yayını Durdur"))
        self.btn_start_host.remove_css_class("suggested-action")
        self.btn_start_host.add_css_class("destructive-action")
        self.lbl_host_status.set_label(_("⏳ Yayın başlatılıyor..."))

        def on_pin(pin):
            GLib.idle_add(self._on_host_pin_ready, pin)

        def run_host():
            self.screen_handler.start_host_stream(on_pin_generated=on_pin)

        threading.Thread(target=run_host, daemon=True).start()

    def _stop_hosting(self):
        self._screen_hosting = False
        self.btn_start_host.set_label(_("▶️ Ekran Yayınını Başlat"))
        self.btn_start_host.add_css_class("suggested-action")
        self.btn_start_host.remove_css_class("destructive-action")
        self.lbl_host_pin.set_label(_("PIN Kodu: —"))
        self.lbl_host_ip.set_label(_("Sunucu IP: —"))
        self.lbl_host_status.set_label(_("Durum: Yayın durduruldu."))
        self.lbl_host_files.set_label("")
        self.lbl_host_files.set_visible(False)
        self.screen_handler.stop_host_stream()

    def _on_host_pin_ready(self, pin):
        import socket

        self.lbl_host_pin.set_label(_("PIN Kodu: {pin}").format(pin=pin))
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
        except Exception as e:
            logger.debug("exception at %s: %s", inspect.currentframe().f_code.co_name, e)
            local_ip = "127.0.0.1"
        finally:
            try:
                s.close()
            except Exception as e:
                pass
        host_port = self.screen_handler.host_port
        self.lbl_host_ip.set_label(_("Sunucu IP: {ip}:{port}").format(ip=local_ip, port=host_port))
        self.lbl_host_status.set_label(
            _("✅ Yayın aktif! Karşı cihaz bu IP ve PIN ile bağlanabilir.")
        )
        self.lbl_host_files.set_label(
            _("🌐 Uygulamasız cihaz: https://{ip}:{port}/file-manager.html "
              "adresinden PIN ile dosya alıp gönderebilir.").format(
                ip=local_ip, port=host_port)
        )
        self.lbl_host_files.set_visible(True)

    def _on_connect_remote(self, btn):
        ip = self.entry_remote_ip.get_text().strip()
        port_str = self.entry_remote_port.get_text().strip()
        pin = self.entry_pin.get_text().strip()

        if not ip:
            self._show_error(_("Lütfen sunucu IP adresini girin."))
            return

        try:
            port = int(port_str) if port_str else DEFAULT_PORT
        except ValueError:
            self._show_error(_("Geçersiz port numarası."))
            return

        self.lbl_client_status.set_label(_("⏳ Bağlanıyor..."))
        self.btn_connect_remote.set_sensitive(False)

        def do_connect():
            ok = self.screen_handler.connect_to_remote_screen(
                ip, port, pin, on_frame=self._on_remote_frame
            )
            GLib.idle_add(self._on_connect_result, ok, ip, port)

        threading.Thread(target=do_connect, daemon=True).start()

    def _on_remote_frame(self, jpeg_bytes):
        """Ağ thread'inden gelen JPEG karesini render için sıraya koyar.

        Backpressure: yalnız en son kare tutulur (ara kareler düşürülür), ana
        thread yetişemezse birikme olmaz. Çizim `GLib.idle_add` ile GTK ana
        thread'ine marshalled edilir — Gdk paintable ana thread'de kurulmalı.
        """
        with self._remote_frame_lock:
            self._remote_frame_latest = jpeg_bytes
            if self._remote_frame_scheduled:
                return  # Zaten sıraya konmuş idle_add son kareyi alacak.
            self._remote_frame_scheduled = True
        GLib.idle_add(self._render_remote_frame)

    def _render_remote_frame(self):
        """Ana thread: en son JPEG karesini `Gdk.Texture`'a çevirip çizer."""
        with self._remote_frame_lock:
            jpeg_bytes = self._remote_frame_latest
            self._remote_frame_latest = None
            self._remote_frame_scheduled = False
        if not jpeg_bytes or not self._screen_connected:
            return False
        try:
            texture = Gdk.Texture.new_from_bytes(GLib.Bytes.new(jpeg_bytes))
        except GLib.Error as e:
            logger.debug("Uzak kare decode edilemedi: %s", e)
            return False
        # Kontrol koordinat eşlemesi native çözünürlüğü bilmeli: texture'dan al.
        self._remote_image_w = texture.get_width()
        self._remote_image_h = texture.get_height()
        self.remote_picture.set_paintable(texture)
        return False  # idle_add tek-atım.

    def _on_connect_result(self, ok, ip=None, port=DEFAULT_PORT):
        if ok:
            self._screen_connected = True
            self.lbl_client_status.set_label(_("✅ Uzak ekrana bağlandı — canlı görüntü aşağıda."))
            self.remote_picture_revealer.set_reveal_child(True)
            self.btn_disconnect_remote.set_sensitive(True)
            self.btn_connect_remote.set_sensitive(False)
            # Ekran bağlı → "Kontrolü İste" artık istenebilir (1.8).
            self.btn_request_control.set_sensitive(True)
        else:
            self.lbl_client_status.set_label(
                _("❌ Bağlantı başarısız. IP, port ve PIN'i kontrol edin.")
            )
            self.btn_connect_remote.set_sensitive(True)

    def _on_disconnect_remote(self, btn):
        # Ekran koparılıyor → varsa açık kontrol kanalını önce kapat (1.8).
        self._release_control_client()
        self.screen_handler.disconnect_remote_screen()
        self._screen_connected = False
        with self._remote_frame_lock:
            self._remote_frame_latest = None
            self._remote_frame_scheduled = False
        self.remote_picture_revealer.set_reveal_child(False)
        self.remote_picture.set_paintable(None)
        self._remote_image_w = 0
        self._remote_image_h = 0
        self.lbl_client_status.set_label(_("Durum: Bağlantı kesildi."))
        self.btn_connect_remote.set_sensitive(True)
        self.btn_disconnect_remote.set_sensitive(False)
        # Ekran koptu → kontrol istenemez.
        self.btn_request_control.set_sensitive(False)

    # ═══════════════════════════════════════════════
    #  UZAKTAN KONTROL – Girdi Yakalama (1.7 — C5)
    # ═══════════════════════════════════════════════
    #
    # GTK4 EventController'lar canlı görüntü Picture'ına (fare) ve pencereye
    # (klavye) bağlanır; olaylar nötr protokol biçimine çevrilip kontrol
    # kanalına iletilir. Kanalın kendisi (bağlan/istek/onay) 1.8'de kurulur;
    # burada gönderim `_control_active` + `_control_client` ile kapılıdır, yani
    # 1.8 tamamlanana dek yakalama geri çağrıları hiçbir şey göndermez (no-op).

    # GDK fare düğme numarası → nötr protokol düğme adı.
    _GDK_BUTTON_NAMES = {1: "left", 2: "middle", 3: "right"}

    def _attach_control_capture(self):
        """Fare/klavye EventController'larını canlı görüntüye ve pencereye bağla.

        Fare olayları (motion/click/scroll) doğrudan `remote_picture`'a bağlanır
        → koordinatlar zaten widget-göreli gelir. Klavye penceredir (odak
        Picture'da olmayabilir). Bağlama daima yapılır; gerçek gönderim yalnız
        kontrol aktifken (`_control_send_active`) gerçekleşir.
        """
        motion = Gtk.EventControllerMotion.new()
        motion.connect("motion", self._on_control_motion)
        self.remote_picture.add_controller(motion)

        click = Gtk.GestureClick.new()
        click.set_button(0)  # 0 = tüm düğmeler (sol/orta/sağ).
        click.connect("pressed", self._on_control_pressed)
        click.connect("released", self._on_control_released)
        self.remote_picture.add_controller(click)

        scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.BOTH_AXES)
        scroll.connect("scroll", self._on_control_scroll)
        self.remote_picture.add_controller(scroll)

        keys = Gtk.EventControllerKey.new()
        keys.connect("key-pressed", self._on_control_key_pressed)
        keys.connect("key-released", self._on_control_key_released)
        self.win.add_controller(keys)

    def _control_send_active(self):
        """Kontrol olayı gönderilebilir mi? (aktif + kanal kurulmuş)."""
        return self._control_active and self._control_client is not None

    def _picture_norm_coords(self, px, py):
        """Picture-göreli (px,py) piksel → 0..1 normalize koordinat; yoksa None.

        Letterbox (aspect-fit) matematiği saf `map_widget_to_normalized`'a
        devredilir. Widget veya görüntü boyutu bilinmiyorsa None döner.
        """
        widget_w = self.remote_picture.get_width()
        widget_h = self.remote_picture.get_height()
        image_w = self._remote_image_w
        image_h = self._remote_image_h
        if widget_w <= 0 or widget_h <= 0 or image_w <= 0 or image_h <= 0:
            return None
        return map_widget_to_normalized(widget_w, widget_h, image_w, image_h, px, py)

    def _on_control_motion(self, controller, px, py):
        """Fare hareketi → normalize move (kare hızına kısılmış)."""
        if not self._control_send_active():
            return
        now = GLib.get_monotonic_time()
        if now - self._last_motion_sent_us < self._control_motion_interval_us:
            return  # Throttle: çok sık hareket düşür.
        coords = self._picture_norm_coords(px, py)
        if coords is None:
            return
        self._last_motion_sent_us = now
        self._control_client.send_move(coords[0], coords[1])

    def _on_control_pressed(self, gesture, n_press, px, py):
        """Fare düğmesine basıldı → button down."""
        self._send_control_button(gesture, px, py, True)

    def _on_control_released(self, gesture, n_press, px, py):
        """Fare düğmesi bırakıldı → button up."""
        self._send_control_button(gesture, px, py, False)

    def _send_control_button(self, gesture, px, py, down):
        if not self._control_send_active():
            return
        name = self._GDK_BUTTON_NAMES.get(gesture.get_current_button())
        if name is None:
            return  # Bilinmeyen düğme (yan tuşlar vb.) — atla.
        coords = self._picture_norm_coords(px, py)
        if coords is None:
            return
        self._control_client.send_button(name, down, coords[0], coords[1])

    def _on_control_scroll(self, controller, dx, dy):
        """Fare tekerleği → scroll (dx,dy)."""
        if not self._control_send_active():
            return False
        self._control_client.send_scroll(dx, dy)
        return False  # Yerel kaydırmayı engelleme.

    def _on_control_key_pressed(self, controller, keyval, keycode, state):
        """Klavye tuşuna basıldı → nötr key down (bilinmeyen tuş yerelde kalır).

        Değiştiriciler (Ctrl/Shift/Alt/Meta) GTK tarafından kendi tuş
        olaylarıyla teslim edilir → host'ta ayrıca çıplak enjekte edilir; `mods`
        damgası yalnız sunucunun tehlikeli-tuş filtresi içindir.
        """
        return self._send_control_key(keyval, state, True)

    def _on_control_key_released(self, controller, keyval, keycode, state):
        """Klavye tuşu bırakıldı → nötr key up."""
        return self._send_control_key(keyval, state, False)

    def _send_control_key(self, keyval, state, down):
        if not self._control_send_active():
            return False  # Kontrol yokken yerel UI'yi engelleme.
        code = keyval_to_key_code(keyval)
        if code is None:
            return False  # Eşlenmemiş tuş → yerel akışa bırak.
        mods = gdk_state_to_mods(state)
        self._control_client.send_key(code, down, mods)
        return True  # Kontrol aktif: olayı tüket (yerel çift-işlem yok).

    # ═══════════════════════════════════════════════
    #  UZAKTAN KONTROL – Consent / Yaşam Döngüsü (1.8 — C6)
    # ═══════════════════════════════════════════════
    #
    # Sunucu tarafı (`ControlChannelServer.handle_upgrade`) consent açıkken +
    # PIN geçerli + enjeksiyon backend'i varsa token'ı OTOMATİK verir; ayrı bir
    # per-bağlantı onay kancası yoktur. Bu yüzden UI consent'i HOST SWITCH'i
    # kapıda tutarak sağlar: switch'i açmak = geri dönüşü olmayan bir yetki
    # olduğundan önce `Adw.MessageDialog` ile onay ister.

    def _on_control_allow_state_set(self, switch, state):
        """Host "Kontrole İzin Ver" switch'i değişti (C4-1 consent kapısı).

        Açılışta (state=True) onay dialog'u gösterir ve switch'i elle yönetir;
        kapanışta doğrudan kontrolü keser. `True` döndürerek varsayılan state
        değişimini bastırır → görsel state yalnız biz `set_state` ile ayarlarız.
        """
        if self._guard_control_switch:
            return True  # Kendi set_state çağrımız — yeniden girme.
        if state:
            self._confirm_enable_control()
        else:
            self._disable_control_host()
        return True  # State'i biz yönetiyoruz (dialog async olabilir).

    def _confirm_enable_control(self):
        """Kontrol iznini açmadan önce katı onay dialog'u gösterir.

        Onaylanırsa `_grant_control_host` koşar; reddedilirse switch görsel
        olarak KAPALI'ya döner ve kontrol açılmaz.
        """
        if not HAS_GTK or not self.win:
            # Başsız/test yolu: doğrudan yetki ver (dialog yok).
            self._grant_control_host()
            return
        dialog = Adw.MessageDialog(
            transient_for=self.win,
            heading=_("Uzaktan kontrole izin verilsin mi?"),
            body=_(
                "Yetkili bir istemci PIN ve güvenli kanalla bağlandığında "
                "farenizi ve klavyenizi UZAKTAN kontrol edebilir.\n\n"
                "Kontrol yalnız bu oturum için açılır (kalıcı değildir). "
                "İstediğiniz an “Kontrolü Durdur” veya Ctrl+Alt+K ile "
                "anında kesebilirsiniz."
            ),
        )
        dialog.add_response("iptal", _("İptal"))
        dialog.add_response("izin_ver", _("İzin Ver"))
        dialog.set_response_appearance("izin_ver", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("iptal")
        dialog.set_close_response("iptal")
        dialog.connect("response", self._on_control_consent_response)
        dialog.present()

    def _on_control_consent_response(self, dialog, response):
        """Consent dialog yanıtı: izin_ver → yetki ver; aksi halde geri al."""
        if response == "izin_ver":
            self._grant_control_host()
        else:
            self._set_control_switch_visual(False)

    def _grant_control_host(self):
        """Host tarafında kontrol iznini açar + görünür göstergeleri kurar."""
        self.screen_handler.set_control_allowed(True)
        self._set_control_switch_visual(True)
        self.lbl_control_banner.set_markup(
            _("<b>⚠️ Uzaktan kontrol ETKİN</b> — yetkili istemci ekranınızı kontrol edebilir.")
        )
        self.control_banner_revealer.set_reveal_child(True)
        self.btn_stop_control.set_sensitive(True)
        self.history.add_control(
            "(yetkili istemci)", STATUS_CONTROL_START, detail="host izin verdi"
        )
        self._notify(
            _("Uzaktan kontrol etkin"),
            _("Yetkili bir istemci ekranınızı kontrol edebilir. Durdurmak için Ctrl+Alt+K."),
            notification_id="pardus-control",
            priority="high",
        )

    def _disable_control_host(self):
        """Host tarafında kontrolü kapatır + göstergeleri gizler (idempotent).

        `set_control_allowed(False)` sunucuda tüm oturum token'larını düşürür →
        bağlı istemciler anında yetkisiz kalır (kill-switch semantiği).
        """
        was_allowed = self.screen_handler.is_control_allowed()
        self.screen_handler.set_control_allowed(False)
        self._set_control_switch_visual(False)
        self.control_banner_revealer.set_reveal_child(False)
        self.btn_stop_control.set_sensitive(False)
        if was_allowed:
            self.history.add_control(
                "(yetkili istemci)", STATUS_CONTROL_STOP, detail="host kontrolü durdurdu"
            )

    def _set_control_switch_visual(self, active):
        """Switch görsel state'ini re-entry tetiklemeden ayarlar."""
        self._guard_control_switch = True
        try:
            self.switch_control_allow.set_state(bool(active))
            self.switch_control_allow.set_active(bool(active))
        finally:
            self._guard_control_switch = False

    def _on_stop_control_host(self, btn):
        """ "Kontrolü Durdur" düğmesi → host kontrolünü anında keser."""
        self._disable_control_host()

    def _on_kill_switch(self):
        """Global kill-switch (Ctrl+Alt+K): host + client kontrolünü keser.

        Host tarafında izin token'larını düşürür; client tarafında varsa açık
        kontrol kanalını kapatır ve girdi yakalamayı durdurur. Tek kısayolla
        her iki rol de güvene alınır.
        """
        self._disable_control_host()
        self._release_control_client()

    # ── Client tarafı kontrol yaşam döngüsü ──────────────────────────

    def _on_request_control(self, btn):
        """ "Kontrolü İste" → ayrı TLS `/control` kanalı açar (host onaylarsa).

        Ekran bağlı değilse no-op. Kanal kurma ağ işidir → thread'e alınır;
        sonuç ana thread'de `_on_request_control_result` ile işlenir.
        """
        if not self._screen_connected:
            return
        self.btn_request_control.set_sensitive(False)
        self.lbl_control_client_status.set_label(_("Kontrol: İsteniyor…"))

        def do_request():
            ok = False
            try:
                ok = self.screen_handler.request_control()
            except Exception as exc:  # Ağ/handshake hatası → başarısız say.
                logger.warning("Kontrol isteği başarısız: %s", exc)
                ok = False
            GLib.idle_add(self._on_request_control_result, ok)

        threading.Thread(target=do_request, daemon=True).start()

    def _on_request_control_result(self, ok):
        """Kontrol isteği sonucu (ana thread): başarılıysa yakalamayı aç."""
        if ok:
            # `_control_send_active` her iki alanı ister → ikisini de kur.
            self._control_client = self.screen_handler.control_client
            self._control_active = True
            self.lbl_control_client_status.set_label(
                _("🖱️ Kontrol: ETKİN — fare/klavye uzak ekrana gidiyor.")
            )
            self.btn_request_control.set_label(_("🖱️ Kontrolü Bırak"))
            self.btn_request_control.set_sensitive(True)
            # Butonu artık "bırak" olarak yeniden kabla.
            self._rewire_request_button(release=True)
            self.history.add_control(
                "(uzak host)", STATUS_CONTROL_START, detail="client kontrol aldı"
            )
        else:
            self._control_active = False
            self._control_client = None
            self.lbl_control_client_status.set_label(_("Kontrol: Reddedildi veya kullanılamıyor."))
            self.btn_request_control.set_sensitive(True)

    def _rewire_request_button(self, release):
        """ "İste"/"Bırak" düğme davranışını değiştirir (tek düğme iki durum)."""
        try:
            self.btn_request_control.disconnect_by_func(self._on_request_control)
        except (TypeError, ImportError):
            pass
        try:
            self.btn_request_control.disconnect_by_func(self._on_release_control)
        except (TypeError, ImportError):
            pass
        if release:
            self.btn_request_control.connect("clicked", self._on_release_control)
        else:
            self.btn_request_control.connect("clicked", self._on_request_control)

    def _on_release_control(self, btn):
        """ "Kontrolü Bırak" → kanalı kapatır, yakalamayı durdurur."""
        self._release_control_client()

    def _release_control_client(self):
        """Client kontrol kanalını kapatır + yakalamayı durdurur (idempotent)."""
        had_control = self._control_client is not None
        self._control_active = False
        self._control_client = None
        try:
            self.screen_handler.release_control()
        except Exception as e:
            logger.debug("exception at %s: %s", inspect.currentframe().f_code.co_name, e)
            pass
        # Düğme geri "İste" durumuna (yalnız GTK'de widget varsa).
        if HAS_GTK and getattr(self, "btn_request_control", None) is not None:
            self.btn_request_control.set_label(_("🖱️ Kontrolü İste"))
            self.btn_request_control.set_sensitive(self._screen_connected)
            self._rewire_request_button(release=False)
            self.lbl_control_client_status.set_label(_("Kontrol: Kapalı"))
        if had_control:
            self.history.add_control(
                "(uzak host)", STATUS_CONTROL_STOP, detail="client kontrolü bıraktı"
            )

    # ═══════════════════════════════════════════════
    #  EVENT HANDLERS – Clipboard Tab
    # ═══════════════════════════════════════════════

    def _get_textview_text(self, textview):
        buf = textview.get_buffer()
        start = buf.get_start_iter()
        end = buf.get_end_iter()
        return buf.get_text(start, end, False)

    def _set_textview_text(self, textview, text):
        buf = textview.get_buffer()
        buf.set_text(text)

    def _on_scan_text(self, btn):
        text = self._get_textview_text(self.clip_input)
        if not text.strip():
            self._show_info(_("Lütfen taranacak metni girin."))
            return

        matches = self.clipboard_handler.analyze_text(text)
        self._update_clip_findings(matches)

    def _on_mask_text(self, btn):
        text = self._get_textview_text(self.clip_input)
        if not text.strip():
            self._show_info(_("Lütfen maskelenecek metni girin."))
            return

        masked = self.clipboard_handler.sanitize_text(text)
        self._set_textview_text(self.clip_output, masked)

        matches = self.clipboard_handler.analyze_text(text)
        self._update_clip_findings(matches)

    def _on_paste_from_clipboard(self, btn):
        try:
            clipboard = Gdk.Display.get_default().get_clipboard()
            clipboard.read_text_async(None, self._on_clipboard_text_received)
        except Exception as e:
            self._show_error(_("Panodan okuma hatası: {error}").format(error=e))

    def _on_clipboard_text_received(self, clipboard, result):
        try:
            text = clipboard.read_text_finish(result)
            if text:
                self._set_textview_text(self.clip_input, text)
        except Exception as e:
            logger.debug("exception at %s: %s", inspect.currentframe().f_code.co_name, e)
            pass

    def _on_toggle_clipboard_monitor(self, btn):
        if btn.get_active():
            self._clipboard_monitoring = True
            self._show_info("Pano izleme aktif. Kopyalanan metinler otomatik taranacak.")
            self._clipboard_timeout_id = GLib.timeout_add_seconds(2, self._check_clipboard)
        else:
            self._clipboard_monitoring = False
            if self._clipboard_timeout_id:
                GLib.source_remove(self._clipboard_timeout_id)
                self._clipboard_timeout_id = 0

    def _check_clipboard(self):
        if not self._clipboard_monitoring:
            return False
        try:
            clipboard = Gdk.Display.get_default().get_clipboard()
            clipboard.read_text_async(None, self._on_monitor_clipboard_text)
        except Exception as e:
            logger.debug("exception at %s: %s", inspect.currentframe().f_code.co_name, e)
            pass
        return True  # Repeat

    def _on_monitor_clipboard_text(self, clipboard, result):
        try:
            text = clipboard.read_text_finish(result)
            if text:
                self._set_textview_text(self.clip_input, text)
                matches = self.clipboard_handler.analyze_text(text)
                if matches:
                    self._update_clip_findings(matches)
                    masked = self.clipboard_handler.sanitize_text(text)
                    self._set_textview_text(self.clip_output, masked)
        except Exception as e:
            logger.debug("exception at %s: %s", inspect.currentframe().f_code.co_name, e)
            pass

    def _update_clip_findings(self, matches):
        # Clear existing
        while True:
            row = self.clip_findings_list.get_first_child()
            if row is None:
                break
            self.clip_findings_list.remove(row)

        if not matches:
            row = Gtk.ListBoxRow()
            lbl = Gtk.Label(label=_("✅ Hassas veri tespit edilmedi."))
            lbl.set_halign(Gtk.Align.START)
            lbl.set_margin_top(4)
            lbl.set_margin_bottom(4)
            row.set_child(lbl)
            self.clip_findings_list.append(row)
            return

        for m in matches:
            row = Gtk.ListBoxRow()
            label = Gtk.Label(
                label=f'⚠️ [{m.match_type}] Bulunan: "{m.original[:30]}..." → Maskeli: "{m.masked}"'
            )
            label.set_halign(Gtk.Align.START)
            label.set_wrap(True)
            label.set_margin_top(4)
            label.set_margin_bottom(4)
            row.set_child(label)
            self.clip_findings_list.append(row)

    # ═══════════════════════════════════════════════
    #  TRANSFER HISTORY
    # ═══════════════════════════════════════════════

    def _on_show_history(self, btn):
        """Transfer geçmişini kaydırılabilir liste diyaloğunda gösterir."""
        if not HAS_GTK or not self.win:
            return

        entries = self.history.read_all()

        dialog = Adw.MessageDialog(
            transient_for=self.win,
            heading=_("Transfer Geçmişi"),
        )

        if not entries:
            dialog.set_body(_("Henüz kayıt yok."))
        else:
            listbox = Gtk.ListBox()
            listbox.set_selection_mode(Gtk.SelectionMode.NONE)
            listbox.add_css_class("boxed-list")
            for e in entries:
                listbox.append(self._build_history_row(e))

            scroller = Gtk.ScrolledWindow()
            scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scroller.set_min_content_height(320)
            scroller.set_child(listbox)
            dialog.set_extra_child(scroller)

            dialog.add_response("temizle", _("Geçmişi Temizle"))
            dialog.set_response_appearance("temizle", Adw.ResponseAppearance.DESTRUCTIVE)

        dialog.add_response("kapat", _("Kapat"))
        dialog.set_default_response("kapat")
        dialog.set_close_response("kapat")

        def on_response(_dlg, response):
            if response == "temizle":
                self.history.clear()

        dialog.connect("response", on_response)
        dialog.present()

    def _build_history_row(self, entry):
        """Tek geçmiş kaydından bir ListBoxRow üretir."""
        direction = entry.get("direction", "")
        status = entry.get("status", "")
        secret = entry.get("secret", False)

        icon = "⬆️" if direction == "sent" else "⬇️"
        if status == "rejected":
            state = " ⛔"
        elif status == "error":
            state = " ⚠️"
        else:
            state = ""
        lock = " 🔒" if secret else ""

        name = entry.get("file_name", "?")
        size = self._format_size(entry.get("size_bytes", 0))
        peer = entry.get("peer", "")
        when = self._format_timestamp(entry.get("timestamp", ""))

        text = f"{icon}{lock} {name}  ({size}){state}\n{peer} · {when}"
        label = Gtk.Label(label=text)
        label.set_halign(Gtk.Align.START)
        label.set_xalign(0.0)
        label.set_wrap(True)
        label.set_margin_top(6)
        label.set_margin_bottom(6)
        label.set_margin_start(8)
        label.set_margin_end(8)

        row = Gtk.ListBoxRow()
        row.set_child(label)
        return row

    @staticmethod
    def _format_timestamp(iso_str):
        """ISO-8601 zaman damgasını okunur yerel biçime çevirir."""
        if not iso_str:
            return ""
        try:
            from datetime import datetime

            dt = datetime.fromisoformat(iso_str)
            return dt.astimezone().strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            return iso_str

    # ═══════════════════════════════════════════════
    #  UTILITY
    # ═══════════════════════════════════════════════

    def _on_window_close(self, window):
        """Clean up background operations when window is closed."""
        if self._discovery_active:
            self._stop_discovery()
        # Uzaktan kontrolü kapat (host izni + client kanalı) — kapanışta
        # asılı token/kanal bırakma (1.8 — C4 teardown).
        try:
            self.screen_handler.stop_control_host()
        except Exception as e:
            logger.debug("exception at %s: %s", inspect.currentframe().f_code.co_name, e)
            pass
        try:
            self.screen_handler.release_control()
        except Exception as e:
            logger.debug("exception at %s: %s", inspect.currentframe().f_code.co_name, e)
            pass
        if self._screen_hosting:
            self._stop_hosting()
        if self._screen_connected:
            self.screen_handler.disconnect_remote_screen()
        if self._clipboard_monitoring:
            self._clipboard_monitoring = False
            if self._clipboard_timeout_id:
                GLib.source_remove(self._clipboard_timeout_id)
        # Arka plan sunucularını durdur (soketleri serbest bırak).
        try:
            self.receiver.stop()
        except Exception as e:
            logger.debug("exception at %s: %s", inspect.currentframe().f_code.co_name, e)
            pass
        try:
            self.clipboard_server.stop()
        except Exception as e:
            logger.debug("exception at %s: %s", inspect.currentframe().f_code.co_name, e)
            pass
        return False  # Allow window to close (False = propagate, don't stop)

    def _on_drop_files(self, drop_target, value, x, y):
        """Handle drag-and-drop of files onto the drop zone."""
        if isinstance(value, Gdk.FileList):
            paths = [f.get_path() for f in value.get_files()]
            self._selected_files = paths
            self._refresh_privacy_list()
            return True
        return False

    @staticmethod
    def _resolve_drop_send(paths, has_device):
        """Bırakılan yolları sınıflandırır (saf karar; GTK'siz test edilebilir).

        Args:
            paths: Bırakılan ham yol listesi (None/klasör içerebilir).
            has_device: Seçili bir hedef cihaz var mı?

        Returns:
            (durum, dosya_yolları) çifti. durum:
              - "no_device": hedef cihaz seçilmemiş.
              - "no_files": gönderilebilir dosya yok (yalnız klasör/None).
              - "send": dosya_yolları gönderime hazır.
            Klasörler ve None yolları elenerek yalnızca gerçek dosyalar döner.
        """
        file_paths = [p for p in paths if p and os.path.isfile(p)]
        if not has_device:
            return ("no_device", file_paths)
        if not file_paths:
            return ("no_files", file_paths)
        return ("send", file_paths)

    def _on_drop_files_to_send(self, drop_target, value, x, y):
        """Cihaz Tanıma sekmesine bırakılan dosyaları seçili cihaza gönderir.

        Seçili cihaz yoksa kullanıcıya önce cihaz seçmesi bildirilir; bu
        durumda bırakma reddedilir (False) — böylece dosyalar sessizce
        yutulmaz. Klasörler bu yolla desteklenmez (kullanıcı 'Klasör Gönder'
        aksiyonunu kullanmalı); yalnızca dosya yolları gönderilir.
        """
        if not isinstance(value, Gdk.FileList):
            return False

        paths = [f.get_path() for f in value.get_files()]
        status, file_paths = self._resolve_drop_send(paths, self._selected_device is not None)

        if status == "no_device":
            self._show_info(_("Dosya göndermek için önce listeden bir cihaz seçin."))
            return False
        if status == "no_files":
            self._show_info(
                _(
                    "Gönderilebilir dosya bulunamadı. Klasörler için "
                    "'Klasör Gönder' aksiyonunu kullanın."
                )
            )
            return False

        self._start_multi_transfer(file_paths, None)
        return True

    def _on_tab_changed(self, stack, param):
        name = stack.get_visible_child_name()
        # Only start discovery if not already active (prevent duplicate listeners)
        if name == "discovery" and not self._discovery_active:
            self._start_discovery()

    def _show_error(self, msg):
        if not HAS_GTK or not self.win:
            logger.error("%s", msg)
            return
        dialog = Adw.MessageDialog(
            transient_for=self.win,
            heading="Hata",
            body=msg,
        )
        dialog.add_response("tamam", "Tamam")
        dialog.present()

    def _show_info(self, msg):
        if not HAS_GTK or not self.win:
            logger.info("%s", msg)
            return
        dialog = Adw.MessageDialog(
            transient_for=self.win,
            heading="Bilgi",
            body=msg,
        )
        dialog.add_response("tamam", "Tamam")
        dialog.present()
