FROM python:3.12-slim

LABEL maintainer="Pardus Paylaşım Ekibi"
LABEL description="Pardus Güvenli Paylaşım - Container"

# System dependencies
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

# Install Python dependencies
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && \
    uv sync --frozen --no-dev

# Copy source
COPY src/ ./src/
COPY data/ ./data/
COPY locale/ ./locale/

# Install package
RUN pip install --no-cache-dir -e .

# Non-root user
RUN useradd -m -s /bin/bash pardus
USER pardus

EXPOSE 52345 8900 8901

ENTRYPOINT ["python", "-m", "pardus_paylasim"]
