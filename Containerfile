FROM python:3.12-slim

LABEL maintainer="Lennebraha38 <farukhilmi12345@gmail.com>"
LABEL description="Pardus Güvenli Paylaşım - Container"

# System dependencies (GUI/GTK ve ekran yakalama araçları)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    python3-gi \
    gir1.2-gtk-4.0 \
    gir1.2-adw-1 \
    gir1.2-gstreamer-1.0 \
    gir1.2-gstreamer-plugins-base-1.0 \
    scrot \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Önce metadata + kaynak: pip install tek adımda ve .venv'e değil,
# sistem Python'ına kurulur (ENTRYPOINT `python -m pardus_paylasim`).
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY locale/ ./locale/
COPY data/ ./data/

RUN pip install --no-cache-dir .

# Non-root user
RUN useradd -m -s /bin/bash pardus
USER pardus

EXPOSE 52345 8900 8901 8920

# Varsayılan olarak CLI yardımını göster; GUI için X11/Wayland soketi gerekir.
ENTRYPOINT ["python", "-m", "pardus_paylasim"]
CMD ["--help"]
