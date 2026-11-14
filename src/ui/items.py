"""The items window: the whole collection at full size, opened from the panel's [▸] button."""
from __future__ import annotations

from typing import Callable

from aqt.qt import (
    QApplication,
    QDialog,
    QFontMetrics,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
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
    return list_widget, list_layout


def add_route_breakdown(layout: QVBoxLayout, owned: list, data: dict | None = None) -> None:
    """The header total split by how items are obtained: bought, crafted, or found in a dungeon.
    Adds up to the header's denominator, and explains why the shop can be complete while this isn't.
    Loot shows from 0/8."""
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


def _add_shard_balance(layout: QVBoxLayout, data: dict) -> None:
    """The Shards held, where they're spent; only once refinement is unlocked."""
    if not shop_mod.refinement_unlocked(data):
        return
    top = prestige_mod.refinement_max_level(data)
    text = QLabel(f"Refinement shards: {shop_mod.shards(data)}")
    pm = _pixmap("currency/shard.png", 20)
    row = QHBoxLayout()
    row.addWidget(_label_with_pixmap(pm, text) if pm else text)
    row.addStretch()
    layout.addLayout(row)
    note = QLabel(f"Items up to level {top} can be refined.")
    note.setStyleSheet(_MUTED_STAT_STYLE)
    layout.addWidget(note)
    layout.addSpacing(4)


def build_items_content(
    layout: QVBoxLayout, on_refine: Callable[[str], None] | None = None, lucky: str | None = None,
) -> None:
    """Fill `layout` with the bag, the count, the bonuses and the whole collection. `on_refine`
    adds the Refine buttons; `lucky` is the item a lucky refine just hit, tagged on its row."""
    data = storage.load()
    owned = data.get("owned_collectibles", [])
    quality = shop_mod.quality_map(data)
    # Newest first. Filtered here, so unknown ids fall into the empty-state branch.
    owned_list = [cid for cid in reversed(owned) if shop_mod.get_collectible(cid)]

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
    _add_shard_balance(layout, data)

    if not owned_list:
        empty_lbl = QLabel("No items owned yet.")
        empty_lbl.setStyleSheet(_DETAIL_MUTED)
        layout.addWidget(empty_lbl)
        return

    rows, row_layout = _items_list(owned_list, data, on_refine, lucky)
    scroll = _ListScrollArea()
    capped = row_layout.count() > _VISIBLE_ITEM_ROWS
    # Rows wrap to the fixed width, less the scrollbar and its gap when there is one.
    rows_w = _WINDOW_WIDTH - (
        _ROW_RIGHT_GAP + scroll.verticalScrollBar().sizeHint().width() if capped else 0
    )

    def _fit_gap(_min: int, maximum: int) -> None:
        # The gap only while the scrollbar shows (a short screen can squeeze one in, too); without
        # it the buttons line up with Close.
        row_layout.setContentsMargins(0, 0, _ROW_RIGHT_GAP if maximum > 0 else 0, 0)

    scroll.verticalScrollBar().rangeChanged.connect(_fit_gap)

    def _rows_height(n: int) -> int:
        """The height of the first `n` rows at the width they will get."""
        n = min(n, row_layout.count())
        return sum(
            row_layout.itemAt(i).layout().totalHeightForWidth(rows_w) for i in range(n)
        ) + row_layout.spacing() * (n - 1)

    height = _rows_height(_VISIBLE_ITEM_ROWS)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setWidget(rows)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setMinimumHeight(min(height, _rows_height(_MIN_ITEM_ROWS)))
    scroll.setMaximumHeight(height)
    # The only stretching widget, so it takes the slack up to its six rows and gives it back first
    # when there is not enough to go round.
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
        build_items_content(layout, on_refine, holder.get("lucky"))
        add_detail_window_close_row(layout, d)
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
    # Height from the wrapped lines at that width, clamped to the screen. adjustSize would cap it at
    # two thirds of the screen and squeeze the list box.
    screen = d.screen() or QApplication.primaryScreen()
    max_h = int(screen.availableGeometry().height() * 0.9) if screen else 900
    want_h = content_height(d, d.width())
    d.resize(d.width(), min(want_h, max_h))
    exec_dialog(d)