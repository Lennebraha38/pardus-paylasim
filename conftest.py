import os
import sys
import tempfile

_SRC_ABS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _SRC_ABS not in sys.path:
    sys.path.insert(0, _SRC_ABS)


def pytest_configure(config):
    """Windows ve sandbox ortamlarında kilitli geçici dizin sorununu önler."""
    if not config.option.basetemp:
        try:
            username = os.environ.get("USERNAME", "user")
            test_dir = os.path.join(tempfile.gettempdir(), f"pytest-of-{username}")
            os.makedirs(test_dir, exist_ok=True)
        except OSError:
            safe_temp = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".pytest_tmp")
            os.makedirs(safe_temp, exist_ok=True)
            config.option.basetemp = safe_temp

