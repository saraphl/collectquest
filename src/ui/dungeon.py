"""The dungeon window: where you are in a dungeon, what you have taken, and the auto-pick setting."""
from __future__ import annotations

from typing import Any, Callable

from aqt.qt import (
    QAbstractItemView,
    QFrame,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QTimer,
    QVBoxLayout,
    QWidget,
    Qt,
)

from .. import dungeon as dungeon_mod, review_rewards, shop as shop_mod, storage
from .assets import _icon_pixmap, add_item_row, equalize_button_widths, exec_dialog, night_mode
from .constants import (
    _DETAIL_MUTED,
    _MUTED_STAT_STYLE,
    _PATH_CELL_BORDER_DARK,
    _PATH_CELL_BORDER_LIGHT,
)

# The window's own icon, at the size the milestones window heads itself with. Icon_Dungeon.png is
# 82x78 and would be upscaled here; this one has the headroom.
_HEADER_ICON = "ui/Icon_BossDungeon.png"
_HEADER_ICON_PX = 96
_TREASURE_ICON = "ui/dungeon_treasure_chest.png"
_PATH_ICON_PX = 40
# Between the pathway cells. Tight enough that three fixed-width cells do not read as three
# separate rows of one.
_PATH_CELL_GAP = 6
# Inside each cell's frame, between the border and what it encloses.
_PATH_CELL_PAD = 6
_PATH_CELL_RADIUS = 4
# The frame's own line. Named because the width has to count it as well as draw it: the border
# sits outside the contents rect, so a cell sized to padding alone leaves the button two pixels
# short of its fixed width and pushes it off centre.
_PATH_CELL_BORDER_PX = 1
# The widest labels offer_summary can produce, measured to fix the button width. "000g + 00 gems"
# stands in for the currency paths: three-digit gold and two-digit gems is past anything the rolls
# and the bonus stack can reach, and a digit-shaped sample is what keeps this from needing a revisit
# every time an item changes the amounts.
_WIDEST_PATH_LABELS = ("Unknown item", "000g + 00 gems")
# A floor, not a width. The content asks for about 250px - narrow enough that the loot line and
# the pathway rows crowd against both edges - so the window is held open to this and the height is
# left entirely to the layout. Forcing the width any wider than the floor only spreads the same
# rows across more space and makes the window look padded.
_MIN_WIDTH = 360
# Between the rows. The 6px Qt default read as a gap between separate things rather than as one
# block of related lines, which is what the loot summary and the numbered pathways are.
_ROW_SPACING = 4
# The numbered pathways are one list, not a stack of separate lines, and read as a block at this.
_LIST_ROW_SPACING = 1
# Tall enough for the five rows without a scrollbar, short enough not to dominate a small dialog.
_ORDER_LIST_HEIGHT = 130
# The catch-up prompt's buttons are dead this long too, for the same reason as the path buttons
# below: it arrives unannounced after a sync, and one of its two answers cannot be taken back.
_PROMPT_ARM_MS = 1000
# How long the path buttons stay dead after a catch-up puts a fresh branching under the cursor.
# The buttons land where the ones just clicked were, so without this a double-click takes the next
# pathway too - a decision the player never saw, on a choice that cannot be undone.
_CHAIN_ARM_MS = 450


def _fit(dialog) -> None:
    """
    Resize the window to what its current content needs, in both directions.

    Deferred by a zero-timer at every call site: a wrapped line only knows its final height once
    the width it has to wrap into is settled, so this second pass catches a state whose text
    rewrapped at the width the first pass chose.

    Both directions, unlike assets.refit_dialog_height, which only ever shrinks a height: the
    states here differ in width too, and one of them is the widest text in the feature.
    """
    try:
        hint = dialog.sizeHint()
        dialog.resize(max(dialog.minimumWidth(), hint.width()), hint.height())
    except RuntimeError:
        pass  # closed before the timer fired


def _path_cell_style() -> str:
    """The frame around one pathway, in the shade the current theme wants."""
    border = _PATH_CELL_BORDER_DARK if night_mode() else _PATH_CELL_BORDER_LIGHT
    return (
        "QFrame#cqPathCell { border: %dpx solid %s; border-radius: %dpx; }"
        % (_PATH_CELL_BORDER_PX, border, _PATH_CELL_RADIUS)
    )


def _size_path_row(buttons: list[QPushButton], row: QWidget | None) -> None:
    """
    Give every path button one width, and its row room for the most paths a branching can offer.

    Width comes from the widest label the feature can produce rather than the widest one on screen,
    so a row reading "51g" and "2 gems" is the same shape as one reading "Unmarked path" - chaining
    through a backlog otherwise resized the buttons on every screen.

    Called once the window is up, and measured by borrowing a real button: a QPushButton built for
    the purpose carries the application font, not the one the dialog will draw it in, and sizing to
    that measurement clipped the labels on any theme whose font is wider. Each button's own hint is
    in the running too, so a label longer than every sample widens the row rather than being cut.
    """
    if not buttons:
        return
    probe = buttons[0]
    keep = probe.text()
    samples = list(_WIDEST_PATH_LABELS) + [dungeon_mod.PATH_LABELS[dungeon_mod.PATH_UNMARKED]]
    width = max(b.sizeHint().width() for b in buttons)
    for text in samples:
        probe.setText(text)
        width = max(width, probe.sizeHint().width())
    probe.setText(keep)
    for btn in buttons:
        btn.setFixedWidth(width)
    # The frame's padding is part of the cell, and the row has to reserve it: sized to the button
    # alone, the cell squeezes the button past its own right edge and clips it.
    cell_width = width + 2 * (_PATH_CELL_PAD + _PATH_CELL_BORDER_PX)
    for btn in buttons:
        cell = btn.parentWidget()
        if cell is not None:
            cell.setFixedWidth(cell_width)
    if row is not None:
        # Held whether or not all the cells are there, so a two-path screen does not draw a
        # narrower window than the three-path one before it. The stretches centre a short row.
        most = max(dungeon_mod.PATHS_PER_BRANCHING)
        row.setFixedWidth(most * cell_width + (most - 1) * _PATH_CELL_GAP)


def _arm(buttons: list[QPushButton]) -> None:
    """Make buttons clickable again once they have settled: the chained path buttons, and the
    catch-up prompt's pair. Both start dead so a click meant for the previous screen cannot land
    on an irreversible choice."""
    for btn in buttons:
        try:
            btn.setEnabled(True)
        except RuntimeError:
            pass  # the window closed, or another rebuild replaced them


def _title(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("font-weight: bold; font-size: 13px;")
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return lbl


def _muted(text: str, center: bool = False, wrap: bool = True) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(_DETAIL_MUTED)
    lbl.setWordWrap(wrap)
    if center:
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return lbl


def _centered_icon(image: str, size: int = _HEADER_ICON_PX) -> QLabel | None:
    pm = _icon_pixmap(image, size, content=size)
    if not pm:
        return None
    lbl = QLabel()
    lbl.setPixmap(pm)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return lbl


def _cards(n: int) -> str:
    return f"{n} card" + ("s" if n != 1 else "")


def _item_name(cid: str | None) -> str:
    c = shop_mod.get_collectible(cid) if cid else None
    return c.get("name", cid) if c else (cid or "")


def _amounts(took: dict[str, Any]) -> str:
    """The gold and gems on one offer, as a phrase. "nothing" when it held neither."""
    parts = []
    if took.get("gold"):
        parts.append(f"{took['gold']}g")
    gems = took.get("gems") or 0
    if gems:
        parts.append(f"{gems} gem" + ("s" if gems != 1 else ""))
    return " + ".join(parts) if parts else "nothing"


def _revealed(took: dict[str, Any]) -> str:
    """
    One pick with its secret opened: "Unknown item (Bronze Helm)", "Unmarked path (26g + 1 gem)".

    Only ever called once the treasure has been reached. The three currency paths are returned
    unchanged - they showed their amount on the button and have nothing left to tell - so this adds
    a parenthesis exactly where one was withheld.
    """
    face = dungeon_mod.offer_summary(took)
    if took.get("kind") not in (dungeon_mod.PATH_UNIQUE, dungeon_mod.PATH_UNMARKED):
        return face
    if took.get("item"):
        return f"{face} ({_item_name(took['item'])})"
    return f"{face} ({_amounts(took)})"


def _add_loot(layout: QVBoxLayout, gold: int, gems: int, item: str | None) -> None:
    """
    "Total loot: 26g, 5 gems, unique item", and the item's own row beneath it when there is one.

    The line names the *kind* rather than the item, because the row below is where the item is
    actually shown - the same icon, name and effect the shop gives a fresh craft. Naming it twice
    would make the row look like a second thing found.
    """
    parts = []
    if gold:
        parts.append(f"{gold}g")
    if gems:
        parts.append(f"{gems} gem" + ("s" if gems != 1 else ""))
    if item:
        parts.append("unique item")
    layout.addWidget(_muted("Total loot: " + (", ".join(parts) if parts else "nothing")))
    c = shop_mod.get_collectible(item) if item else None
    if c:
        add_item_row(layout, c)


def _add_bonus_lines(layout: QVBoxLayout, pity: int, from_items: float, kind: str) -> None:
    """
    The pity bonus, and the total once items add to it. `kind` is "discovery" or "exploration".

    The total is drawn only when items contribute: with none it would only restate the figure above.
    """
    if pity:
        layout.addWidget(_muted(
            f"+{pity}% bonus dungeon {kind} since {dungeon_mod.PITY_FLOOR_REVIEWS}th answer",
            wrap=False,
        ))
    if from_items > 0:
        layout.addWidget(_muted(
            f"+{int(from_items + pity)}% total dungeon {kind}", wrap=False,
        ))


def _add_pathway_list(layout: QVBoxLayout, taken: list, reveal: bool = False) -> None:
    """
    The numbered record of what was chosen, worded as the buttons were.

    `reveal` opens the two that kept a secret, and is passed only by the treasure and the
    last-dungeon summary. Everywhere else the list has to read exactly as the buttons did, or a
    dungeon still running would tell the player what it is holding for them.
    """
    if not taken:
        return
    layout.addSpacing(6)
    layout.addWidget(_muted("Pathways taken:"))
    rows = QVBoxLayout()
    rows.setContentsMargins(0, 0, 0, 0)
    rows.setSpacing(_LIST_ROW_SPACING)
    for i, took in enumerate(taken, start=1):
        text = _revealed(took or {}) if reveal else dungeon_mod.offer_summary(took or {})
        row = QLabel(f"  {i}. {text}")
        row.setStyleSheet(_MUTED_STAT_STYLE)
        rows.addWidget(row)
    layout.addLayout(rows)


# --- Auto-pick ---------------------------------------------------------------------------------

def _locked_auto_pick_dialog(parent: QWidget | None, claimed: int) -> None:
    """
    The gate, drawn the way the locked shop draws its own: icon, the rule, the count, Close.

    Mirrors show_shop_dialog's early return beat for beat so the two read as the same kind of
    "not yet" - but with _icon_pixmap rather than _pixmap, so the dungeon icon is the same visual
    size here as in the window one click away.
    """
    d = QDialog(parent)
    d.setWindowTitle("CollectQuest — Auto-pick")
    layout = QVBoxLayout(d)
    layout.addSpacing(12)
    icon = _centered_icon(_HEADER_ICON)
    if icon:
        layout.addWidget(icon)
    layout.addWidget(
        _title(f"Auto-pick available after {dungeon_mod.AUTO_PICK_UNLOCK_DUNGEONS} dungeons!")
    )
    count = QLabel(f"Dungeons completed: {claimed} / {dungeon_mod.AUTO_PICK_UNLOCK_DUNGEONS}")
    count.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(count)
    layout.addSpacing(12)
    close = QPushButton("Close")
    close.clicked.connect(d.accept)
    layout.addWidget(close)
    exec_dialog(d)
def _auto_pick_dialog(parent: QWidget | None, on_change: Callable[[], None]) -> None:
    """The setting itself: the switch, what it costs, and the ranking it follows."""
    data = storage.load()
    d = QDialog(parent)
    d.setWindowTitle("CollectQuest — Auto-pick")
    layout = QVBoxLayout(d)
    layout.setSpacing(6)

    cb = QCheckBox("Pick pathways automatically")
    cb.setChecked(bool(data.get(dungeon_mod.KEY_AUTO_ENABLED, False)))
    layout.addWidget(cb)

    # No color set: this line is the disclosure that makes the setting honest, and a hardcoded gray
    # is near-invisible in dark mode. Smaller, and the theme supplies the color.
    note = QLabel("Auto-pick follows your order, not the amounts offered. Picking by hand can pay more.")
    note.setStyleSheet("font-size: 10px;")
    note.setWordWrap(True)
    layout.addWidget(note)
    layout.addSpacing(4)

    layout.addWidget(_muted("Drag to reorder. The highest-ranked pathway on offer is taken."))
    order_list = QListWidget()
    order_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
    order_list.setFixedHeight(_ORDER_LIST_HEIGHT)
    for kind in dungeon_mod.auto_pick_order(data):
        order_list.addItem(dungeon_mod.PATH_LABELS.get(kind, kind))
    layout.addWidget(order_list)

    def _save() -> None:
        """Written on every change, as every control in Options already is: no Apply button."""
        saved = storage.load()
        saved[dungeon_mod.KEY_AUTO_ENABLED] = cb.isChecked()
        by_label = {v: k for k, v in dungeon_mod.PATH_LABELS.items()}
        saved[dungeon_mod.KEY_AUTO_ORDER] = [
            by_label[order_list.item(i).text()]
            for i in range(order_list.count())
            if order_list.item(i).text() in by_label
        ]
        storage.save(saved)
        on_change()

    def _sync_enabled() -> None:
        # Grayed rather than hidden, so the order stays legible before the switch is on.
        order_list.setEnabled(cb.isChecked())

    cb.stateChanged.connect(lambda _s: (_sync_enabled(), _save()))
    order_list.model().rowsMoved.connect(lambda *_a: _save())
    _sync_enabled()

    layout.addSpacing(8)
    row = QHBoxLayout()
    row.addStretch()
    close = QPushButton("Close")
    close.clicked.connect(d.accept)
    close.setMinimumWidth(close.sizeHint().width() * 2)
    row.addWidget(close)
    layout.addLayout(row)
    exec_dialog(d)
def _auto_pick_button(
    parent: QWidget | None, on_change: Callable[[], None], data: dict[str, Any] | None = None
) -> QPushButton:
    """
    The Auto-pick button, grayed by stylesheet while locked but never disabled.

    Necessary rather than stylistic: a disabled Qt button is not clickable, so it could not open
    the dialog that explains the gate, which is the only place the gate is explained - nothing in
    this window uses a hover tooltip. The bottom-bar Shop button grays the same way.
    """
    data = storage.load() if data is None else data
    unlocked = dungeon_mod.has_auto_pick(data)
    claimed = dungeon_mod.dungeons_claimed(data)
    btn = QPushButton("Auto-pick")
    if unlocked:
        btn.clicked.connect(lambda: _auto_pick_dialog(parent, on_change))
    else:
        btn.setStyleSheet("QPushButton { color: #666; }")
        btn.clicked.connect(lambda: _locked_auto_pick_dialog(parent, claimed))
    return btn


# --- The four states ---------------------------------------------------------------------------

def _add_pick_log(layout: QVBoxLayout, data: dict[str, Any]) -> None:
    """
    What has been taken so far, worded exactly as the button that was clicked.

    offer_summary rather than a description of the outcome, which is what makes the log a record of
    the choices as they were presented. It also keeps the one promise the design makes about the
    item: a Unique pick reads "Unknown item" here too, and is named only once the treasure is
    reached. Describing the outcome instead would have spoiled it several branchings early.
    """
    _add_pathway_list(layout, [e.get("took") for e in dungeon_mod.picks(data)])


def _add_idle(layout: QVBoxLayout, data: dict[str, Any]) -> None:
    """No dungeon open: the last one's result, or the search a player who has none is still on."""
    last = data.get("last_dungeon")
    icon = _centered_icon(_HEADER_ICON)
    if icon:
        layout.addWidget(icon)
    # Answers spent searching, and what they have bought. Only counted above level 15, so the
    # figure is answers that could have found something rather than every card ever answered.
    searched = dungeon_mod.search_reviews(data)
    owned = data.get("owned_collectibles", [])
    has_last = isinstance(last, dict)
    if has_last:
        layout.addWidget(_title("Last dungeon"))
        text = f"{_cards(searched)} answered since completing the last dungeon."
    else:
        layout.addWidget(_title("No dungeon discovered yet."))
        text = f"{_cards(searched)} answered so far without finding an entrance."
    layout.addWidget(_muted(text, wrap=False))
    _add_bonus_lines(
        layout, dungeon_mod.discover_pity_percent(data),
        shop_mod.dungeon_discover_percent(owned), "discovery",
    )
    if not has_last:
        return
    _add_loot(layout, int(last.get("gold") or 0), int(last.get("gems") or 0), last.get("item"))
    _add_pathway_list(layout, last.get("picked") or [], reveal=True)


def _add_venturing(layout: QVBoxLayout, data: dict[str, Any]) -> None:
    state = dungeon_mod.get_state(data) or {}
    icon = _centered_icon(_HEADER_ICON)
    if icon:
        layout.addWidget(icon)
    layout.addWidget(_title("Review more cards to venture further into the dungeon."))
    # One line, because the second figure needs no clause of its own and the pair reads as one
    # measurement. Before the first branching there is no pathway to be on - the player is only in
    # the dungeon - and the two counters hold the same number, so that case drops to the half that
    # is true rather than printing one figure twice under different names.
    entrance = int(state.get("reviews_since_entrance", 0))
    if int(state.get("branchings_done", 0)) > 0:
        on_path = int(state.get("reviews_since_branching", 0))
        text = f"{_cards(on_path)} answered on this pathway, {entrance} since the entrance."
    else:
        text = f"{_cards(entrance)} answered since the entrance."
    # This line and the bonus lines under it must not wrap: each is a single measurement, and split
    # across two lines it reads as two. Unwrapped, their full width joins the layout's minimum, so
    # the window opens wide enough to hold them rather than sizing itself to the title alone.
    layout.addWidget(_muted(text, wrap=False))
    _add_bonus_lines(
        layout, dungeon_mod.explore_pity_percent(data),
        shop_mod.dungeon_explore_percent(data.get("owned_collectibles", [])), "exploration",
    )
    _add_pick_log(layout, data)


def _add_pending(
    layout: QVBoxLayout, data: dict[str, Any], on_choose: Callable[[int], None]
) -> tuple[list[QPushButton], QWidget]:
    """The choice: one button per offered path, in the fixed left-to-right order, icon above.

    Returns the buttons and the row holding them: the window disarms the buttons for a moment when
    it has chained into a fresh branching (see _CHAIN_ARM_MS), and sizes both once it is up
    (_size_path_row).
    """
    # The window keeps its own icon here as in the venturing and idle states. Only the treasure
    # swaps it, for the chest that is the point of that screen.
    icon = _centered_icon(_HEADER_ICON)
    if icon:
        layout.addWidget(icon)
    layout.addWidget(_title("Branching pathways!"))
    layout.addWidget(_muted(
        "Several pathways appeared in front of you. Markings on the walls promise different"
        " rewards at the end.",
        center=True,
    ))
    layout.addSpacing(6)

    row_holder = QWidget()
    row = QHBoxLayout(row_holder)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(_PATH_CELL_GAP)
    row.addStretch()
    buttons = []
    for index, offer in enumerate((dungeon_mod.pending(data) or {}).get("paths", [])):
        cell = QVBoxLayout()
        # The frame's inset, set here rather than left to Qt: its default nine is wider than the
        # frame wants, and _size_path_row reserves exactly this much when it fixes the cell width.
        cell.setContentsMargins(
            _PATH_CELL_PAD, _PATH_CELL_PAD, _PATH_CELL_PAD, _PATH_CELL_PAD
        )
        cell.setSpacing(2)
        pm = _icon_pixmap(dungeon_mod.PATH_ICONS.get(offer.get("kind"), ""), _PATH_ICON_PX,
                          content=_PATH_ICON_PX)
        if pm:
            icon_lbl = QLabel()
            icon_lbl.setPixmap(pm)
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell.addWidget(icon_lbl)
        btn = QPushButton(dungeon_mod.offer_summary(offer))
        # Return must not pick a pathway. Taking one is irreversible and the choice is the point.
        btn.setAutoDefault(False)
        btn.clicked.connect(lambda _checked=False, i=index: on_choose(i))
        buttons.append(btn)
        cell.addWidget(btn)
        holder = QFrame()
        # Named, so the rule reaches this frame alone - an unnamed QFrame selector would put the
        # border on the button and the icon label inside it too.
        holder.setObjectName("cqPathCell")
        holder.setStyleSheet(_path_cell_style())
        holder.setLayout(cell)
        row.addWidget(holder)
    row.addStretch()
    # Centred explicitly: the holder is given a fixed width below, and a fixed-width widget in a
    # box layout sits at the left of the space it is given rather than in the middle of it.
    layout.addWidget(row_holder, 0, Qt.AlignmentFlag.AlignHCenter)
    _add_pick_log(layout, data)
    return buttons, row_holder


def _add_treasure(layout: QVBoxLayout, data: dict[str, Any]) -> None:
    icon = _centered_icon(_TREASURE_ICON)
    if icon:
        layout.addWidget(icon)
    layout.addWidget(_title("Treasure room!"))
    totals = dungeon_mod.treasure_totals(data)
    # The item is shown here and nowhere earlier: it is the one thing the dungeon withheld, which
    # is what makes reaching the treasure a reveal rather than a restated total.
    _add_loot(layout, totals["gold"], totals["gems"], totals["item"])
    _add_pathway_list(layout, [e.get("took") for e in dungeon_mod.picks(data)], reveal=True)


def show_catch_up_prompt(parent: QWidget | None, locked: bool) -> bool:
    """
    Offer to auto-pick a backlog too big to be worth clicking through. True if the player accepts.

    Shown after a sync only, and only when auto-pick is not already doing this. `locked` picks the
    word for why it is not: the setting is either off, or not yet earned.
    """
    d = QDialog(parent)
    d.setWindowTitle("CollectQuest — Dungeon")
    layout = QVBoxLayout(d)
    icon = _centered_icon(_HEADER_ICON)
    if icon:
        layout.addWidget(icon)
    text = QLabel(
        f"Over {dungeon_mod.CATCH_UP_PROMPT_MIN_BANK} reviews were synced, but dungeon path"
        f" auto-pick is {'locked' if locked else 'disabled'}. This would result in a lot of manual"
        " choices. Do you want to have the paths be auto-picked instead? This may yield suboptimal"
        " rewards."
    )
    text.setWordWrap(True)
    layout.addWidget(text)
    # Its own line, and quieter than the question: it answers the worry the question raises rather
    # than adding to it.
    note = QLabel("One-time action only — your auto-pick setting will stay untouched.")
    note.setStyleSheet(_MUTED_STAT_STYLE)
    # Unwrapped, so its full width joins the dialog's minimum and it stays one line. Broken across
    # two it reads as a second paragraph rather than as a footnote to the question above it.
    note.setWordWrap(False)
    layout.addWidget(note)
    layout.addSpacing(12)

    chosen = {"auto": False}
    auto_btn = QPushButton("Auto-pick")
    manual_btn = QPushButton("Pick manually")
    for btn in (auto_btn, manual_btn):
        btn.setAutoDefault(False)
        btn.setEnabled(False)
    equalize_button_widths(auto_btn, manual_btn, minimum=90)
    auto_btn.clicked.connect(lambda: (chosen.update(auto=True), d.accept()))
    manual_btn.clicked.connect(d.accept)
    # Manual is the default: it is the answer that changes nothing, and Return should not be able
    # to trade away rewards on a dialog the player did not ask for.
    manual_btn.setAutoDefault(True)
    manual_btn.setDefault(True)

    row = QHBoxLayout()
    row.addStretch()
    row.addWidget(auto_btn)
    row.addWidget(manual_btn)
    layout.addLayout(row)

    def _arm_prompt() -> None:
        _arm([auto_btn, manual_btn])
        try:
            manual_btn.setFocus()
        except RuntimeError:
            pass  # closed before the timer fired
    QTimer.singleShot(_PROMPT_ARM_MS, _arm_prompt)
    exec_dialog(d)
    return chosen["auto"]


# --- The window --------------------------------------------------------------------------------

def build_dungeon_content(
    layout: QVBoxLayout, on_choose: Callable[[int], None], data: dict[str, Any] | None = None
) -> tuple[list[QPushButton], QWidget | None]:
    """
    Fill `layout` with whichever of the four states the save is in.

    Returns the pathway buttons and the row holding them, empty in the three states that offer no
    choice. The caller sizes and arms them once the window is up.
    """
    data = storage.load() if data is None else data
    if not dungeon_mod.is_active(data):
        _add_idle(layout, data)
    elif dungeon_mod.treasure_ready(data):
        _add_treasure(layout, data)
    elif dungeon_mod.pending(data):
        return _add_pending(layout, data, on_choose)
    else:
        _add_venturing(layout, data)
    return [], None


def show_dungeon_dialog(parent: QWidget | None = None, on_refresh: Callable[[], None] | None = None) -> None:
    """
    Open the dungeon in its own window.

    Rebuilt in place rather than reopened, the way the CollectQuest window is, so a setting changed
    here is reflected without the window going away. Taking a pathway is the exception: that closes
    the window instead, since the choice is what it was opened for.
    """
    on_refresh = on_refresh or (lambda: None)
    d = QDialog(parent)
    d.setWindowTitle("CollectQuest — Dungeon")
    d.setMinimumWidth(_MIN_WIDTH)
    outer = QVBoxLayout(d)
    content: QWidget | None = None

    def rebuild(chained: bool = False) -> None:
        nonlocal content
        # Read once and passed down: every helper below wants the same save, and storage.load()
        # decodes and rehashes the whole file each time it is called.
        data = storage.load()
        holder = QWidget()
        inner = QVBoxLayout(holder)
        inner.setSpacing(_ROW_SPACING)
        path_buttons, path_row = build_dungeon_content(inner, _choose, data)
        if chained and path_buttons:
            # Arrived under a cursor that was mid-click on the previous branching.
            for btn in path_buttons:
                btn.setEnabled(False)
            QTimer.singleShot(_CHAIN_ARM_MS, lambda bs=path_buttons: _arm(bs))

        inner.addSpacing(8)
        row = QHBoxLayout()
        row.addStretch()
        auto_btn = _auto_pick_button(d, lambda: (rebuild(), on_refresh()), data)
        auto_btn.setAutoDefault(False)
        # One button, not two: at the treasure there is nothing to do but take it, so the button
        # that closes the window is the one that claims. Closing any other way claims too (below),
        # which is what lets this be a single button rather than a choice between leaving with the
        # treasure and leaving without it.
        close_btn = QPushButton("Claim" if dungeon_mod.treasure_ready(data) else "Close")
        close_btn.clicked.connect(d.accept)
        equalize_button_widths(auto_btn, close_btn, minimum=90)
        row.addWidget(auto_btn)
        row.addWidget(close_btn)
        inner.addLayout(row)

        old, content = content, holder
        if old is not None:
            # Hidden as well as removed: deleteLater only fires once the event loop is reached, and
            # until then the old copy would sit on top of the new one.
            outer.removeWidget(old)
            old.hide()
            old.deleteLater()
        outer.addWidget(holder)
        # After the show below the buttons carry the dialog's font; before it they carry the
        # application's, and sizing to that clipped their labels.

        # Shown by hand, or the sizing below measures an empty window: a widget added to a visible
        # window's layout stays hidden until Qt shows it, and a hidden child adds nothing to
        # sizeHint(). Both passes then fell back to _MIN_WIDTH and clipped the venturing title.
        holder.show()
        _size_path_row(path_buttons, path_row)
        # Close takes the focus and the Return key on every build, as the CollectQuest and prestige
        # windows do: the row is rebuilt from scratch each time, so a rebuild that skipped this
        # would leave whichever button Qt reached first wearing the focus ring.
        close_btn.setDefault(True)
        close_btn.setFocus()
        # Both dimensions from the layout, so a state with fewer rows opens shorter rather than
        # padding itself out to match the tallest, and the venturing state gets the extra width its
        # longer title needs. The deferred pass measures again once the wrapped lines have settled
        # at the width this one chose.
        d.adjustSize()
        QTimer.singleShot(0, lambda: _fit(d))

    def _choose(index: int) -> None:
        data = storage.load()
        # Nothing is paid here: taking a pathway only records the choice, and the treasure it leads
        # to is found by a later review's roll rather than by this click.
        dungeon_mod.choose_path(data, index, auto=False)
        # The reviews answered while this choice sat unanswered are rolled now, so deciding late
        # costs nothing. They can hand back another branching, or the treasure itself.
        review_rewards.apply_dungeon_catch_up(data)
        storage.save(data)
        if dungeon_mod.pending(data) or dungeon_mod.treasure_ready(data):
            # Straight into the next screen: the window is already open on the thing that needs
            # answering, and closing only to be reopened would be a step for nothing.
            rebuild(chained=True)
        else:
            # Closed rather than rebuilt into the venturing state: the choice is the whole reason
            # the window was opened, and the screen behind it only says to keep reviewing.
            d.accept()
        on_refresh()

    def _claim_on_close(_result: int = 0) -> None:
        """
        Take the treasure when the window closes, however it was closed.

        The button, the title bar's X and Escape all end here, so there is no way to leave a
        reached treasure behind - which is the point of having one button rather than a Claim and a
        Close that mean different things. Guarded on treasure_ready, so it is a no-op in every
        other state and cannot pay twice.
        """
        data = storage.load()
        if not dungeon_mod.treasure_ready(data):
            return
        review_rewards.claim_dungeon_treasure(data)
        # Whatever was banked while the treasure went unclaimed now goes to the search for the next
        # entrance, and can find one - the window is closing, so the bottom-bar button is what says
        # so. Deliberately quiet: a claim that opened another window would be a chain nobody asked
        # to be dragged through.
        review_rewards.apply_dungeon_catch_up(data)
        storage.save(data)
        on_refresh()

    d.finished.connect(_claim_on_close)
    rebuild()
    exec_dialog(d)
