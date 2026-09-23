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
from .assets import _icon_pixmap, add_detail_window_close_row, add_detail_window_header, add_section_heading, exec_dialog
from .constants import _DETAIL_MUTED, _MUTED_STAT_STYLE

# Item rows the scroll box shows at once; the icon grid above always stays whole.
_VISIBLE_ITEM_ROWS = 6
# What the box may be squeezed to on a short screen: a floor rather than a fixed height, or the
# close row gets drawn over it.
_MIN_ITEM_ROWS = 2


# Icons shrink once the collection outgrows a comfortable grid. The window is never narrower than
# this many icons, so a small collection (e.g. just after prestige) doesn't leave it a sliver.
_ICON_PX_LARGE = 32
_ICON_PX_SMALL = 28
_ICON_SHRINK_AFTER = 20
_GRID_SPACING = 6
_MIN_COLS = 10


def _grid_min_width(icon_sz: int) -> int:
    """The width of _MIN_COLS icons side by side, spacing included."""
    return _MIN_COLS * icon_sz + (_MIN_COLS - 1) * _GRID_SPACING


def items_stats_parts(owned: list) -> list[str]:
    """The collection's standing bonuses as ["+2% XP", ..., "+5% gem luck"], excluding the dungeon
    stats (see dungeon_stats_parts)."""
    parts: list[str] = []
    xp_pct = shop_mod.xp_bonus_percent(owned)
    xp_flat = shop_mod.xp_flat(owned)
    gold_pct = shop_mod.gold_bonus_percent(owned)
    gold_flat = shop_mod.gold_flat(owned)
    luck_pct = shop_mod.luck_gem_chance_percent(owned)
    if xp_pct:
        parts.append(f"+{int(xp_pct)}% XP")
    if xp_flat:
        parts.append(f"+{xp_flat} XP/review")
    if gold_pct:
        parts.append(f"+{int(gold_pct)}% gold")
    if gold_flat:
        parts.append(f"+{gold_flat}g")
    if luck_pct:
        parts.append(f"+{int(luck_pct)}% gem luck")
    return parts


def dungeon_stats_parts(owned: list) -> list[str]:
    """The two dungeon bonuses, long enough to need their own line; worded as the items are, and
    last in reading order."""
    parts: list[str] = []
    discover = shop_mod.dungeon_discover_percent(owned)
    explore = shop_mod.dungeon_explore_percent(owned)
    if discover:
        parts.append(f"+{int(discover)}% chance to find a dungeon")
    if explore:
        parts.append(f"+{int(explore)}% faster dungeon exploration")
    return parts


def _stat_label(text: str, for_panel: bool) -> QLabel:
    """One gray stat line, shrinkable to the dock's sliver when the panel asks."""
    lbl = QLabel(text)
    lbl.setStyleSheet(_MUTED_STAT_STYLE)
    if for_panel:
        lbl.setMinimumWidth(1)
    return lbl


def _stats_row(layout, indent: bool) -> QHBoxLayout:
    """A row for one line of gray stats. `indent` gives the two-space indent of the rows above,
    measured from the body font rather than the label's smaller one."""
    row = QHBoxLayout()
    # Zero, so the indent below is exactly two spaces wide and lines up with the quest and
    # milestone rows; Qt's default 6px would push the row past them.
    row.setSpacing(0)
    if indent:
        owner = layout.parentWidget()
        metrics = owner.fontMetrics() if owner is not None else QFontMetrics(QApplication.font())
        row.addSpacing(metrics.horizontalAdvance("  "))
    return row


def add_items_stats_row(
    layout, owned: list, for_panel: bool = False, indent: bool = False,
) -> bool:
    """The gray lines of standing bonuses; returns whether any were added. The dungeon pair takes a
    second line. `indent` is for the panel's section heading."""
    parts = items_stats_parts(owned)
    dungeon_parts = dungeon_stats_parts(owned)
    if not parts and not dungeon_parts:
        return False
    sep = "  ·  "

    def add_line(segments: list[str]) -> None:
        row = _stats_row(layout, indent)
        row.addWidget(_stat_label(sep.join(segments), for_panel))
        row.addStretch()
        layout.addLayout(row)

    # A player whose whole collection is one dungeon item has nothing for the first line, and an
    # empty one is a gap, not a row - so the pair leads instead of sitting under a blank.
    if parts:
        add_line(parts)
    if dungeon_parts:
        add_line(dungeon_parts)
    return True


def _icons_grid(owned_list: list) -> QWidget:
    """The icon grid: every owned item as a tooltipped pixmap, reflowed to the width available."""
    icon_sz = _ICON_PX_SMALL if len(owned_list) > _ICON_SHRINK_AFTER else _ICON_PX_LARGE
    icons_widget = QWidget()
    icons_widget.setMinimumWidth(_grid_min_width(icon_sz))
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
        # The last column needs no trailing spacing, hence the + _GRID_SPACING.
        cols = max(_MIN_COLS, (w + _GRID_SPACING) // cell_w) if w > 0 else _MIN_COLS
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
    """A scroll area that asks for a set height but can still be squeezed below it (QScrollArea's
    own hint is tiny, and a fixed height can't yield)."""

    def __init__(self, preferred_height: int) -> None:
        super().__init__()
        self._preferred_height = preferred_height

    def sizeHint(self):
        hint = super().sizeHint()
        hint.setHeight(self._preferred_height)
        return hint


def _items_list(owned_list: list) -> tuple[QWidget, QVBoxLayout]:
    """One row per owned item: icon, name and effect. Returns the layout too, for sizing the scroll
    box."""
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


def add_route_breakdown(layout: QVBoxLayout, owned: list) -> None:
    """The header total split by how items are obtained: bought, crafted, or found in a dungeon.
    Adds up to the header's denominator, and explains why the shop can be complete while this isn't.
    Loot shows from 0/8."""
    owned_ids = set(owned)
    rows = QVBoxLayout()
    rows.setContentsMargins(12, 0, 0, 0)
    rows.setSpacing(1)
    for title, pool in (
        ("Purchasable items", shop_mod.collectibles_for_gold()),
        ("Gem-only items", shop_mod.gem_only_collectibles()),
        ("Dungeon loot", shop_mod.loot_collectibles()),
    ):
        add_section_heading(rows, title, owned_ids, pool)
    layout.addLayout(rows)
    layout.addSpacing(4)


def build_items_content(layout: QVBoxLayout) -> None:
    """Fill `layout` with the bag, the count, the bonuses and the whole collection."""
    data = storage.load()
    owned = data.get("owned_collectibles", [])
    # Newest first. Filtered here, so unknown ids fall into the empty-state branch.
    owned_list = [cid for cid in reversed(owned) if shop_mod.get_collectible(cid)]

    add_detail_window_header(
        layout, "collectibles/Bag.png", "Items", f"{len(owned)}/{len(shop_mod.COLLECTIBLES)}"
    )

    add_route_breakdown(layout, owned)

    # The same lines the panel shows, repeated here so the window answers "what am I getting for
    # this collection?" without sending the reader back to the panel for the figures.
    add_items_stats_row(layout, owned)
    layout.addSpacing(8)

    if not owned_list:
        empty_lbl = QLabel("No items owned yet.")
        empty_lbl.setStyleSheet(_DETAIL_MUTED)
        empty_lbl.setMinimumWidth(_grid_min_width(_ICON_PX_LARGE))
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
    exec_dialog(d)