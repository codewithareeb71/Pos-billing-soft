"""Generate the ALSHAN POS SYSTEM application icon (.ico + .png).

Run:  python assets/generate_icon.py
Produces:
    assets/alshan_pos.ico   (16, 24, 32, 48, 64, 128, 256 px)
    assets/alshan_pos.png   (256 px, used by the installer and the docs)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (QColor, QGuiApplication, QPainter,  # noqa: E402
                           QPen, QPixmap)

# Icons need a (minimal) Qt application object; offscreen keeps this working
# on build servers without a desktop session.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
APP = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])

PRIMARY = "#123A5C"
ACCENT = "#2E86AB"
SIZES = (16, 24, 32, 48, 64, 128, 256)


def render(size: int) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    rect = QRectF(0, 0, size, size)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(PRIMARY))
    painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), size * 0.22, size * 0.22)
    painter.setBrush(QColor(ACCENT))
    painter.drawRoundedRect(QRectF(size * 0.14, size * 0.52, size * 0.72, size * 0.30),
                            size * 0.08, size * 0.08)
    # The "A" is drawn as vector strokes so the icon looks the same on every
    # machine, including build servers without any fonts installed.
    painter.setPen(QPen(QColor("#FFFFFF"), max(1, size * 0.11),
                        Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.drawLine(QPointF(size * 0.30, size * 0.84),
                     QPointF(size * 0.50, size * 0.22))
    painter.drawLine(QPointF(size * 0.50, size * 0.22),
                     QPointF(size * 0.70, size * 0.84))
    painter.drawLine(QPointF(size * 0.385, size * 0.62),
                     QPointF(size * 0.615, size * 0.62))
    painter.end()
    return pix


def _png_bytes(size: int) -> bytes:
    """Render one size and return it as PNG data."""
    from PySide6.QtCore import QBuffer, QIODevice

    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    ok = render(size).save(buffer, "PNG")
    if not ok:
        raise RuntimeError(f"could not encode the {size}px icon as PNG")
    return bytes(buffer.data())


def write_ico(path: Path, sizes: tuple[int, ...] = SIZES) -> bool:
    """Write a real multi-resolution .ico (PNG entries, Vista and later)."""
    import struct

    blobs = {size: _png_bytes(size) for size in sizes}
    ordered = sorted(sizes)
    header = struct.pack("<HHH", 0, 1, len(ordered))          # ICONDIR
    offset = 6 + 16 * len(ordered)                            # header + entries
    entries = b""
    data = b""
    for size in ordered:
        blob = blobs[size]
        width = 0 if size >= 256 else size                    # 0 means 256
        entries += struct.pack(
            "<BBBBHHII", width, width, 0, 0, 1, 32, len(blob), offset)
        data += blob
        offset += len(blob)
    path.write_bytes(header + entries + data)
    return path.exists() and path.stat().st_size > 0


def main() -> int:
    out_dir = Path(__file__).resolve().parent
    out_dir.mkdir(parents=True, exist_ok=True)

    png_path = out_dir / "alshan_pos.png"
    render(256).save(str(png_path), "PNG")

    ico_path = out_dir / "alshan_pos.ico"
    if not write_ico(ico_path):
        print(f"FAILED writing {ico_path}")
        return 1

    for path in (ico_path, png_path):
        print(f"OK  {path}  ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
