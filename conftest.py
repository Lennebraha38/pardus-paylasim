import os
import sys

_SRC_ABS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _SRC_ABS not in sys.path:
    sys.path.insert(0, _SRC_ABS)
