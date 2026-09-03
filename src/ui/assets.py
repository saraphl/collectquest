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

    Cached after the first call: every image lookup goes through it, and the status bar reloads its
    icons after every answered card. The add-on cannot move while Anki is running.

    Found by walking up to the manifest rather than counting parent directories: the fixed
    dirname(dirname(...)) it used to be broke silently when this file moved into src/ui/, returning
    src/ so every image lookup failed its isfile() test and _pixmap returned None.
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

    Both scaling flags are explicit because Qt's defaults are wrong here: nearest-neighbor dropped
    whole pixels from 128-256px art shown at 12-56px, and the default aspect mode stretches to a
    square, which happens to be invisible only while every image asked for is square.

    Fits the image's frame; _icon_pixmap() fits the drawing inside it, which is what lines up a
    column of icons.
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

    Measured on a small probe copy: scanning the 128-256px source in Python costs tens of thousands
    of pixel reads for a figure that need only be accurate to a fraction of a screen pixel. Cached
    per path, since the shop rebuilds its rows on every purchase.
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

    For a pixmap standing in for a text glyph, where the widget already positions it: a transparent
    frame would offset it from whatever it lines up with. _icon_pixmap() keeps the frame instead,
    to hold a column of icons on a common center.
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
        # A null pixmap is truthy at the call site, so the caller's fallback glyph would be skipped.
        return None if out.isNull() else out
    except Exception:
        return None

def _icon_pixmap(filename: str, size: int = 36, content: int | None = None):
    """
    Load an image as a size x size pixmap whose *visible* content is scaled to fit `content` px
    and centered, or None if missing. `content` defaults to eight ninths of `size`.

    For icons stacked in a column. _pixmap() fits the image's frame, which lines up the files but
    not the art in them - every icon carries its own transparent margin (4% on the gems, 12% on the
    dragon teeth), leaving a ragged edge and drawings that look randomly sized. Fitting the alpha
    bounding box centers them on a common grid, with the aspect ratio preserved.
    """
    if content is None:
        # Eight ninths of the canvas: the ratio the shop rows were built at (32 in 36), so a caller
        # that only asks for a size gets the same breathing room at any size.
        content = max(1, round(size * 8 / 9))
    # Never larger than the canvas: the offsets below would go negative and clip the drawing.
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

def last_house_level() -> int | None:
    """Level the final shipped house unlocks at, or None when no house art is installed.

    Derived from the image count so adding a house moves it without a second constant to update.
    """
    count = house_image_count()
    return _house_level_threshold(count) if count else None


def _house_level_threshold(image_index: int) -> int:
    """Level at which this house image unlocks. Image 1 at level 1, 2 at 3, 3 at 6, 4 at 10, 5 at 15, ... (n(n+1)/2)."""
    return image_index * (image_index + 1) // 2

_house_image_count_cache: int | None = None


def house_image_count() -> int:
    """How many house images ship with the add-on, counted from house/1.png upward.

    Cached: the files cannot appear or vanish while Anki runs, and this is read on every redraw of
    the CollectQuest window.
    """
    global _house_image_count_cache
    if _house_image_count_cache is None:
        n = 0
        while os.path.isfile(image_path(os.path.join("house", f"{n + 1}.png"))):
            n += 1
        _house_image_count_cache = n
    return _house_image_count_cache


def house_index_for_level(level: int) -> int:
    """Largest house image index unlocked at this level (1-based), clamped to the last image.

    The thresholds are unbounded but the art is not. Without the clamp the index kept climbing past
    the final house, _house_pixmap found no file, and the whole house block disappeared from the
    window - taking the fully-expanded line with it - about 18 levels after the house stopped
    changing.
    """
    # n(n+1)/2 <= level  =>  n^2 + n - 2*level <= 0  =>  n <= (-1 + sqrt(1+8*level))/2
    if level < 1:
        return 0
    n = int(((-1 + (1 + 8 * level) ** 0.5) / 2))
    return max(0, min(n, house_image_count()))

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

def add_detail_window_header(layout, icon: str, title: str, count: str) -> None:
    """The heading a detail window opens with: its icon centered, then the title and count.

    Shared by the milestones and items windows, which are opened the same way and shaped alike.
    """
    from .constants import _DETAIL_HEADER_ICON_PX, _DETAIL_MUTED, _DETAIL_TITLE_STYLE

    # A pixmap in the layout, as the shop puts its sign above its heading - not setWindowIcon, which
    # no dialog here sets. content = the full canvas: nothing shares a column with it, so there is
    # no inset to reserve.
    pm = _icon_pixmap(icon, _DETAIL_HEADER_ICON_PX, content=_DETAIL_HEADER_ICON_PX)
    if pm:
        icon_lbl = QLabel()
        icon_lbl.setPixmap(pm)
        layout.addWidget(icon_lbl, 0, Qt.AlignmentFlag.AlignCenter)

    row = QHBoxLayout()
    row.setSpacing(8)
    title_lbl = QLabel(title)
    title_lbl.setStyleSheet(_DETAIL_TITLE_STYLE)
    row.addWidget(title_lbl)
    count_lbl = QLabel(count)
    count_lbl.setStyleSheet(_DETAIL_MUTED)
    row.addWidget(count_lbl)
    row.addStretch()
    layout.addLayout(row)


def add_detail_window_close_row(layout, dialog) -> None:
    """The close row a detail window ends with, right-aligned below a gap."""
    from aqt.qt import QPushButton
    from .constants import _DETAIL_BUTTON_ROW_GAP

    layout.addSpacing(_DETAIL_BUTTON_ROW_GAP)
    row = QHBoxLayout()
    row.addStretch()
    btn = QPushButton("Close")
    btn.clicked.connect(dialog.accept)
    # Twice the width its text asks for. Measured from the button's own hint rather than set to a
    # pixel count, so it stays proportionate at any font size.
    btn.setMinimumWidth(btn.sizeHint().width() * 2)
    row.addWidget(btn)
    layout.addLayout(row)


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

def refit_dialog_height(widget) -> None:
    """Shrink `widget`'s window back to the height its rebuilt content needs.

    Qt grows a window for taller content but never shrinks it again, so a shorter rebuild leaves a
    band of empty space. Height only; call it from a zero-timer so sizeHint() is the new content's.
    """
    try:
        win = widget.window()
        if win is None:
            return
        wanted = win.sizeHint().height()
        if win.height() > wanted:
            win.resize(win.width(), wanted)
    except RuntimeError:
        pass  # window closed before the timer fired


def clear_layout(layout) -> None:
    """Empty a layout so it can be refilled, recursing into nested ones.

    Shared by the shop and the prestige window: both redraw their contents in place rather than
    closing and reopening, and both need every child gone before the redraw.
    """
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            clear_layout(item.layout())


def gem_counts_row_widget(gems: dict) -> QWidget:
    """One icon + "xN" per gem color, left-aligned. Shared so the shop and the prestige window
    show the same row instead of two hand-tuned copies."""
    from .. import shop as shop_mod

    w = QWidget()
    row = QHBoxLayout(w)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(3)  # 1px less than default
    for color, img_name in shop_mod.GEM_COLORS:
        cnt = gems.get(color, 0) or 0  # a stored null would otherwise render as "xNone"
        pm = _pixmap(img_name, 24)
        if pm:
            row.addWidget(_label_with_pixmap(pm, QLabel(f"\u00d7{cnt}")))
        else:
            row.addWidget(QLabel(f"{color}:{cnt}"))
    row.addStretch()
    return w


def equalize_button_widths(*buttons, minimum: int = 0) -> None:
    """Size a row of buttons to the widest one's hint, so they read as one block.

    Taking the widest rather than a fixed number is what keeps the longest label from being clipped
    when a button's text changes with game state. `minimum` is the floor for rows whose labels are
    all short words - "Options" and "Close" hint at barely 80px, which reads as a pair of slivers in
    a window twice the shop's width.
    """
    present = [b for b in buttons if b is not None]
    if not present:
        return
    width = max([b.sizeHint().width() for b in present] + [minimum])
    for b in present:
        b.setFixedWidth(width)


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
