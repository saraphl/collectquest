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

# Probe resolution for alpha bounding boxes: fine enough that a 36px icon lands within a pixel of
# where a full-resolution scan would put it, small enough to scan in pure Python.
_CONTENT_PROBE_PX = 48


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
    """
    Load an image as a QPixmap fitted to size, or None if missing.

    Both scaling flags are given explicitly rather than left to Qt's defaults, which are wrong for
    this art on both counts. The default transform is nearest-neighbor, and every icon here is a
    128-256px drawing shown at 12-56px, so whole pixels were being dropped: at 12px the gem icons
    lost their highlight and the magnet's sparks broke up. The default aspect mode stretches to a
    square, which is invisible today only because every image this function is asked for happens to
    be square — it would silently distort the first one that is not.

    Fits the image's frame. For icons stacked in a column, _icon_pixmap() fits the drawing inside
    the frame instead, which is what makes a column of them line up.
    """
    path = image_path(filename)
    if not os.path.isfile(path):
        return None
    try:
        from aqt.qt import QPixmap
        src = QPixmap(path)
        if src.isNull():
            # A present but unreadable file — a truncated PNG, or one caught mid-rsync. Without
            # this, scaled() hands back a null pixmap, and a null QPixmap is truthy in Python, so
            # every `if pm:` caller sails past its guard and draws an invisible icon that still
            # takes up its slot.
            return None
        return src.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    except Exception:
        return None

_content_box_cache: dict[str, "tuple[float, float, float, float] | None"] = {}

def _content_box(path: str) -> "tuple[float, float, float, float] | None":
    """
    Fractional box (left, top, right, bottom) of an image's non-transparent pixels, or None.

    Measured on a small probe copy rather than the source: the art is 128-256px square, and
    scanning one in Python costs tens of thousands of pixel reads for a figure that only needs to
    be accurate to a fraction of a screen pixel. Cached per path because it is a property of the
    file, and the shop rebuilds its rows on every purchase.
    """
    if path in _content_box_cache:
        return _content_box_cache[path]
    box = None
    try:
        from aqt.qt import QImage
        probe = QImage(path)
        if not probe.isNull():
            probe = probe.convertToFormat(QImage.Format.Format_ARGB32).scaled(
                _CONTENT_PROBE_PX,
                _CONTENT_PROBE_PX,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            n = _CONTENT_PROBE_PX
            left, top, right, bottom = n, n, -1, -1
            for y in range(n):
                for x in range(n):
                    # Above a faint threshold, so an antialiased halo or a stray near-invisible
                    # pixel does not report the whole frame as content.
                    if ((probe.pixel(x, y) >> 24) & 0xFF) > 8:
                        left = min(left, x)
                        right = max(right, x)
                        top = min(top, y)
                        bottom = max(bottom, y)
            if right >= left and bottom >= top:
                # One probe pixel of slack each way: the probe is a downscale, so an edge column
                # of the source can land just under the alpha threshold.
                box = (
                    max(0.0, (left - 1) / n),
                    max(0.0, (top - 1) / n),
                    min(1.0, (right + 2) / n),
                    min(1.0, (bottom + 2) / n),
                )
    except Exception:
        # Deliberately not cached. A raise here is a transient condition — a file being rewritten
        # underneath us — unlike a box that is legitimately None because the art is blank. Caching
        # it would pin every later call for this image to the frame-fitting fallback, quietly
        # restoring the misalignment the crop exists to remove, until Anki restarts.
        return None
    _content_box_cache[path] = box
    return box

def _cropped_to_content(src, path: str):
    """
    `src` cropped to its drawing, or `src` unchanged when the box cannot be measured.

    Shared by the two helpers below, which both need the drawing without its transparent frame and
    differ only in what they do with it afterwards.
    """
    box = _content_box(path)
    if box is None:
        return src
    from aqt.qt import QRect
    w, h = src.width(), src.height()
    return src.copy(
        QRect(
            int(box[0] * w),
            int(box[1] * h),
            max(1, int((box[2] - box[0]) * w)),
            max(1, int((box[3] - box[1]) * h)),
        )
    )

def _ink_pixmap(filename: str, height: int):
    """
    Image cropped to its drawing and scaled to `height`, with no frame left around it, or None.

    For a pixmap standing in for a text glyph, where the surrounding widget is already positioning
    it: a transparent frame would offset it from whatever it is meant to line up with, and the
    caller has no way to see how much frame there is. _icon_pixmap() keeps the frame on purpose,
    to hold a column of differently-shaped icons on a common center; this one strips it, so the
    drawing itself is the widget's contents.
    """
    if height <= 0:
        return None
    path = image_path(filename)
    if not os.path.isfile(path):
        return None
    try:
        from aqt.qt import QPixmap
        src = QPixmap(path)
        if src.isNull():
            return None
        out = _cropped_to_content(src, path).scaledToHeight(
            height, Qt.TransformationMode.SmoothTransformation
        )
        # Null rather than None would be truthy at the call site, and the caller's fallback glyph
        # would be skipped in favour of drawing nothing at all.
        return None if out.isNull() else out
    except Exception:
        return None

def _icon_pixmap(filename: str, size: int = 36, content: int | None = None):
    """
    Load an image as a size x size pixmap whose *visible* content is scaled to fit `content` px
    and centered, or None if missing. `content` defaults to eight ninths of `size`.

    For icons stacked in a column. _pixmap() fits the image's frame, which lines up the files but
    not the art in them: every icon carries its own transparent margin (4% on the gems, 12% on
    equip_icon_dragon_teeth.png), so a column of frame-fitted icons has a ragged left edge and
    drawings that look randomly sized. Fitting the alpha bounding box instead makes the drawings the same size and
    centers them on a common grid, which is what the eye actually aligns on. Aspect ratio is
    preserved, unlike _pixmap's stretch-to-square.
    """
    if content is None:
        # Eight ninths of the canvas: the ratio the shop rows were built at (32 in 36), so a caller
        # that only asks for a size gets the same breathing room at any size.
        content = max(1, round(size * 8 / 9))
    # Never larger than the canvas it is centered on: the offsets below would go negative and the
    # drawing would be silently clipped on all four sides rather than reported as a bad call.
    content = min(content, size)
    path = image_path(filename)
    if not os.path.isfile(path):
        return None
    try:
        from aqt.qt import QPainter, QPixmap
        src = QPixmap(path)
        if src.isNull():
            return None
        art = _cropped_to_content(src, path).scaled(
            content,
            content,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        canvas = QPixmap(size, size)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        try:
            painter.drawPixmap((size - art.width()) // 2, (size - art.height()) // 2, art)
        finally:
            # Ends even if the draw raises: the catch below would otherwise return None while
            # leaving the painter active on the canvas, which Qt reports as a painter destroyed
            # while still in use.
            painter.end()
        return canvas
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
