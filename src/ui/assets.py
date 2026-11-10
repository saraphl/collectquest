"""Image lookup and pixmap helpers shared by every CollectQuest UI module."""
from __future__ import annotations

import os
from aqt.qt import (
    QEvent,
    QHBoxLayout,
    QLabel,
    QObject,
    QTimer,
    QVBoxLayout,
    QWidget,
    Qt,
)

_addon_dir_cache: str | None = None

# Probe resolution for alpha bounding boxes: fine enough that a 36px icon lands within a pixel of
# where a full-resolution scan would put it, small enough to scan in pure Python.
_CONTENT_PROBE_PX = 48


def addon_dir() -> str:
    """The add-on root (manifest.json, images/, admin.txt), found by walking up to the manifest and
    cached, since every image lookup goes through it."""
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

def load_save() -> dict:
    """storage.load() with finished buffs expired, for windows that show or charge what a buff
    changes: outside a review nothing else expires them."""
    from aqt import mw

    from .. import milestones, storage

    data = storage.load()
    milestones.active_buffs(data, getattr(mw, "col", None))
    return data

def image_path(filename: str) -> str:
    return os.path.join(addon_dir(), "images", filename)

def _pixmap(filename: str, size: int = 32):
    """Load an image as a QPixmap fitted to size, or None if missing. Both scaling flags are
    explicit: Qt's defaults drop pixels and stretch to a square. Fits the frame; _icon_pixmap() fits
    the drawing."""
    path = image_path(filename)
    if not os.path.isfile(path):
        return None
    try:
        from aqt.qt import QPixmap
        src = QPixmap(path)
        if src.isNull():
            # Unreadable file (truncated, or mid-rsync): scaled() would return a null pixmap, which
            # is truthy, so callers would draw an invisible icon.
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
    """Fractional box (left, top, right, bottom) of an image's non-transparent pixels, or None.
    Measured on a small probe copy and cached per path."""
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
        # Not cached: a raise here is transient (file being rewritten), unlike a legitimately blank
        # image.
        return None
    _content_box_cache[path] = box
    return box

def _cropped_to_content(src, path: str):
    """`src` cropped to its drawing, or `src` unchanged when the box can't be measured."""
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
    """Image cropped to its drawing and scaled to `height`, frameless, or None. For pixmaps standing
    in for text glyphs; _icon_pixmap() keeps the frame for icon columns."""
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
    """Load an image as a size x size pixmap whose visible content fits `content` px (default 8/9 of
    `size`), centered, or None. Fitting the alpha box, not the frame, lines up a column of icons
    whose art has uneven transparent margins."""
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
            # Ends even if the draw raises, or Qt reports a painter destroyed while active.
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
    """Level the final house unlocks at, or None without house art; derived from the image count."""
    count = house_image_count()
    return _house_level_threshold(count) if count else None


def _house_level_threshold(image_index: int) -> int:
    """Level at which this house image unlocks. Image 1 at level 1, 2 at 3, 3 at 6, 4 at 10, 5 at 15, ... (n(n+1)/2)."""
    return image_index * (image_index + 1) // 2

_house_image_count_cache: int | None = None


def house_image_count() -> int:
    """How many house images ship, counted from house/1.png up. Cached: read on every redraw."""
    global _house_image_count_cache
    if _house_image_count_cache is None:
        n = 0
        while os.path.isfile(image_path(os.path.join("house", f"{n + 1}.png"))):
            n += 1
        _house_image_count_cache = n
    return _house_image_count_cache


def house_index_for_level(level: int) -> int:
    """Largest house image index unlocked at this level (1-based), clamped to the last image, or the
    house block would vanish past the final one."""
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
    """Load house/N.png scaled to `width`, preserving aspect ratio."""
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

def add_detail_window_header(layout, icon: str, title: str, count: str, beneath=None) -> None:
    """The heading a detail window opens with: icon, then title and count. With `beneath`, the icon
    sits left of the title and that layout, sized to their height, as the shop's sign does."""
    from .constants import _DETAIL_HEADER_ICON_PX, _DETAIL_MUTED, _DETAIL_TITLE_STYLE, _HEADER_ICON_GAP

    row = QHBoxLayout()
    row.setSpacing(8)
    title_lbl = QLabel(title)
    title_lbl.setStyleSheet(_DETAIL_TITLE_STYLE)
    row.addWidget(title_lbl)
    count_lbl = QLabel(count)
    count_lbl.setStyleSheet(_DETAIL_MUTED)
    row.addWidget(count_lbl)
    row.addStretch()

    if beneath is None:
        # Centered above the title, at full canvas since nothing shares its column.
        pm = _icon_pixmap(icon, _DETAIL_HEADER_ICON_PX, content=_DETAIL_HEADER_ICON_PX)
        if pm:
            icon_lbl = QLabel()
            icon_lbl.setPixmap(pm)
            layout.addWidget(icon_lbl, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addLayout(row)
        return

    # In a widget so it can be measured before the window shows; polished so the title's font counts.
    text_w = QWidget()
    text_col = QVBoxLayout(text_w)
    text_col.setContentsMargins(0, 0, 0, 0)
    text_col.setSpacing(0)
    text_col.addLayout(row)
    text_col.addLayout(beneath)
    text_w.ensurePolished()
    header = QHBoxLayout()
    header.setSpacing(_HEADER_ICON_GAP)
    side = text_w.sizeHint().height()
    pm = _icon_pixmap(icon, side, content=side)
    if pm:
        icon_lbl = QLabel()
        icon_lbl.setPixmap(pm)
        header.addWidget(icon_lbl, 0, Qt.AlignmentFlag.AlignTop)
    header.addWidget(text_w, 1)
    layout.addLayout(header)


def night_mode() -> bool:
    """Whether Anki is in its dark theme. False if the theme manager cannot be reached."""
    try:
        from aqt.theme import theme_manager

        return bool(theme_manager.night_mode)
    except Exception:
        return False


def attention_color() -> str:
    """The color that marks a control needing the player, in the shade the current theme wants."""
    from .constants import _ATTENTION_COLOR_DARK, _ATTENTION_COLOR_LIGHT

    return _ATTENTION_COLOR_DARK if night_mode() else _ATTENTION_COLOR_LIGHT


class _WrappedLabel(QLabel):
    """Word-wrapped label that claims its wrapped height itself; a rebuilt grid can size it one line short."""

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if event.size().width() != event.oldSize().width():
            # Cleared first: QLabel's heightForWidth never reports less than the minimum height.
            self.setMinimumHeight(0)
            self.setMinimumHeight(self.heightForWidth(self.width()))


class EffectLabel(_WrappedLabel):
    """An item's effect line that wraps between stats, and inside one only when it alone is too wide."""

    def __init__(self, effect: str) -> None:
        super().__init__(effect)
        self._parts = effect.split(", ")
        self._heights: dict = {}
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(True)

    def _packed(self, width: int) -> str:
        """Each stat starts a new line unless it fits whole on the current one; a stat too wide for
        any line wraps by words instead."""
        fm = self.fontMetrics()
        lines = [""]

        def joined(chunk: str) -> str:
            return f"{lines[-1]} {chunk}" if lines[-1] else chunk

        last = len(self._parts) - 1
        for i, part in enumerate(self._parts):
            text = part if i == last else part + ","
            if fm.horizontalAdvance(joined(text)) <= width:
                lines[-1] = joined(text)
            elif lines[-1] and fm.horizontalAdvance(text) <= width:
                lines.append(text)
            else:
                for word in text.split(" "):
                    if lines[-1] and fm.horizontalAdvance(joined(word)) > width:
                        lines.append(word)
                    else:
                        lines[-1] = joined(word)
        return "\n".join(lines)

    def _text_width(self, width: int) -> int:
        m = self.contentsMargins()
        return width - m.left() - m.right() - 2 * max(0, self.margin())

    def heightForWidth(self, width: int) -> int:
        # Measured on the text as packed for that width, which is what the label shows at it.
        self.ensurePolished()
        key = (width, self.font().key())
        if key not in self._heights:
            if len(self._heights) > 64:
                self._heights.clear()
            probe = QLabel(self._packed(self._text_width(width)))
            probe.setFont(self.font())
            probe.setTextFormat(Qt.TextFormat.PlainText)
            probe.setWordWrap(True)
            probe.setContentsMargins(self.contentsMargins())
            probe.setMargin(self.margin())
            self._heights[key] = probe.heightForWidth(width)
        return self._heights[key]

    def resizeEvent(self, event) -> None:
        text = self._packed(self._text_width(event.size().width()))
        if text != self.text():
            self.setText(text)
        super().resizeEvent(event)


def quality_color(quality: int) -> str | None:
    """A quality's title color in the current theme's shade; None for Normal (the theme's own)."""
    from .constants import _QUALITY_COLORS

    shades = _QUALITY_COLORS.get(quality)
    if not shades:
        return None
    return shades[1] if night_mode() else shades[0]


def quality_name_label(c: dict, quality: int = 0) -> QLabel:
    """The item's name with its quality in front, colored by tier."""
    from .. import shop as shop_mod

    lbl = QLabel(shop_mod.display_name(c, quality))
    color = quality_color(quality)
    if color:
        lbl.setStyleSheet(f"color: {color};")
    return lbl


def drawn_button(name: str, spacing: int) -> "tuple[QPushButton, QHBoxLayout]":
    """A button with a row of widgets drawn on it; fill the row, then pass both to finish_drawn_button."""
    from aqt.qt import QPushButton

    btn = QPushButton()
    btn.setAccessibleName(name)
    row = QHBoxLayout(btn)
    row.setContentsMargins(6, 0, 6, 0)
    row.setSpacing(spacing)
    row.addStretch()
    return btn, row


def finish_drawn_button(btn, row: QHBoxLayout):
    """Close the row, size the button to it (it doesn't size itself to a drawn row), and let clicks
    reach it."""
    row.addStretch()
    btn.setMinimumWidth(row.sizeHint().width())
    for child in btn.findChildren(QWidget):
        child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    return btn


def item_row_widgets(c: dict, quality: int = 0) -> "tuple[QLabel | None, QWidget]":
    """Icon and name/effect cell for one collectible, as the shop's rows draw it; shared by every
    place showing an item just gained."""
    from .. import shop as shop_mod
    from .constants import _MUTED_STAT_STYLE

    effect = shop_mod.effect_text(c, quality)
    pm = _icon_pixmap(c["image"])
    icon = None
    if pm:
        icon = QLabel()
        icon.setPixmap(pm)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
    name_cell = QWidget()
    name_col = QVBoxLayout(name_cell)
    name_col.setContentsMargins(0, 0, 0, 0)
    name_col.setSpacing(2)
    name_col.addWidget(quality_name_label(c, quality))
    if effect:
        eff_lbl = EffectLabel(effect)
        eff_lbl.setStyleSheet(_MUTED_STAT_STYLE)
        name_col.addWidget(eff_lbl)
    return (icon, name_cell)


def add_item_row(layout, c: dict, quality: int = 0) -> None:
    """Lay one item's icon and name/effect cell into `layout` as a row."""
    from aqt.qt import QHBoxLayout

    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    icon, name_cell = item_row_widgets(c, quality)
    if icon is not None:
        row.addWidget(icon)
    row.addWidget(name_cell, 1)
    layout.addLayout(row)


def add_section_heading(
    layout, title: str, owned_ids, pool: list[dict], for_panel: bool = False
) -> None:
    """A section heading with an owned/total count. The total is every item of that kind, not just
    those unlocked, so it shows real progress. One rich-text label, so the two parts share a
    baseline."""
    from .constants import _MUTED_STAT_STYLE

    owned_n = len([c for c in pool if c["id"] in owned_ids])
    lbl = QLabel(
        f'{title}&nbsp;&nbsp;<span style="{_MUTED_STAT_STYLE}">{owned_n}/{len(pool)}</span>'
    )
    lbl.setTextFormat(Qt.TextFormat.RichText)
    if for_panel:
        lbl.setMinimumWidth(1)
    layout.addWidget(lbl)


def pad_detail_window(layout) -> None:
    """Pad a detail window's top-level layout on top of the dialog's own margins, as the
    CollectQuest window pads inside its own."""
    from .constants import _DIALOG_CONTENT_MARGINS

    m = layout.contentsMargins()
    pad_l, pad_t, pad_r, pad_b = _DIALOG_CONTENT_MARGINS
    layout.setContentsMargins(m.left() + pad_l, m.top() + pad_t, m.right() + pad_r, m.bottom() + pad_b)


def add_detail_window_close_row(layout, dialog) -> None:
    """The close row a detail window ends with, right-aligned below a gap."""
    from aqt.qt import QPushButton
    from .constants import _DETAIL_BUTTON_ROW_GAP, _DIALOG_BUTTON_MIN_WIDTH

    layout.addSpacing(_DETAIL_BUTTON_ROW_GAP)
    row = QHBoxLayout()
    row.addStretch()
    btn = QPushButton("Close")
    btn.clicked.connect(dialog.accept)
    # The CollectQuest window's floor, as a minimum so it still fits its label in the dialog's font.
    btn.setMinimumWidth(_DIALOG_BUTTON_MIN_WIDTH)
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


def section_header(icon: str, title: str, for_panel: bool = False) -> QHBoxLayout:
    """A section's heading row: icon and name, falling back to the bare title if the image is
    missing."""
    from .constants import _SECTION_ICON_PX

    row = QHBoxLayout()
    row.setSpacing(4)
    # _icon_pixmap, not _pixmap, so each icon's transparent margin doesn't shift its title.
    pm = _icon_pixmap(icon, _SECTION_ICON_PX)
    title_lbl = QLabel(title)
    if pm:
        header_w = _label_with_pixmap(pm, title_lbl)
        row.addWidget(header_w)
        if for_panel:
            header_w.setMinimumWidth(1)
    else:
        row.addWidget(title_lbl)
        if for_panel:
            title_lbl.setMinimumWidth(1)
    return row

def exec_dialog(dialog) -> int:
    """Run a modal dialog and destroy it once closed, returning exec()'s result. Otherwise it lives
    under Anki's main window until the profile closes."""
    result = dialog.exec()
    dialog.deleteLater()
    return result


def content_height(win, width: int) -> int:
    """`win`'s preferred height at `width`. sizeHint guesses its own width for wrapped text instead."""
    layout = win.layout()
    if layout is not None and layout.hasHeightForWidth():
        return layout.totalHeightForWidth(width)
    return win.sizeHint().height()


def refit_dialog(widget, width: int | None = None) -> None:
    """Fit `widget`'s window to its content: shrink to its height (Qt never shrinks on its own) and widen
    if needed. With `width`, fit exactly at it, growing too. After a rebuild, call from a zero-timer."""
    try:
        win = widget.window()
        if win is None:
            return
        # An explicit minimum width overrides the layout's, so a wider rebuild (e.g. a longer button
        # label) would otherwise be clipped.
        needed = win.minimumSizeHint().width()
        if needed > win.minimumWidth():
            win.setMinimumWidth(needed)
        if needed > win.maximumWidth():
            win.setMaximumWidth(needed)
        w = max(win.width() if width is None else width, needed)
        wanted = content_height(win, w)
        # Qt still clamps a too-short window up to its minimum.
        win.resize(w, wanted if width is not None else min(win.height(), wanted))
    except RuntimeError:
        pass  # window closed before the timer fired


class RefitOnActivate(QObject):
    """Runs `fit` (default: refit_dialog) on the window's next activation, once. KWin can hand a
    stale size over with the focus: on first show, or after a confirm box closes."""

    def __init__(self, win, fit=None):
        super().__init__(win)
        self._fit = fit or (lambda: refit_dialog(win))

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.WindowActivate:
            obj.removeEventFilter(self)
            self.deleteLater()
            QTimer.singleShot(0, self._fit)
        return False


def clear_layout(layout) -> None:
    """Empty a layout so it can be refilled, recursing into nested ones."""
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
    """Size a row of buttons to the widest one's hint so they read as one block. `minimum` stops
    rows of short labels becoming slivers."""
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
