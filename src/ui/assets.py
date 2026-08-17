"""Image lookup and pixmap helpers shared by every CollectQuest UI module."""
from __future__ import annotations

import os
from aqt.qt import (
    QHBoxLayout,
    QLabel,
    QWidget,
    Qt,
)

_addon_dir_cache: str | None = None


def addon_dir() -> str:
    """
    The add-on root: the folder Anki loads, holding manifest.json, images/ and admin.txt.

    Cached after the first call: this runs once per image through image_path(), and the status bar
    reloads its icons after every answered card, so the walk-up below would otherwise put a handful
    of filesystem stats on the per-review path. The add-on cannot move while Anki is running.

    Found by walking up to the manifest rather than counting parent directories. The fixed
    `dirname(dirname(...))` this used to be was right while the code lived at ag/ui.py and silently
    wrong the moment it moved to src/ui/assets.py — it returned src/, so every image lookup failed
    its isfile() test and _pixmap returned None without raising anything. Walking up survives the
    next move too.
    """
    global _addon_dir_cache
    if _addon_dir_cache is not None:
        return _addon_dir_cache
    here = os.path.dirname(os.path.abspath(__file__))
    while True:
        if os.path.isfile(os.path.join(here, "manifest.json")):
            _addon_dir_cache = here
            return here
        parent = os.path.dirname(here)
        if parent == here:
            # Filesystem root reached without a manifest (unpacked oddly, or run from source):
            # fall back to this file's known depth of src/ui/ below the add-on root.
            _addon_dir_cache = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            return _addon_dir_cache
        here = parent

def _admin_enabled() -> bool:
    """True if an empty txt named 'admin' exists at add-on root (admin.txt)."""
    path = os.path.join(addon_dir(), "admin.txt")
    return os.path.isfile(path)

def image_path(filename: str) -> str:
    return os.path.join(addon_dir(), "images", filename)

def _pixmap(filename: str, size: int = 32):
    """Load image as QPixmap scaled to size, or None if missing."""
    path = image_path(filename)
    if not os.path.isfile(path):
        return None
    try:
        from aqt.qt import QPixmap
        return QPixmap(path).scaled(size, size)
    except Exception:
        return None

def _pixmap_ui(filename: str, height: int = 36):
    """Load image from images/ui/ scaled to height (width auto), for UI buttons."""
    path = image_path(os.path.join("ui", filename))
    if not os.path.isfile(path):
        return None
    try:
        from aqt.qt import QPixmap
        px = QPixmap(path)
        if px.isNull():
            return None
        return px.scaledToHeight(height, Qt.TransformationMode.SmoothTransformation)
    except Exception:
        return None

def _house_level_threshold(image_index: int) -> int:
    """Level at which this house image unlocks. Image 1 at level 1, 2 at 3, 3 at 6, 4 at 10, 5 at 15, ... (n(n+1)/2)."""
    return image_index * (image_index + 1) // 2

def house_index_for_level(level: int) -> int:
    """Largest house image index unlocked at this level (1-based)."""
    # n(n+1)/2 <= level  =>  n^2 + n - 2*level <= 0  =>  n <= (-1 + sqrt(1+8*level))/2
    if level < 1:
        return 0
    n = int(((-1 + (1 + 8 * level) ** 0.5) / 2))
    return max(0, n)

def next_house_goal_level(level: int) -> int | None:
    """Level required for the next house image, or None if at max."""
    idx = house_index_for_level(level)
    next_level = _house_level_threshold(idx + 1)
    return next_level  # same as current threshold means we're at max; caller can hide "next" then

def _house_pixmap(image_index: int, width: int = 360) -> "QPixmap | None":
    """Load house/N.png scaled by width, preserving the image's aspect ratio.

    The image is uniformly rescaled to the requested width; height is derived from
    the original aspect ratio (no squashing or stretching)."""
    path = image_path(os.path.join("house", f"{image_index}.png"))
    if not os.path.isfile(path):
        return None
    try:
        from aqt.qt import QPixmap
        pm = QPixmap(path)
        if pm.isNull():
            return None
        # Uniformly scale to the requested width while keeping the original aspect ratio.
        return pm.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
    except Exception:
        return None

def _label_with_pixmap(pixmap, text_label: QLabel) -> QWidget:
    """Row: icon + text label, vertically centered."""
    w = QWidget()
    row = QHBoxLayout(w)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(2)
    icon = QLabel()
    icon.setPixmap(pixmap)
    row.addWidget(icon)
    row.addWidget(text_label)
    row.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    return w

def _review_dialog_icon() -> QLabel | None:
    """Scroll/letter icon shared by the prestige and game-finished dialogs."""
    pm = None
    for name in ("icon_scroll_letter_1.png", "Icon_Scroll_Letter_1.png"):
        pm = _pixmap_ui(name, height=64)
        if pm is not None and not pm.isNull():
            break
    if pm is None or pm.isNull():
        return None
    lbl = QLabel()
    lbl.setPixmap(pm)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return lbl
