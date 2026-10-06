"""ALSHAN POS SYSTEM launcher (development and packaged builds).

Run:  python run.py      (or double-click run.bat)
"""
from __future__ import annotations

import sys

from app.main import main

if __name__ == "__main__":
    sys.exit(main())
