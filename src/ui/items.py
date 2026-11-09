"""The items window: the whole collection at full size, opened from the panel's [▸] button."""
from __future__ import annotations

import html
from typing import Callable

from aqt.qt import (
    QApplication,
    QDialog,
    QFontMetrics,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTimer,
    QVBoxLayout,
    QWidget,
    Qt,
)

from .. import prestige as prestige_mod, shop as shop_mod, storage
from .assets import (
    _icon_pixmap,
    _label_with_pixmap,
    _pixmap,
    add_detail_window_close_row,
    add_detail_window_header,
    add_section_heading,
    content_height,
    drawn_button,
    exec_dialog,
    finish_drawn_button,
    pad_detail_window,
    quality_name_html,
)
from .constants import _DETAIL_MUTED, _MUTED_STAT_STYLE
from .hover_tip import set_hover_tip

# Item rows the scroll box shows at once; the icon grid above always stays whole.
_VISIBLE_ITEM_ROWS = 6
# What the box may be squeezed to on a short screen: a floor rather than a fixed height, or the
# close row gets drawn over it.
_MIN_ITEM_ROWS = 2


# Icons shrink in steps as the collection grows. The window is always exactly this many full-size
# icons wide, so a bigger collection only makes it taller; smaller icons fit more per row.
_ICON_PX_LARGE = 32
_ICON_PX_SMALL = 28
_ICON_PX_TINY = 24
_ICON_SMALL_FROM = 33  # 3 full rows of 11
_ICON_TINY_FROM = 48  # 4 full rows of 12
_GRID_SPACING = 6
_GRID_COLS = 10
_GRID_WIDTH = _GRID_COLS * _ICON_PX_LARGE + (_GRID_COLS - 1) * _GRID_SPACING


_fmt = shop_mod.format_amount


def items_stats_parts(owned: list, quality: dict | None = None) -> list[str]:
    """The collection's standing bonuses as ["+2% XP", ..., "+5% gem luck"], excluding the streak
    and dungeon stats (see streak_stats_parts, dungeon_stats_parts). `quality` is quality_map."""
    parts: list[str] = []
    xp_pct = shop_mod.xp_bonus_percent(owned, quality)
    xp_flat = shop_mod.xp_flat(owned, quality)
    gold_pct = shop_mod.gold_bonus_percent(owned, quality)
    gold_flat = shop_mod.gold_flat(owned, quality)
    luck_pct = shop_mod.luck_gem_chance_percent(owned, quality)
    shard_pct = shop_mod.luck_shard_chance_percent(owned, quality)
    if xp_pct:
        parts.append(f"+{_fmt(xp_pct)}% XP")
    if xp_flat:
        parts.append(f"+{_fmt(xp_flat)} XP/review")
    if gold_pct:
        parts.append(f"+{_fmt(gold_pct)}% gold")
    if gold_flat:
        parts.append(f"+{_fmt(gold_flat)}g")
    if luck_pct:
        parts.append(f"+{_fmt(luck_pct)}% gem luck")
    if shard_pct:
        parts.append(f"+{_fmt(shard_pct)}% shard luck")
    return parts


def streak_stats_parts(owned: list, quality: dict | None = None) -> list[str]:
    """The 7-day streak reward bonus, on its own line between the standing bonuses and dungeons."""
    pct = shop_mod.streak_reward_bonus_percent(owned, quality)
    return [f"+{_fmt(pct)}% 7-day streak rewards"] if pct else []


def dungeon_stats_parts(owned: list, quality: dict | None = None) -> list[str]:
    """The two dungeon bonuses, long enough to need their own line; worded as the items are, and
    last in reading order."""
    parts: list[str] = []
    discover = shop_mod.dungeon_discover_percent(owned, quality)
    explore = shop_mod.dungeon_explore_percent(owned, quality)
    if discover:
        parts.append(f"+{_fmt(discover)}% chance to find a dungeon")
    if explore:
        parts.append(f"+{_fmt(explore)}% faster dungeon exploration")
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
    layout, owned: list, for_panel: bool = False, indent: bool = False, wrap: bool = False,
    quality: dict | None = None,
) -> bool:
    """The gray lines of standing bonuses; returns whether any were added. The streak bonus and the
    dungeon pair take a line each. `indent` is for the panel's section heading; `wrap` for the
    fixed-width Items window."""
    lines = [
        items_stats_parts(owned, quality), streak_stats_parts(owned, quality),
        dungeon_stats_parts(owned, quality),
    ]
    if not any(lines):
        return False
    sep = "  ·  "

    def add_line(segments: list[str]) -> None:
        row = _stats_row(layout, indent)
        if wrap:
            # Break between stats only, never inside one; stretch 1 so it wraps at the window's
            # width, not at the label's own guess.
            lbl = _stat_label(sep.join(seg.replace(" ", "\u00a0") for seg in segments), for_panel)
            lbl.setWordWrap(True)
            row.addWidget(lbl, 1)
        else:
            row.addWidget(_stat_label(sep.join(segments), for_panel))
            row.addStretch()
        layout.addLayout(row)

    # Empty lines are skipped rather than left as gaps, so whichever line has stats leads.
    for segments in lines:
        if segments:
            add_line(segments)
    return True


def _icons_grid(owned_list: list, quality: dict | None = None) -> QWidget:
    """The icon grid: every owned item as a pixmap with a hover tip, as many per row as fit."""
    if len(owned_list) >= _ICON_TINY_FROM:
        icon_sz = _ICON_PX_TINY
    elif len(owned_list) >= _ICON_SMALL_FROM:
        icon_sz = _ICON_PX_SMALL
    else:
        icon_sz = _ICON_PX_LARGE
    icons_widget = QWidget()
    icons_widget.setFixedWidth(_GRID_WIDTH)
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
        q = int((quality or {}).get(cid, 0) or 0)
        name = shop_mod.display_name(c, q)
        effect = shop_mod.effect_text(c, q)
        icon_lbl = QLabel()
        icon_lbl.setPixmap(pm)
        set_hover_tip(icon_lbl, f"{name}: {effect}" if effect else name)
        icon_labels.append(icon_lbl)
    # The last column needs no trailing spacing, hence the + _GRID_SPACING.
    cols = (_GRID_WIDTH + _GRID_SPACING) // (icon_sz + _GRID_SPACING)
    for i, lbl in enumerate(icon_labels):
        r, c = divmod(i, cols)
        icons_layout.addWidget(lbl, r, c)
    # A single row sits left; a full grid is centered, evening out the slack smaller icons leave.
    if len(icon_labels) <= cols:
        icons_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    else:
        icons_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
    return icons_widget


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


def _items_list(
    owned_list: list, data: dict | None = None, on_refine: Callable[[str], None] | None = None,
) -> tuple[QWidget, QVBoxLayout]:
    """One row per owned item: icon, name and effect, and its Refine button. Returns the layout too,
    for sizing the scroll box."""
    data = data or {}
    list_widget = QWidget()
    list_layout = QVBoxLayout(list_widget)
    list_layout.setContentsMargins(0, 0, _ROW_RIGHT_GAP, 0)
    for cid in owned_list:
        c = shop_mod.get_collectible(cid)
        if not c:
            continue
        row = QHBoxLayout()
        pm = _icon_pixmap(c["image"])
        if pm:
            icon = QLabel()
            icon.setPixmap(pm)
            row.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        q = shop_mod.item_quality(data, cid)
        desc = quality_name_html(c, q)
        effect = shop_mod.effect_text(c, q)
        if effect:
            # Under the name, small and gray, as the shop's rows show it.
            desc += f'<br><span style="{_MUTED_STAT_STYLE}">{html.escape(effect)}</span>'
        lbl = QLabel(desc)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setWordWrap(True)
        row.addWidget(lbl, 1)
        btn = _refine_button(data, cid, on_refine)
        if btn is not None:
            row.addWidget(btn, 0, Qt.AlignmentFlag.AlignTop)
        list_layout.addLayout(row)
    return list_widget, list_layout


def add_route_breakdown(layout: QVBoxLayout, owned: list, data: dict | None = None) -> None:
    """The header total split by how items are obtained: bought, crafted, or found in a dungeon.
    Adds up to the header's denominator, and explains why the shop can be complete while this isn't.
    Loot shows from 0/8."""
    owned_ids = set(owned)
    rows = QVBoxLayout()
    rows.setContentsMargins(12, 0, 0, 0)
    rows.setSpacing(1)
    for title, pool in (
        ("Purchasable items", shop_mod.collectibles_for_gold(data)),
        ("Gem-only items", shop_mod.gem_only_collectibles(data)),
        ("Dungeon loot", shop_mod.loot_collectibles()),
    ):
        add_section_heading(rows, title, owned_ids, pool)
    layout.addLayout(rows)
    layout.addSpacing(4)


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
    layout: QVBoxLayout, on_refine: Callable[[str], None] | None = None
) -> None:
    """Fill `layout` with the bag, the count, the bonuses and the whole collection. `on_refine`
    adds the Refine buttons."""
    data = storage.load()
    owned = data.get("owned_collectibles", [])
    quality = shop_mod.quality_map(data)
    # Newest first. Filtered here, so unknown ids fall into the empty-state branch.
    owned_list = [cid for cid in reversed(owned) if shop_mod.get_collectible(cid)]

    add_detail_window_header(
        layout, "collectibles/Bag.png", "Items", f"{len(owned)}/{len(shop_mod.catalog(data))}"
    )

    add_route_breakdown(layout, owned, data)

    # The same lines the panel shows, repeated here so the window answers "what am I getting for
    # this collection?" without sending the reader back to the panel for the figures.
    add_items_stats_row(layout, owned, wrap=True, quality=quality)
    layout.addSpacing(8)
    _add_shard_balance(layout, data)

    if not owned_list:
        empty_lbl = QLabel("No items owned yet.")
        empty_lbl.setStyleSheet(_DETAIL_MUTED)
        layout.addWidget(empty_lbl)
        return

    # The grid sits outside the scroll box, so every item is visible at once however many there are.
    layout.addWidget(_icons_grid(owned_list, quality))
    layout.addSpacing(8)

    rows, row_layout = _items_list(owned_list, data, on_refine)
    scroll = _ListScrollArea()
    capped = row_layout.count() > _VISIBLE_ITEM_ROWS
    # Rows wrap to the fixed width, less the scrollbar when there is one, so measure them there.
    rows_w = _GRID_WIDTH - _ROW_RIGHT_GAP - (
        scroll.verticalScrollBar().sizeHint().width() if capped else 0
    )

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
        # Built from the save, so a stale button (Shards spent elsewhere) just redraws.
        if shop_mod.refine_item(data, cid):
            storage.save(data)
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
        build_items_content(layout, on_refine)
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
        d.setFixedWidth(_GRID_WIDTH + m.left() + m.right())

    build()
    # Height from the wrapped lines at that width, clamped to the screen. adjustSize would cap it at
    # two thirds of the screen and squeeze the list box.
    screen = d.screen() or QApplication.primaryScreen()
    max_h = int(screen.availableGeometry().height() * 0.9) if screen else 900
    want_h = content_height(d, d.width())
    d.resize(d.width(), min(want_h, max_h))
    exec_dialog(d)