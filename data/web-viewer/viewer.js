/*
 * Pardus Paylaşım — uzak ekran web viewer istemci mantığı.
 *
 * Görüntüleme:  <img src="/stream?pin=PIN">  (multipart MJPEG, tarayıcı native).
 * Kontrol:      WebSocket  wss://host/control?pin=PIN
 *
 * Tarayıcı <img> ve WebSocket'e özel HTTP başlığı EKLEYEMEZ → PIN sorgu
 * parametresiyle taşınır (sunucu `_check_auth` header'ı tercih eder, query
 * fallback'i destekler). Aynı-origin + TLS + bastırılmış erişim günlüğü altında
 * kabul edilebilir. Sunucu WS'e bağlanınca İLK metin çerçevesi olarak `grant`
 * gönderir (izin + oturum token'ı); istemci token'ı yakalar ve SONRAKİ her
 * mesaja `sid` olarak ekler. `control_protocol.py` tel formatıyla birebir uyumlu.
 *
 * CSP 'self' altında çalışır: satır-içi script/handler yok, harici kaynak yok.
 */

"use strict";

(function () {
  // --- Tel protokol sabitleri (control_protocol.py ile eşleşmeli) ---
  var PROTOCOL_VERSION = 1;
  var SCROLL_MAX = 100.0;

  // Fare düğmesi index → nötr ad (protokol BUTTONS kümesi).
  var BUTTON_NAMES = { 0: "left", 1: "middle", 2: "right" };

  // Tarayıcı KeyboardEvent.code (fiziksel, düzen-bağımsız) → evdev KEY_* enum.
  // Fiziksel `code` kullanılır: klavye düzeninden bağımsız, host tuş kodu eşlemesi
  // (protokol KEY_CODES) ile aynı felsefe. Eşlenmeyen tuşlar sessizce atlanır.
  var KEY_MAP = buildKeyMap();

  // Hareket gönderim kısması (ms). Frame hızını aşan pointermove selini bağlar.
  var MOVE_THROTTLE_MS = 30;

  // Tekerlek delta → protokol kaydırma adımı böleni (kabaca satır).
  var WHEEL_DIVISOR = 40;

  // --- DOM referansları ---
  var els = {
    form: document.getElementById("conn-form"),
    pin: document.getElementById("pin"),
    connect: document.getElementById("btn-connect"),
    control: document.getElementById("btn-control"),
    kill: document.getElementById("btn-kill"),
    upload: document.getElementById("btn-upload"),
    fm: document.getElementById("btn-fm"),
    fileInput: document.getElementById("file-input"),
    monitorSelect: document.getElementById("monitor-select"),
    qualitySelect: document.getElementById("quality-select"),
    chatPanel: document.getElementById("chat-panel"),
    chatMessages: document.getElementById("chat-messages"),
    chatForm: document.getElementById("chat-form"),
    chatInput: document.getElementById("chat-input"),
    frame: document.getElementById("frame"),
    screen: document.getElementById("screen"),
    brand: document.querySelector(".brand"),
    status: document.getElementById("status"),
    host: document.getElementById("host"),
    fingerprint: document.getElementById("fingerprint"),
    backend: document.getElementById("backend"),
  };

  // --- Durum ---
  var state = {
    pin: "",
    deviceId: "",
    watching: false,
    ws: null,
    token: null, // grant sonrası oturum token'ı (sid)
    controlling: false,
    lastMoveAt: 0,
    pendingMove: null, // {x, y} — throttle penceresinde biriken son konum
    moveTimer: null,
  };

  // ---------------------------------------------------------------------------
  // Başlangıç
  // ---------------------------------------------------------------------------

  function init() {
    var savedId = localStorage.getItem("pardusDeviceId");
    if (!savedId) {
      savedId = "dev-" + Math.random().toString(36).substr(2, 9);
      localStorage.setItem("pardusDeviceId", savedId);
    }
    state.deviceId = savedId;

    // URL'de ?pin= varsa PIN alanını önceden doldur (paylaşılabilir bağlantı).
    var urlPin = new URLSearchParams(window.location.search).get("pin");
    if (urlPin) {
      els.pin.value = urlPin.replace(/[^0-9]/g, "").slice(0, 6);
    }

    els.host.textContent = window.location.host || "—";

    els.form.addEventListener("submit", onWatchSubmit);
    els.control.addEventListener("click", onRequestControl);
    els.kill.addEventListener("click", onReleaseControl);
    els.upload.addEventListener("click", function() { els.fileInput.click(); });
    els.fm.addEventListener("click", function() {
        window.open("/file-manager.html", "_blank");
    });
    els.fileInput.addEventListener("change", onFileSelected);
    els.screen.addEventListener("error", onStreamError);
    els.screen.addEventListener("load", onStreamLoad);

    // Host meta bilgisini çek (parmak izi / kontrol backend). Auth'suz uç nokta.
    fetchInfo();
  }

  // ---------------------------------------------------------------------------
  // Görüntüleme (MJPEG)
  // ---------------------------------------------------------------------------

  function onWatchSubmit(ev) {
    ev.preventDefault();
    var pin = (els.pin.value || "").replace(/[^0-9]/g, "");
    if (pin.length < 4) {
      setStatus("PIN geçersiz", "err");
      els.pin.focus();
      return;
    }
    
    setStatus("doğrulanıyor...", "wait");
    fetch("/auth", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pin: pin })
    })
    .then(function(res) {
      if (!res.ok) throw new Error("PIN reddedildi");
      return res.json();
    })
    .then(function(data) {
      state.pin = pin; // Geriye dönük uyumluluk, ama artık token (cookie) kullanılacak
      startWatching();
    })
    .catch(function(err) {
      console.error(err);
      setStatus("yanlış PIN", "err");
    });
  }

  els.monitorSelect.addEventListener("change", function() {
    if (state.watching) restartWatching();
  });
  
  els.qualitySelect.addEventListener("change", function() {
    if (state.watching) restartWatching();
  });

  function restartWatching() {
    onStreamError(); // state.watching = false ve her şeyi durdurur, ama PC ve DC'yi de kapatmamız lazım
    if (state.pc) {
      state.pc.close();
      state.pc = null;
    }
    if (state.ws) {
      state.ws.close();
      state.ws = null;
    }
    startWatching();
  }

  function startWatching() {
    setStatus("bağlanıyor (WebRTC)…", "wait");
    
    if (state.pc) {
      state.pc.close();
    }
    
    var pc = new RTCPeerConnection({
      iceServers: [
        { urls: "stun:stun.l.google.com:19302" },
        { urls: "stun:stun1.l.google.com:19302" }
      ]
    });
    state.pc = pc;

    var dc = pc.createDataChannel("chat");
    state.dc = dc;
    
    dc.onmessage = function(ev) {
      var msg = document.createElement("div");
      msg.className = "chat-message";
      msg.textContent = ev.data;
      els.chatMessages.appendChild(msg);
      els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
    };

    els.chatForm.onsubmit = function(e) {
      e.preventDefault();
      var txt = els.chatInput.value.trim();
      if (txt && state.dc && state.dc.readyState === "open") {
        state.dc.send(txt);
        var msg = document.createElement("div");
        msg.className = "chat-message self";
        msg.textContent = txt;
        els.chatMessages.appendChild(msg);
        els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
        els.chatInput.value = "";
      }
    };

    pc.addEventListener("track", function(evt) {
      if (els.screen.srcObject !== evt.streams[0]) {
        els.screen.srcObject = evt.streams[0];
        onStreamLoad();
      }
    });

    pc.addTransceiver("video", { direction: "recvonly" });
    pc.addTransceiver("audio", { direction: "recvonly" });

    pc.createOffer()
      .then(function(offer) {
        return pc.setLocalDescription(offer).then(function() { return offer; });
      })
      .then(function(offer) {
        var url = "/webrtc/offer";
        return fetch(url, {
          method: "POST",
          body: JSON.stringify({ 
            sdp: offer.sdp, 
            type: offer.type,
            monitor_index: parseInt(els.monitorSelect.value, 10),
            quality: els.qualitySelect.value
          }),
          headers: {
            "Content-Type": "application/json",
            "X-Pardus-PIN": state.pin || "",
            "X-Pardus-Device-Id": state.deviceId || ""
          }
        });
      })
      .then(function(res) {
        if (!res.ok) throw new Error("Bağlantı reddedildi (PIN?)");
        return res.json();
      })
      .then(function(answer) {
        return pc.setRemoteDescription(answer);
      })
      .catch(function(err) {
        console.error(err);
        onStreamError();
      });
      
    els.control.disabled = false;
  }

  function onStreamLoad() {
    if (state.watching) {
      return;
    }
    state.watching = true;
    els.frame.classList.add("live");
    els.brand.classList.add("live");
    setStatus("canlı", "live");
    els.upload.disabled = false;
    els.fm.disabled = false;
    els.chatPanel.style.display = "flex";
    fetchInfo();
  }

  function onStreamError() {
    // Yanlış PIN / kapalı akış / kopma. Multipart akışta `error` bağlantı
    // düşünce de tetiklenir; kontrol aktifse onu da düşür.
    state.watching = false;
    els.frame.classList.remove("live");
    els.brand.classList.remove("live");
    els.control.disabled = true;
    els.upload.disabled = true;
    els.fm.disabled = true;
    els.chatPanel.style.display = "none";
    setStatus("bağlantı yok (PIN?/akış kapalı)", "err");
    if (state.controlling) {
      teardownControl();
    }
  }

  function onFileSelected(ev) {
    var files = ev.target.files;
    if (!files || files.length === 0) return;
    
    // Multiple files support
    for (var i = 0; i < files.length; i++) {
        uploadFile(files[i]);
    }
    els.fileInput.value = ""; // Reset
  }

  function uploadFile(file) {
    var url = "/api/v1/files/upload?name=" + encodeURIComponent(file.name);
    setStatus("Yükleniyor: " + file.name + "...", "wait");
    
    fetch(url, {
      method: "POST",
      body: file,
      headers: {
        "Content-Type": "application/octet-stream"
      }
    })
    .then(function(res) {
      if (!res.ok) throw new Error("Yükleme reddedildi: " + res.status);
      return res.text();
    })
    .then(function(text) {
      setStatus("Dosya gönderildi: " + file.name, "live");
    })
    .catch(function(err) {
      setStatus("Yükleme hatası: " + err.message, "err");
    });
  }

  // ---------------------------------------------------------------------------
  // Host meta bilgisi
  // ---------------------------------------------------------------------------

  function fetchInfo() {
    fetch("/info", { cache: "no-store" })
      .then(function (r) {
        return r.ok ? r.json() : null;
      })
      .then(function (info) {
        if (!info) {
          return;
        }
        if (info.name) {
          els.host.textContent = info.name + " · " + window.location.host;
        }
        els.fingerprint.textContent = info.cert_fingerprint || "TLS yok";
        var backend = info.control_backend;
        var allowed = info.control_allowed;
        if (backend) {
          els.backend.textContent =
            backend + (allowed ? "" : " (host kapalı)");
        } else {
          els.backend.textContent = allowed === false ? "host kapalı" : "yok";
        }
        // Kontrol backend yoksa "Kontrolü İste" anlamsız → görsel ipucu.
        if (!backend && state.watching) {
          els.control.title = "Host'ta enjeksiyon backend'i yok.";
        }
      })
      .catch(function () {
        /* meta zorunlu değil; sessiz geç */
      });
  }

  // ---------------------------------------------------------------------------
  // Kontrol kanalı (WebSocket)
  // ---------------------------------------------------------------------------

  function onRequestControl() {
    if (state.controlling || state.ws) {
      return;
    }
    if (!state.pin) {
      setStatus("önce izle (PIN gerekli)", "err");
      return;
    }
    var scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
    var url = scheme + "//" + window.location.host + "/control";

    setStatus("kontrol isteniyor…", "wait");
    var ws;
    try {
      ws = new WebSocket(url);
    } catch (e) {
      setStatus("kontrol açılamadı", "err");
      return;
    }
    state.ws = ws;
    ws.binaryType = "arraybuffer";
    ws.addEventListener("message", onWsMessage);
    ws.addEventListener("close", onWsClose);
    ws.addEventListener("error", onWsError);
  }

  function onWsMessage(ev) {
    var msg;
    try {
      msg = JSON.parse(typeof ev.data === "string" ? ev.data : "");
    } catch (e) {
      return;
    }
    if (!msg || typeof msg.t !== "string") {
      return;
    }
    if (msg.t === "grant") {
      if (msg.allow && typeof msg.session === "string" && msg.session) {
        state.token = msg.session;
        activateControl();
      } else {
        setStatus("kontrol reddedildi (host)", "err");
        closeWs();
      }
    } else if (msg.t === "revoke") {
      setStatus("kontrol geri alındı (host)", "err");
      teardownControl();
    } else if (msg.t === "ping") {
      sendRaw({ t: "pong" });
    } else if (msg.t === "clipboard") {
      if (typeof msg.text === "string" && navigator.clipboard) {
        navigator.clipboard.writeText(msg.text).catch(function(err) {
          console.warn("Pano yazılamadı (izin yok/odak yok):", err);
        });
      }
    }
  }

  function onWsClose() {
    if (state.controlling) {
      setStatus("kontrol kapandı", "idle");
    }
    teardownControl();
  }

  function onWsError() {
    setStatus("kontrol bağlantı hatası", "err");
  }

  function activateControl() {
    state.controlling = true;
    els.frame.classList.add("controlling");
    els.brand.classList.remove("live");
    els.brand.classList.add("ctrl");
    els.control.disabled = true;
    els.kill.hidden = false;
    setStatus("KONTROL ETKİN", "ctrl");
    attachInputCapture();
    els.frame.focus();
  }

  function onReleaseControl() {
    setStatus("kontrol durduruldu", "idle");
    teardownControl();
  }

  function teardownControl() {
    detachInputCapture();
    state.controlling = false;
    state.token = null;
    els.frame.classList.remove("controlling");
    els.brand.classList.remove("ctrl");
    if (state.watching) {
      els.brand.classList.add("live");
    }
    els.kill.hidden = true;
    els.control.disabled = !state.watching;
    if (state.pendingMove && state.moveTimer) {
      clearTimeout(state.moveTimer);
    }
    state.pendingMove = null;
    state.moveTimer = null;
    closeWs();
  }

  function closeWs() {
    var ws = state.ws;
    state.ws = null;
    if (!ws) {
      return;
    }
    ws.removeEventListener("message", onWsMessage);
    ws.removeEventListener("close", onWsClose);
    ws.removeEventListener("error", onWsError);
    try {
      ws.close();
    } catch (e) {
      /* zaten kapalı */
    }
  }

  // ---------------------------------------------------------------------------
  // Girdi yakalama → normalize koordinat → tel mesajı
  // ---------------------------------------------------------------------------

  var handlers = {
    pointermove: onPointerMove,
    pointerdown: onPointerDown,
    pointerup: onPointerUp,
    wheel: onWheel,
    contextmenu: onContextMenu,
    keydown: onKeyDown,
    keyup: onKeyUp,
    paste: onPaste,
  };

  function attachInputCapture() {
    els.frame.addEventListener("pointermove", handlers.pointermove);
    els.frame.addEventListener("pointerdown", handlers.pointerdown);
    els.frame.addEventListener("pointerup", handlers.pointerup);
    els.frame.addEventListener("wheel", handlers.wheel, { passive: false });
    els.frame.addEventListener("contextmenu", handlers.contextmenu);
    // Tuşlar pencere düzeyinde: frame odaktayken tüm klavye yakalanır.
    window.addEventListener("keydown", handlers.keydown, true);
    window.addEventListener("keyup", handlers.keyup, true);
    window.addEventListener("paste", handlers.paste, true);
  }

  function detachInputCapture() {
    els.frame.removeEventListener("pointermove", handlers.pointermove);
    els.frame.removeEventListener("pointerdown", handlers.pointerdown);
    els.frame.removeEventListener("pointerup", handlers.pointerup);
    els.frame.removeEventListener("wheel", handlers.wheel);
    els.frame.removeEventListener("contextmenu", handlers.contextmenu);
    window.removeEventListener("keydown", handlers.keydown, true);
    window.removeEventListener("keyup", handlers.keyup, true);
    window.removeEventListener("paste", handlers.paste, true);
  }

  /**
   * İşaretçi konumunu görüntülenen (letterbox'lı) resim dikdörtgenine göre
   * 0..1'e normalize et. object-fit:contain → resim öğe kutusu içinde en-boy
   * korunarak ortalanır; kenar boşlukları (letterbox) hariç tutulur. Resim
   * alanı dışındaysa null (kenar boşluğuna tıklama enjekte edilmez).
   */
  function normalizePoint(clientX, clientY) {
    var img = els.screen;
    var natW = img.naturalWidth;
    var natH = img.naturalHeight;
    if (!natW || !natH) {
      return null;
    }
    var rect = img.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) {
      return null;
    }
    var scale = Math.min(rect.width / natW, rect.height / natH);
    var drawnW = natW * scale;
    var drawnH = natH * scale;
    var offX = rect.left + (rect.width - drawnW) / 2;
    var offY = rect.top + (rect.height - drawnH) / 2;
    var lx = clientX - offX;
    var ly = clientY - offY;
    if (lx < 0 || ly < 0 || lx > drawnW || ly > drawnH) {
      return null; // letterbox alanı
    }
    return { x: clamp01(lx / drawnW), y: clamp01(ly / drawnH) };
  }

  function onPointerMove(ev) {
    var p = normalizePoint(ev.clientX, ev.clientY);
    if (!p) {
      return;
    }
    // Kısma: pencere içinde son konumu biriktir, zamanlayıcıyla en fazla
    // MOVE_THROTTLE_MS'de bir gönder (host'u pointermove seliyle boğma).
    var t = nowMs();
    var elapsed = t - state.lastMoveAt;
    if (elapsed >= MOVE_THROTTLE_MS) {
      state.lastMoveAt = t;
      sendMove(p.x, p.y);
      return;
    }
    state.pendingMove = p;
    if (!state.moveTimer) {
      state.moveTimer = setTimeout(flushMove, MOVE_THROTTLE_MS - elapsed);
    }
  }

  function flushMove() {
    state.moveTimer = null;
    var p = state.pendingMove;
    state.pendingMove = null;
    if (p && state.controlling) {
      state.lastMoveAt = nowMs();
      sendMove(p.x, p.y);
    }
  }

  function sendMove(x, y) {
    send({ t: "move", x: x, y: y });
  }

  function onPointerDown(ev) {
    var name = BUTTON_NAMES[ev.button];
    if (!name) {
      return;
    }
    var p = normalizePoint(ev.clientX, ev.clientY);
    if (!p) {
      return;
    }
    ev.preventDefault();
    els.frame.focus();
    send({ t: "btn", b: name, down: true, x: p.x, y: p.y });
  }

  function onPointerUp(ev) {
    var name = BUTTON_NAMES[ev.button];
    if (!name) {
      return;
    }
    var p = normalizePoint(ev.clientX, ev.clientY);
    // Bırakmada resim dışına çıkmış olabilir → son geçerli değil; kutu-içi
    // değilse yine de bırakmayı bildir (konum kenara kırpılır).
    var x = p ? p.x : clamp01(lastNorm.x);
    var y = p ? p.y : clamp01(lastNorm.y);
    ev.preventDefault();
    send({ t: "btn", b: name, down: false, x: x, y: y });
  }

  var lastNorm = { x: 0.5, y: 0.5 };

  function onWheel(ev) {
    ev.preventDefault();
    var dx = clampScroll(-ev.deltaX / WHEEL_DIVISOR);
    var dy = clampScroll(-ev.deltaY / WHEEL_DIVISOR);
    if (dx === 0 && dy === 0) {
      return;
    }
    send({ t: "scroll", dx: dx, dy: dy });
  }

  function onContextMenu(ev) {
    // Sağ tık kontrol için enjekte edilir; tarayıcı menüsü açılmasın.
    ev.preventDefault();
  }

  function onKeyDown(ev) {
    sendKey(ev, true);
  }

  function onKeyUp(ev) {
    sendKey(ev, false);
  }

  function sendKey(ev, down) {
    var code = KEY_MAP[ev.code];
    if (!code) {
      return; // eşlenmeyen tuş: atla
    }
    // Tarayıcı/OS kısayollarını (Ctrl+W sekme kapatma vb.) engelle: kontrol
    // aktifken tuşlar uzak host'a aittir.
    ev.preventDefault();
    ev.stopPropagation();
    var mods = [];
    if (ev.ctrlKey) mods.push("ctrl");
    if (ev.shiftKey) mods.push("shift");
    if (ev.altKey) mods.push("alt");
    if (ev.metaKey) mods.push("meta");
    send({ t: "key", code: code, down: down, mods: mods });
  }

  function onPaste(ev) {
    if (!state.controlling || !state.token) return;
    var text = ev.clipboardData && ev.clipboardData.getData("text");
    if (text) {
      send({ t: "clipboard", text: text });
    }
  }

  // ---------------------------------------------------------------------------
  // Gönderim
  // ---------------------------------------------------------------------------

  /** Oturum token'ı (`sid`) ve sürüm (`v`) ekleyip mesajı gönder. */
  function send(body) {
    if (!state.controlling || !state.token) {
      return;
    }
    if (body.t === "btn" || body.t === "move") {
      lastNorm.x = body.x;
      lastNorm.y = body.y;
    }
    body.sid = state.token;
    sendRaw(body);
  }

  /** Ham mesaj gönder (sürüm damgalı). grant/pong gibi token'sız da kullanılır. */
  function sendRaw(body) {
    var ws = state.ws;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      return;
    }
    body.v = PROTOCOL_VERSION;
    try {
      ws.send(JSON.stringify(body));
    } catch (e) {
      /* soket kapanmış olabilir */
    }
  }

  // ---------------------------------------------------------------------------
  // Yardımcılar
  // ---------------------------------------------------------------------------

  function clamp01(v) {
    if (v < 0) return 0;
    if (v > 1) return 1;
    return v;
  }

  function clampScroll(v) {
    if (v < -SCROLL_MAX) return -SCROLL_MAX;
    if (v > SCROLL_MAX) return SCROLL_MAX;
    return v;
  }

  function nowMs() {
    return Date.now();
  }

  function setStatus(text, kind) {
    els.status.textContent = text;
    els.status.className = "meta-val status-" + (kind || "idle");
  }

  /**
   * KeyboardEvent.code → evdev KEY_* eşlemesi kur. Fiziksel kod kullanılır →
   * klavye düzeninden bağımsız. control_protocol.py KEY_CODES kümesinin
   * tarayıcıdan üretilebilen alt kümesini kapsar.
   */
  function buildKeyMap() {
    var m = {};
    var i;
    // Harfler: KeyA..KeyZ → KEY_A..KEY_Z
    for (i = 65; i <= 90; i++) {
      var ch = String.fromCharCode(i);
      m["Key" + ch] = "KEY_" + ch;
    }
    // Rakamlar (üst sıra): Digit0..Digit9 → KEY_0..KEY_9
    for (i = 0; i <= 9; i++) {
      m["Digit" + i] = "KEY_" + i;
    }
    // Fonksiyon tuşları: F1..F12
    for (i = 1; i <= 12; i++) {
      m["F" + i] = "KEY_F" + i;
    }
    // Navigasyon / düzenleme
    m.Enter = "KEY_ENTER";
    m.NumpadEnter = "KEY_ENTER";
    m.Escape = "KEY_ESC";
    m.Backspace = "KEY_BACKSPACE";
    m.Tab = "KEY_TAB";
    m.Space = "KEY_SPACE";
    m.ArrowLeft = "KEY_LEFT";
    m.ArrowRight = "KEY_RIGHT";
    m.ArrowUp = "KEY_UP";
    m.ArrowDown = "KEY_DOWN";
    m.Home = "KEY_HOME";
    m.End = "KEY_END";
    m.PageUp = "KEY_PAGEUP";
    m.PageDown = "KEY_PAGEDOWN";
    m.Insert = "KEY_INSERT";
    m.Delete = "KEY_DELETE";
    m.CapsLock = "KEY_CAPSLOCK";
    // Değiştiriciler (sol/sağ ayrı fiziksel tuşlar)
    m.ControlLeft = "KEY_LEFTCTRL";
    m.ControlRight = "KEY_RIGHTCTRL";
    m.ShiftLeft = "KEY_LEFTSHIFT";
    m.ShiftRight = "KEY_RIGHTSHIFT";
    m.AltLeft = "KEY_LEFTALT";
    m.AltRight = "KEY_RIGHTALT";
    m.MetaLeft = "KEY_LEFTMETA";
    m.MetaRight = "KEY_RIGHTMETA";
    // Noktalama / semboller (US düzen fiziksel adları)
    m.Minus = "KEY_MINUS";
    m.Equal = "KEY_EQUAL";
    m.BracketLeft = "KEY_LEFTBRACE";
    m.BracketRight = "KEY_RIGHTBRACE";
    m.Semicolon = "KEY_SEMICOLON";
    m.Quote = "KEY_APOSTROPHE";
    m.Backquote = "KEY_GRAVE";
    m.Backslash = "KEY_BACKSLASH";
    m.Comma = "KEY_COMMA";
    m.Period = "KEY_DOT";
    m.Slash = "KEY_SLASH";
    return m;
  }

  // Başlat
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
