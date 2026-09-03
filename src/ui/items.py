"""The items window: the whole collection at full size, opened from the panel's [▸] button."""
from __future__ import annotations

from aqt.qt import (
    QApplication,
    QDialog,
    QEvent,
    QFontMetrics,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QObject,
    QScrollArea,
    QTimer,
    QVBoxLayout,
    QWidget,
    Qt,
)

from .. import shop as shop_mod, storage
from .assets import _icon_pixmap, add_detail_window_close_row, add_detail_window_header
from .constants import _DETAIL_MUTED, _MUTED_STAT_STYLE

# How many item rows the scroll box shows at once. The icon grid above it stays whole however
# large the collection gets - it is the part that answers "what do I have?" at a glance - so only
# the rows, which grow one per item, are what the window is stopped from growing with.
_VISIBLE_ITEM_ROWS = 6
# What the box may be squeezed to when the window has no room for the full six - a short screen, or
# a window manager that caps the height. A floor rather than a fixed height: pinned to six rows the
# box cannot yield, and the layout resolves the shortfall by drawing the close row over it.
_MIN_ITEM_ROWS = 2

# Icons shrink once the collection outgrows a comfortable grid, and the grid never narrows below
# this many columns however narrow the window is dragged.
_ICON_PX_LARGE = 32
_ICON_PX_SMALL = 28
_ICON_SHRINK_AFTER = 20
_GRID_SPACING = 6
_MIN_COLS = 6


def items_stats_parts(owned: list) -> tuple[list[str], float]:
    """
    The collection's standing bonuses as (["+2% XP", ...], gem luck percent).

    Shared by the panel's gray stats line and this window's copy of it, so the two cannot drift
    into quoting different numbers for the same collection.
    """
    parts: list[str] = []
    xp_pct = shop_mod.xp_bonus_percent(owned)
    xp_flat = shop_mod.xp_flat(owned)
    gold_pct = shop_mod.gold_bonus_percent(owned)
    gold_flat = shop_mod.gold_flat(owned)
    if xp_pct:
        parts.append(f"+{int(xp_pct)}% XP")
    if xp_flat:
        parts.append(f"+{xp_flat} XP")
    if gold_pct:
        parts.append(f"+{int(gold_pct)}% gold")
    if gold_flat:
        parts.append(f"+{gold_flat}g")
    return parts, shop_mod.luck_gem_chance_percent(owned)


def add_items_stats_row(
    layout, owned: list, for_panel: bool = False, indent: bool = False
) -> bool:
    """The gray line of standing bonuses. Returns whether there was anything to add.

    `indent` lines the row up under a section heading, for the panel; the items window, whose own
    heading is flush left, leaves it off.
    """
    parts, luck_pct = items_stats_parts(owned)
    if not parts and not luck_pct:
        return False
    row = QHBoxLayout()
    if indent:
        # The same two-space indent the quest, milestone and buff rows carry. Set as a spacer
        # measured from the body font rather than written into the label, whose 10px font would
        # indent by two of its own narrower spaces and land short of the rows above.
        owner = layout.parentWidget()
        metrics = owner.fontMetrics() if owner is not None else QFontMetrics(QApplication.font())
        row.addSpacing(metrics.horizontalAdvance("  "))
    if parts:
        parts_lbl = QLabel("  ·  ".join(parts))
        parts_lbl.setStyleSheet(_MUTED_STAT_STYLE)
        if for_panel:
            parts_lbl.setMinimumWidth(1)
        row.addWidget(parts_lbl)
    if luck_pct:
        if parts:
            sep = QLabel("  ·  ")
            sep.setStyleSheet(_MUTED_STAT_STYLE)
            if for_panel:
                sep.setMinimumWidth(1)
            row.addWidget(sep)
        luck_lbl = QLabel(f"+{int(luck_pct)}% gem luck")
        luck_lbl.setStyleSheet(_MUTED_STAT_STYLE)
        luck_lbl.setToolTip("Gem luck improves your chances of finding gems")
        if for_panel:
            luck_lbl.setMinimumWidth(1)
        row.addWidget(luck_lbl)
    row.addStretch()
    layout.addLayout(row)
    return True


def _icons_grid(owned_list: list) -> QWidget:
    """The icon grid: every owned item as a tooltipped pixmap, reflowed to the width available."""
    icon_sz = _ICON_PX_SMALL if len(owned_list) > _ICON_SHRINK_AFTER else _ICON_PX_LARGE
    icons_widget = QWidget()
    icons_widget.setMinimumWidth(1)
    icons_widget.setMaximumWidth(800)
    icons_layout = QGridLayout(icons_widget)
    icons_layout.setContentsMargins(0, 0, 0, 0)
    icons_layout.setSpacing(_GRID_SPACING)
    icon_labels: list[QLabel] = []
    for cid in owned_list:
        c = shop_mod.get_collectible(cid)
        if not c:
            continue
        pm = _icon_pixmap(c["image"], icon_sz)
        if not pm:
            continue
        effect = c.get("effect_description", "")
        icon_lbl = QLabel()
        icon_lbl.setPixmap(pm)
        icon_lbl.setToolTip(f"{c.get('name', cid)}: {effect}" if effect else c.get("name", cid))
        icon_labels.append(icon_lbl)
    cell_w = icon_sz + _GRID_SPACING

    def _relayout():
        w = icons_widget.width()
        cols = max(_MIN_COLS, w // cell_w) if w > 0 else _MIN_COLS
        for lbl in icon_labels:
            icons_layout.removeWidget(lbl)
        for i, lbl in enumerate(icon_labels):
            r, c = divmod(i, cols)
            icons_layout.addWidget(lbl, r, c)
        # When only one row, align grid content left so it doesn't sit centered
        if len(icon_labels) <= cols:
            icons_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        else:
            icons_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

    icons_widget._grid_relayout = _relayout
    _relayout()

    class _IconsGridResizeFilter(QObject):
        def __init__(self, w):
            super().__init__(w)
            self._w = w

        def eventFilter(self, obj, event):
            if obj is self._w and event.type() == QEvent.Type.Resize:
                relayout = getattr(self._w, "_grid_relayout", None)
                if callable(relayout):
                    QTimer.singleShot(0, relayout)
            return False

    icons_widget.installEventFilter(_IconsGridResizeFilter(icons_widget))
    return icons_widget


class _ListScrollArea(QScrollArea):
    """A scroll area that asks for a set height but can still be squeezed below it.

    QScrollArea reports a small fixed hint whatever it holds, so a window sized from the layout
    opens showing a sliver of the list. setFixedHeight cures that but then the box cannot yield at
    all, and a window kept shorter than the layout wants - a short screen, or a window manager
    capping the height - resolves the shortfall by drawing the close row over the list.
    """

    def __init__(self, preferred_height: int) -> None:
        super().__init__()
        self._preferred_height = preferred_height

    def sizeHint(self):
        hint = super().sizeHint()
        hint.setHeight(self._preferred_height)
        return hint


def _items_list(owned_list: list) -> tuple[QWidget, QVBoxLayout]:
    """One row per owned item: its icon, its name and what it does.

    Returns the layout alongside the widget: the caller sizes its scroll box from the real rows.
    """
    list_widget = QWidget()
    list_layout = QVBoxLayout(list_widget)
    list_layout.setContentsMargins(0, 0, 0, 0)
    for cid in owned_list:
        c = shop_mod.get_collectible(cid)
        if not c:
            continue
        row = QHBoxLayout()
        pm = _icon_pixmap(c["image"])
        if pm:
            icon = QLabel()
            icon.setPixmap(pm)
            row.addWidget(icon)
        desc = c.get("name", cid)
        if c.get("effect_description"):
            desc += f"  — {c['effect_description']}"
        lbl = QLabel(desc)
        lbl.setToolTip(c.get("effect_description") or c.get("name", cid))
        row.addWidget(lbl)
        row.addStretch()
        list_layout.addLayout(row)
    return list_widget, list_layout


def build_items_content(layout: QVBoxLayout) -> None:
    """Fill `layout` with the bag, the count, the bonuses and the whole collection."""
    data = storage.load()
    owned = data.get("owned_collectibles", [])
    # Newest first, so an item just bought or crafted is the one at the top. Filtered here rather
    # than in the two builders below, so an id this build does not define takes the empty-state
    # branch with the rest instead of leaving a window with no list and nothing said about it.
    owned_list = [cid for cid in reversed(owned) if shop_mod.get_collectible(cid)]

    add_detail_window_header(
        layout, "collectibles/Bag.png", "Items", f"{len(owned)}/{len(shop_mod.COLLECTIBLES)}"
    )

    # The same line the panel shows, repeated here so the window answers "what am I getting for
    # this collection?" without sending the reader back to the panel for the figures.
    add_items_stats_row(layout, owned)
    layout.addSpacing(8)

    if not owned_list:
        empty_lbl = QLabel("No items owned yet.")
        empty_lbl.setStyleSheet(_DETAIL_MUTED)
        layout.addWidget(empty_lbl)
        return

    # The grid sits outside the scroll box, so every item is visible at once however many there are.
    layout.addWidget(_icons_grid(owned_list))
    layout.addSpacing(8)

    rows, row_layout = _items_list(owned_list)
    hint = rows.sizeHint()

    def _rows_height(n: int) -> int:
        """The height of the first `n` rows, measured from the real rows rather than a pixel count
        so it stays right at any font or icon size."""
        n = min(n, row_layout.count())
        return sum(
            row_layout.itemAt(i).sizeHint().height() for i in range(n)
        ) + row_layout.spacing() * (n - 1)

    height = _rows_height(_VISIBLE_ITEM_ROWS)
    scroll = _ListScrollArea(height)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setWidget(rows)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    extra = 0
    if height < hint.height():
        # Capped, so a vertical scrollbar will appear and eat width the rows need.
        extra = scroll.verticalScrollBar().sizeHint().width()
    scroll.setMinimumWidth(hint.width() + extra)
    scroll.setMinimumHeight(min(height, _rows_height(_MIN_ITEM_ROWS)))
    scroll.setMaximumHeight(height)
    # The only stretching widget, so it takes the slack up to its six rows and gives it back first
    # when there is not enough to go round.
    layout.addWidget(scroll, 1)


def show_items_dialog(parent: QWidget | None = None) -> None:
    """Open the collection in its own window."""
    d = QDialog(parent)
    d.setWindowTitle("Items")
    layout = QVBoxLayout(d)
    layout.setSpacing(6)
    build_items_content(layout)

    add_detail_window_close_row(layout, d)

    # adjustSize caps a top-level window at two thirds of the screen, which would leave the layout
    # short and squeeze the list box; ask for the height it wants, clamped to the screen.
    d.adjustSize()
    screen = d.screen() or QApplication.primaryScreen()
    max_h = int(screen.availableGeometry().height() * 0.9) if screen else 900
    d.resize(d.width(), min(d.sizeHint().height(), max_h))
    d.exec()
