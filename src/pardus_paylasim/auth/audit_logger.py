import json
import logging
import os
import time

logger = logging.getLogger("Audit")

AUDIT_LOG_DIR = os.path.expanduser("~/.local/share/pardus-paylasim")
AUDIT_LOG_FILE = os.path.join(AUDIT_LOG_DIR, "audit.jsonl")


def log_event(event_type: str, details: dict):
    try:
        if not os.path.exists(AUDIT_LOG_DIR):
            os.makedirs(AUDIT_LOG_DIR, exist_ok=True)

        entry = {"timestamp": time.time(), "type": event_type, **details}

        with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.error("Audit log yazılamadı: %s", e)
