# Pardus 23 (Debian 12 Bookworm tabanlıdır)
FROM pardus/yirmiuc:latest 

# X11, DBus, GTK, Python ve uygulamamızın bağımlılıkları
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-pytest \
    python3-gi \
    python3-gi-cairo \
    gir1.2-gtk-4.0 \
    gir1.2-adw-1 \
    gir1.2-gstreamer-1.0 \
    python3-gst-1.0 \
    mat2 \
    libimage-exiftool-perl \
    python3-zeroconf \
    python3-bleak \
    xvfb \
    dbus-x11 \
    lintian \
    file \
    python3-cryptography \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY entrypoint.sh /app/entrypoint.sh
COPY test_turing.py /app/test_turing.py
COPY test_backend.py /app/test_backend.py
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
