"""The items window: the whole collection at full size, opened from the panel's [▸] button."""
from __future__ import annotations

from typing import Callable

from aqt.qt import (
    QApplication,
    QComboBox,
    QDialog,
    QFontMetrics,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStyledItemDelegate,
    QTimer,
    QVBoxLayout,
    QWidget,
    Qt,
)

from .. import prestige as prestige_mod, shop as shop_mod, stats as stats_mod, storage
from .assets import (
    _label_with_pixmap,
    _pixmap,
    add_detail_window_close_row,
    add_detail_window_header,
    add_section_heading,
    content_height,
    drawn_button,
    equalize_button_widths,
    exec_dialog,
    finish_drawn_button,
    item_row_widgets,
    pad_detail_window,
    quality_color,
)
from .constants import _DETAIL_MUTED, _MUTED_STAT_STYLE

# Item rows the scroll box shows at once.
_VISIBLE_ITEM_ROWS = 7
# What the box may be squeezed to on a short screen: a floor rather than a fixed height, or the
# close row gets drawn over it.
_MIN_ITEM_ROWS = 2


# Fixed, so a bigger collection only makes the window taller.
_WINDOW_WIDTH = 374

# The list's sort orders and filters as (key, label), in the drop-downs' order; the first of each
# is the default. The picked sort is kept in the save under _SORT_KEY; the filter starts over.
_SORT_KEY = "items_sort"
_SORTS = (
    ("newest", "Newest first"),
    ("level_up", "Lowest level first"),
    ("level_down", "Highest level first"),
    ("name", "Name (A\u2013Z)"),
)
_FILTERS = (
    ("all", "All items"),
    ("refinable", "Refinable"),
    ("ready", "Have shards"),
)
# Anki's style sheet pads the drop-down arrow by 4px a side, on top of the box's own 4px. Cut down
# here, the longest option still fits and the drop-downs come out 11px narrower.
_COMBO_TRIM = (
    "QComboBox { padding-right: 0px; }"
    " QComboBox::drop-down { padding-left: 0px; border-left-width: 0px; padding-right: 2px; }"
)
# The refine_status values a filter lets through: a Refine button, and one that isn't grayed.
_FILTER_STATUSES = {
    "refinable": (shop_mod.REFINE_READY, shop_mod.REFINE_POOR),
    "ready": (shop_mod.REFINE_READY,),
}


_NO_BREAK_SPACE = "\u00a0"
_WORD_JOINER = "\u2060"  # zero-width, so the text's own hyphen and slash stay as they are


def _unbreakable(stat: str) -> str:
    """One stat with its break points removed: spaces, around a hyphen ("7-day") and after "/"."""
    joined = stat.replace("-", f"{_WORD_JOINER}-{_WORD_JOINER}").replace("/", f"/{_WORD_JOINER}")
    return joined.replace(" ", _NO_BREAK_SPACE)


def _stat_label(text: str, for_panel: bool) -> QLabel:
    """One gray stat line that wraps, shrinkable to the dock's sliver when the panel asks."""
    lbl = QLabel(text)
    lbl.setStyleSheet(_MUTED_STAT_STYLE)
    lbl.setWordWrap(True)
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


def add_stats_rows(layout, stats: dict, for_panel: bool = False, indent: bool = False) -> None:
    """The gray lines of standing bonuses in `stats` (stats.item_stats or total_stats), worded as
    the items word them. `indent` is for the panel's section heading."""
    for keys in stats_mod.STAT_LINES:
        segments = [shop_mod.phrase(key, stats[key]) for key in keys if stats[key]]
        if not segments:
            continue  # skipped rather than left as a gap, so whichever line has stats leads
        row = _stats_row(layout, indent)
        # A narrow window breaks between stats, after the dot, and never within one.
        text = f"{_NO_BREAK_SPACE * 2}·  ".join(_unbreakable(seg) for seg in segments)
        # Stretch 1, so it wraps at the window's width, not at the label's own guess.
        row.addWidget(_stat_label(text, for_panel), 1)
        layout.addLayout(row)


class _ListScrollArea(QScrollArea):
    """A scroll area that asks for its maximum height but can still be squeezed below it
    (QScrollArea's own hint is tiny, and a fixed height can't yield)."""

    def sizeHint(self):
        hint = super().sizeHint()
        hint.setHeight(self.maximumHeight())
        return hint


# Room between the Refine buttons and the list's scrollbar.
_ROW_RIGHT_GAP = 8


def _refine_button(data: dict, cid: str, on_refine: Callable[[str], None] | None) -> QPushButton | None:
    """"Refine [shard]×1" while the item can take a step, grayed when short of Shards; None for an
    item that's Superior, outside the unlocked bands, or never refinable."""
    status = shop_mod.refine_status(data, cid)
    if on_refine is None or status not in (shop_mod.REFINE_READY, shop_mod.REFINE_POOR):
        return None
    c = shop_mod.get_collectible(cid)
    cost = shop_mod.refine_cost(c, shop_mod.item_quality(data, cid))
    pm = _pixmap("currency/shard.png", 14)
    if pm is None:
        btn = QPushButton(f"Refine ({shop_mod.shard_word(cost)})")
    else:
        # Drawn like the shop's discounted Craft button: the label, the icon, then the count.
        btn, row = drawn_button(f"Refine ({shop_mod.shard_word(cost)})", spacing=1)
        icon = QLabel()
        icon.setPixmap(pm)
        row.addWidget(QLabel("Refine"))
        row.addSpacing(4)
        row.addWidget(icon)
        row.addWidget(QLabel(f"\u00d7{cost}"))
        finish_drawn_button(btn, row)
    btn.setAutoDefault(False)
    btn.setEnabled(status == shop_mod.REFINE_READY)
    btn.clicked.connect(lambda _checked=False, i=cid: on_refine(i))
    return btn


def _lucky_tag() -> QLabel:
    """The tag a lucky refine leaves where the Refine button was, in Superior's color like the name
    beside it."""
    tag = QLabel("Lucky refine!")
    tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
    # Padded to a button's height, so the text sits level with the Refine labels below it.
    tag.setStyleSheet(f"color: {quality_color(shop_mod.QUALITY_SUPERIOR)}; padding: 4px 0;")
    return tag


def _name_key(cid: str) -> str:
    # The bare name, so a Fine item keeps its place among the others.
    return shop_mod.display_name(shop_mod.get_collectible(cid)).casefold()


def _level_key(cid: str) -> int:
    return shop_mod.item_level(shop_mod.get_collectible(cid))


def _shown_items(data: dict, owned_list: list, view: dict, lucky: str | None = None) -> list:
    """`owned_list` (newest first) as `view` filters and sorts it. The `lucky` item passes any
    filter, or the tag would vanish with the Superior item it's on."""
    statuses = _FILTER_STATUSES.get(view.get("filter"))
    shown = [
        cid for cid in owned_list
        if statuses is None or cid == lucky or shop_mod.refine_status(data, cid) in statuses
    ]
    sort = view.get("sort")
    if sort in ("level_up", "level_down", "name"):
        shown.sort(key=_name_key)  # also what orders a level's items, whichever way levels run
    if sort in ("level_up", "level_down"):
        shown.sort(key=_level_key, reverse=sort == "level_down")
    return shown


def _items_list(
    owned_list: list, data: dict | None = None, on_refine: Callable[[str], None] | None = None,
    lucky: str | None = None,
) -> tuple[QWidget, QVBoxLayout]:
    """One row per owned item: icon, name and effect, and its Refine button, or the lucky tag on
    the `lucky` item's row. Returns the layout too, for sizing the scroll box."""
    data = data or {}
    list_widget = QWidget()
    list_layout = QVBoxLayout(list_widget)
    list_layout.setContentsMargins(0, 0, 0, 0)
    if not owned_list:
        # Only a filter gets here: an empty collection never reaches the list.
        note = QLabel("No items match this filter.")
        note.setStyleSheet(_DETAIL_MUTED)
        list_layout.addWidget(note)
    buttons = []
    tag = None
    for cid in owned_list:
        c = shop_mod.get_collectible(cid)
        if not c:
            continue
        row = QHBoxLayout()
        # The shop's name/effect cell, so both windows wrap and style it alike; the level is ours.
        icon, name_cell = item_row_widgets(
            c, shop_mod.item_quality(data, cid), shop_mod.origin_note(c)
        )
        if icon is not None:
            row.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        row.addWidget(name_cell, 1)
        btn = _refine_button(data, cid, on_refine)
        if btn is not None:
            row.addWidget(btn, 0, Qt.AlignmentFlag.AlignTop)
            buttons.append(btn)
        elif cid == lucky:
            tag = _lucky_tag()
            row.addWidget(tag, 0, Qt.AlignmentFlag.AlignTop)
        list_layout.addLayout(row)
    # One column, however many digits a cost has.
    equalize_button_widths(*buttons)
    # The tag centers on that column but never sets its width: big fonts make it the wider one.
    if tag is not None and buttons:
        tag.setMinimumWidth(buttons[0].width())
    # Keeps the rows at the top when a filter leaves too few to fill the box.
    list_layout.addStretch(1)
    return list_widget, list_layout


def _box_heights(row_layout: QVBoxLayout, bar_width: int) -> tuple[int, int]:
    """The scroll box's floor and full heights: _MIN_ITEM_ROWS and _VISIBLE_ITEM_ROWS of these
    rows at the width they will get."""
    items = [row_layout.itemAt(i).layout() for i in range(row_layout.count())]
    rows = [row for row in items if row is not None]
    # Rows wrap to the fixed width, less the scrollbar and its gap when there is one.
    capped = len(rows) > _VISIBLE_ITEM_ROWS
    width = _WINDOW_WIDTH - (_ROW_RIGHT_GAP + bar_width if capped else 0)

    def height(n: int) -> int:
        heights = [row.totalHeightForWidth(width) for row in rows[:n]]
        return sum(heights) + row_layout.spacing() * max(0, len(heights) - 1)

    full = height(_VISIBLE_ITEM_ROWS)
    return min(full, height(_MIN_ITEM_ROWS)), full


def add_route_breakdown(layout: QVBoxLayout, owned: list, data: dict | None = None) -> None:
    """The header total split by how items are obtained: bought, crafted, or found in a dungeon.
    Adds up to the header's denominator, and explains why the shop can be complete while this isn't.
    Loot shows from 0/16."""
    owned_ids = set(owned)
    rows = QVBoxLayout()
    rows.setContentsMargins(0, 0, 0, 0)
    rows.setSpacing(1)
    for title, pool in (
        ("Purchasable items", shop_mod.collectibles_for_gold(data)),
        ("Gem-only items", shop_mod.gem_only_collectibles(data)),
        ("Dungeon loot", shop_mod.loot_collectibles()),
    ):
        add_section_heading(rows, title, owned_ids, pool)
    layout.addLayout(rows)


def _view_combo(options: tuple, view: dict, key: str, on_change: Callable[[str], None]) -> QComboBox:
    """A drop-down that keeps its pick in `view[key]` and calls `on_change(key)` after each one."""
    combo = QComboBox()
    for value, label in options:
        combo.addItem(label, value)
    combo.setCurrentIndex(max(0, combo.findData(view.get(key))))
    sheet = QApplication.instance().styleSheet()
    # Anki's style sheet makes Qt's own delegate tick the current item; a plain one lists them
    # bare. The native style has no such sheet and keeps its own list.
    if "QComboBox::item" in sheet:
        combo.setItemDelegate(QStyledItemDelegate(combo))
    # The trim is for that sheet's arrow, left to right only: it swaps the sides for right-to-left.
    ltr = combo.layoutDirection() == Qt.LayoutDirection.LeftToRight
    if ltr and "QComboBox::drop-down" in sheet:
        combo.setStyleSheet(_COMBO_TRIM)
    # Shrinkable, so a big font cuts the pick short instead of pushing past the window's fixed width.
    combo.setMinimumWidth(1)

    def pick(_index: int) -> None:
        view[key] = combo.currentData()
        on_change(key)

    combo.currentIndexChanged.connect(pick)
    return combo


def _remember_sort(view: dict) -> None:
    """Save the picked sort for the next time the window opens."""
    # A fresh load, not the window's copy, so nothing saved since it opened is written over.
    saved = storage.load()
    saved[_SORT_KEY] = view.get("sort")
    storage.save(saved)


def _add_list_bar(
    layout: QVBoxLayout, data: dict, view: dict | None = None,
    on_change: Callable[[str], None] | None = None,
) -> None:
    """The row above the list: the Shards held and how far they reach, once refinement is unlocked,
    and with `on_change` the list's Sort and Show drop-downs to their right, line for line."""
    unlocked = shop_mod.refinement_unlocked(data)
    if not unlocked and on_change is None:
        return
    grid = QGridLayout()
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setColumnStretch(1, 1)  # the slack goes between the two halves
    if unlocked:
        text = QLabel(f"Refinement shards: {shop_mod.shards(data)}")
        pm = _pixmap("currency/shard.png", 20)
        grid.addWidget(_label_with_pixmap(pm, text) if pm else text, 0, 0)
        top = prestige_mod.refinement_max_level(data)
        note = QLabel(f"Items up to level {top} can be refined.")
        note.setStyleSheet(_MUTED_STAT_STYLE)
        grid.addWidget(note, 1, 0)
    if on_change is not None:
        # Both filters are about refining, so Show waits for refinement as the Shards do.
        rows = [("Sort:", _SORTS, "sort")] + ([("Show:", _FILTERS, "filter")] if unlocked else [])
        for i, (label, options, key) in enumerate(rows):
            # One column, so both drop-downs take the width of the widest, Sort.
            name, combo = QLabel(label), _view_combo(options, view, key, on_change)
            name.setBuddy(combo)  # the label is the drop-down's name to a screen reader
            grid.addWidget(name, i, 2)
            grid.addWidget(combo, i, 3)
    layout.addLayout(grid)
    layout.addSpacing(4)


def build_items_content(
    layout: QVBoxLayout, on_refine: Callable[[str], None] | None = None, lucky: str | None = None,
    view: dict | None = None,
) -> None:
    """Fill `layout` with the bag, the count, the bonuses and the whole collection. `on_refine`
    adds the Refine buttons; `lucky` is the item a lucky refine just hit, tagged on its row; `view`
    carries the list's sort, filter and box height across the caller's rebuilds."""
    data = storage.load()
    owned = data.get("owned_collectibles", [])
    quality = shop_mod.quality_map(data)
    # Newest first. Filtered here, so unknown ids fall into the empty-state branch.
    owned_list = [cid for cid in reversed(owned) if shop_mod.get_collectible(cid)]
    view = {} if view is None else view
    view.setdefault("sort", data.get(_SORT_KEY))

    breakdown = QVBoxLayout()
    add_route_breakdown(breakdown, owned, data)
    add_detail_window_header(
        layout, "ui/items.png", "Items", f"{len(owned)}/{len(shop_mod.catalog(data))}",
        beneath=breakdown,
    )
    layout.addSpacing(4)

    # The items' own share of the panel's Stats section: what this collection alone adds.
    add_stats_rows(layout, stats_mod.item_stats(owned, quality))
    layout.addSpacing(8)

    if not owned_list:
        _add_list_bar(layout, data)
        empty_lbl = QLabel("No items owned yet.")
        empty_lbl.setStyleSheet(_DETAIL_MUTED)
        layout.addWidget(empty_lbl)
        return

    scroll = _ListScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    bar = scroll.verticalScrollBar()

    def _fit_gap(*_range: int) -> None:
        # The gap only while the scrollbar shows (a short screen can squeeze one in, too); without
        # it the buttons line up with Close.
        rows = scroll.widget()
        if rows is not None:
            rows.layout().setContentsMargins(0, 0, _ROW_RIGHT_GAP if bar.maximum() > 0 else 0, 0)

    bar.rangeChanged.connect(_fit_gap)

    def show_rows() -> QVBoxLayout:
        shown = _shown_items(data, owned_list, view, lucky)
        rows, row_layout = _items_list(shown, data, on_refine, lucky)
        scroll.setWidget(rows)  # deletes the rows it replaces and scrolls back to the top
        _fit_gap()  # a re-sort leaves the range as it was, so the signal alone would miss it
        return row_layout

    def on_view_change(key: str) -> None:
        show_rows()
        if key == "sort":
            _remember_sort(view)

    _add_list_bar(layout, data, view, on_view_change)
    row_layout = show_rows()
    # Sized once, by the unfiltered list the window opens on: a filter then empties part of the
    # box instead of resizing the window.
    if "box" not in view:
        view["box"] = _box_heights(row_layout, bar.sizeHint().width())
    scroll.setMinimumHeight(view["box"][0])
    scroll.setMaximumHeight(view["box"][1])
    # The only stretching widget, so it takes the slack up to its full height and gives it back
    # first when there is not enough to go round.
    layout.addWidget(scroll, 1)


def show_items_dialog(
    parent: QWidget | None = None, on_refresh: Callable[[], None] | None = None
) -> None:
    """Open the collection in its own window; refining rebuilds it in place."""
    d = QDialog(parent)
    d.setWindowTitle("CollectQuest — Items")
    outer = QVBoxLayout(d)
    outer.setContentsMargins(0, 0, 0, 0)
    holder: dict = {"content": None}
    # The list's sort and filter. The sort starts as it was last left, the filter at its default.
    view: dict = {}

    def on_refine(cid: str) -> None:
        data = storage.load()
        holder["lucky"] = None
        # Built from the save, so a stale button (Shards spent elsewhere) just redraws.
        before = shop_mod.item_quality(data, cid)
        if shop_mod.refine_item(data, cid):
            storage.save(data)
            # Two tiers in one click is the lucky refine. Held here, not saved, so the tag lasts
            # until the next refine or the window closing.
            if shop_mod.item_quality(data, cid) - before > 1:
                holder["lucky"] = cid
            if on_refresh:
                on_refresh()
        bar = holder["scroll"].verticalScrollBar() if holder.get("scroll") else None
        keep = bar.value() if bar else 0
        build()
        if holder.get("scroll"):
            QTimer.singleShot(0, lambda: holder["scroll"].verticalScrollBar().setValue(keep))

    def build() -> None:
        old = holder["content"]
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(6)
        pad_detail_window(layout)
        build_items_content(layout, on_refine, holder.get("lucky"), view)
        holder["close"] = add_detail_window_close_row(layout, d)
        holder["scroll"] = next(iter(content.findChildren(_ListScrollArea)), None)
        if old is not None:
            outer.removeWidget(old)
            old.hide()
            old.deleteLater()
        outer.addWidget(content)
        holder["content"] = content
        # Always the grid's width, so a bigger collection only makes the window taller.
        m = layout.contentsMargins()
        d.setFixedWidth(_WINDOW_WIDTH + m.left() + m.right())

    build()
    # Otherwise the window opens with the Sort drop-down focused, as the first control in it.
    holder["close"].setFocus()
    # Height from the wrapped lines at that width, clamped to the screen. adjustSize would cap it at
    # two thirds of the screen and squeeze the list box.
    screen = d.screen() or QApplication.primaryScreen()
    max_h = int(screen.availableGeometry().height() * 0.9) if screen else 900
    want_h = content_height(d, d.width())
    d.resize(d.width(), min(want_h, max_h))
    exec_dialog(d)