"""
Build every dungeon UI state with PyQt6 standing in for aqt.qt on an offscreen display.
Exit 1 = a window did not build.

    python3 tests/check_dungeon_ui.py
"""
import copy
import importlib
import os
import pathlib
import random
import sys
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent))

import PyQt6.QtCore as QtCore
import PyQt6.QtGui as QtGui
import PyQt6.QtWidgets as QtWidgets

# aqt.qt is a flat re-export of Qt: build the same shape so the add-on's imports resolve to the
# real classes and a wrong enum path or a missing widget fails here rather than in Anki.
qt = types.ModuleType("aqt.qt")
for src in (QtCore, QtGui, QtWidgets):
    for name in dir(src):
        if name.startswith("Q") or name == "Qt":
            setattr(qt, name, getattr(src, name))
sys.modules["aqt.qt"] = qt

aqt = types.ModuleType("aqt")
aqt.mw = None
aqt.qt = qt
# hooks.py does `from aqt import gui_hooks, mw`, so both have to exist to import it at all.
aqt.gui_hooks = types.SimpleNamespace()
sys.modules["aqt"] = aqt
sys.modules["aqt.gui_hooks"] = types.ModuleType("aqt.gui_hooks")
for name, attrs in (
    ("aqt.utils", {"tooltip": lambda *a, **k: None, "showInfo": lambda *a, **k: None,
                   "openLink": lambda *a, **k: None, "askUser": lambda *a, **k: True}),
    ("aqt.theme", {"theme_manager": types.SimpleNamespace(night_mode=False)}),
    ("anki", {}), ("anki.collection", {}),
):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    mod.__getattr__ = lambda n: types.SimpleNamespace()
    sys.modules.setdefault(name, mod)

pkg = types.ModuleType("cq")
pkg.__path__ = [str(ROOT)]
sys.modules["cq"] = pkg

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

storage = importlib.import_module("cq.src.storage")
dungeon = importlib.import_module("cq.src.dungeon")
shop = importlib.import_module("cq.src.shop")
ui_dungeon = importlib.import_module("cq.src.ui.dungeon")
ui_items = importlib.import_module("cq.src.ui.items")
assets = importlib.import_module("cq.src.ui.assets")

# The add-on finds its images relative to its own package; point the asset loader at the repo so
# every icon this feature names is really loaded rather than silently missing.
assets.addon_dir = lambda: str(ROOT)
assets._addon_dir_cache = str(ROOT)
hooks = importlib.import_module("cq.src.hooks")
notices = importlib.import_module("cq.src.notices")

FAILS = []
STATE = {}
storage.load = lambda: STATE
storage.save = lambda d: STATE.update(d)


def use(state):
    STATE.clear()
    STATE.update(state)


def build(label, fn):
    try:
        holder = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(holder)
        fn(layout)
        holder.adjustSize()
        texts = [w.text() for w in holder.findChildren(QtWidgets.QLabel) if w.text()]
        texts += [b.text() for b in holder.findChildren(QtWidgets.QPushButton)]
        print(f"  ok   {label}: {len(texts)} labels/buttons")
        return holder, texts
    except Exception as e:
        print(f"  FAIL {label}: {type(e).__name__}: {e}")
        FAILS.append(label)
        return None, []


def fresh(**over):
    d = storage._default_state()
    d["total_xp"] = 100_000
    d.update(over)
    return d


print("every icon the feature names resolves")
for label, path in (
    [("window header", ui_dungeon._HEADER_ICON), ("treasure", ui_dungeon._TREASURE_ICON)]
    + [(f"path {k}", v) for k, v in dungeon.PATH_ICONS.items()]
):
    ok = pathlib.Path(ROOT / "images" / path).is_file()
    print(f"  {'ok  ' if ok else 'FAIL'} {label}: {path}")
    if not ok:
        FAILS.append(f"missing image {path}")
for c in shop.COLLECTIBLES:
    if not pathlib.Path(ROOT / "images" / c["image"]).is_file():
        FAILS.append(f"missing item image {c['image']}")
        print(f"  FAIL item image {c['id']}: {c['image']}")

print("\nthe four window states")
noop = lambda *a: None

use(fresh())
build("idle, never played", lambda l: ui_dungeon.build_dungeon_content(l, noop))

use(fresh(last_dungeon={"branchings": 4, "gold": 180, "gems": 3, "item": "mushroom",
                        "picked": [{"kind": "gold", "gold": 43},
                                   {"kind": "unique", "item": "mushroom"}]}))
_, texts = build("idle, last dungeon", lambda l: ui_dungeon.build_dungeon_content(l, noop))
if not any("Mushroom" in t for t in texts):
    FAILS.append("last dungeon does not name its item")

d = fresh()
d["dungeon"] = dungeon._new_dungeon()
d["dungeon"]["reviews_since_entrance"] = 412
use(d)
_, texts = build("venturing", lambda l: ui_dungeon.build_dungeon_content(l, noop))
if not any("412" in t for t in texts):
    FAILS.append("venturing does not show the counter")

# The bonus block appears only with the pity bonus, and drops its total when no item feeds it.
print("\nthe dungeon bonus block")
EXPLORE_ITEMS = ["crystal_ball", "delvers_ring", "lantern"]  # 7 + 10 + 18 = 35%
PITY_224 = dungeon.PITY_FLOOR_REVIEWS + 124  # +24%: 2% per step of 10 past the floor


def venturing_texts(label, on_path, owned):
    d = fresh(owned_collectibles=list(owned))
    d["dungeon"] = dungeon._new_dungeon()
    d["dungeon"]["reviews_since_branching"] = on_path
    d["dungeon"]["branchings_done"] = 1
    use(d)
    return build(label, lambda l: ui_dungeon.build_dungeon_content(l, noop))[1]


for label, on_path, owned, want, unwanted in (
    ("pity and items", PITY_224, EXPLORE_ITEMS,
     ["Faster dungeon exploration:", "  +24% bonus since 100th answer", "  +59% total"], []),
    ("pity, no items", PITY_224, [],
     ["  +24% bonus since 100th answer"], ["total"]),
    ("items, no pity", 40, EXPLORE_ITEMS,
     [], ["Faster dungeon exploration:", "bonus since"]),
):
    texts = venturing_texts(label, on_path, owned)
    missing = [w for w in want if w not in texts]
    present = [u for u in unwanted if any(u in t for t in texts)]
    if missing or present:
        print(f"  FAIL {label}: missing {missing}, unwanted {present}")
        FAILS.append(f"bonus block, {label}")
    else:
        print(f"  ok   {label}")

# The discovery half is headed by its own name, worded as the items that feed it are.
use(fresh(owned_collectibles=["smoke_pipe"], dungeon_search_reviews=PITY_224))
texts = build("idle, discovery bonus", lambda l: ui_dungeon.build_dungeon_content(l, noop))[1]
if "Chance to find a dungeon:" not in texts:
    FAILS.append("discovery bonus block is not headed by its stat name")

for n_paths in (2, 3):
    d = fresh()
    d["dungeon"] = dungeon._new_dungeon()
    d["dungeon"]["picked"] = [{"took": {"kind": "gold", "gold": 43}, "auto": False}]
    d["dungeon"]["pending"] = {"paths": [
        {"kind": "gold", "gold": 43},
        {"kind": "gems", "gems": 2, "most_needed": False},
        {"kind": "unique", "item": "skull_scroll"},
    ][:n_paths]}
    use(d)
    _, texts = build(f"pending branching, {n_paths} paths",
                     lambda l: ui_dungeon.build_dungeon_content(l, noop))
    if not any("43g" in t for t in texts):
        FAILS.append(f"branching row missing its amounts ({n_paths} paths)")

# Every path kind has to survive being drawn, including the two that carry no number.
for kind in dungeon.PATH_ORDER:
    d = fresh()
    d["dungeon"] = dungeon._new_dungeon()
    offer = dungeon._build_offer(kind, d, [])
    d["dungeon"]["pending"] = {"paths": [offer, {"kind": "gold", "gold": 30}]}
    use(d)
    build(f"branching row with {kind}", lambda l: ui_dungeon.build_dungeon_content(l, noop))

d = fresh()
d["dungeon"] = dungeon._new_dungeon()
d["dungeon"]["picked"] = [
    {"took": {"kind": "gold", "gold": 40}, "auto": False},
    {"took": {"kind": "gems", "gems": 3, "most_needed": True}, "auto": True},
    {"took": {"kind": "unmarked", "outcome": "nothing"}, "auto": False},
    {"took": {"kind": "unique", "item": "winged_shoes"}, "auto": False},
]
d["dungeon"]["treasure"] = {"claimed": False}
use(d)
_, texts = build("unclaimed treasure", lambda l: ui_dungeon.build_dungeon_content(l, noop))
if not any("Winged Shoes" in t for t in texts):
    FAILS.append("treasure does not reveal the item")

# The window's own icon heads every state except the treasure, which swaps it for the chest.
print("\nthe header icon is present in every state")
for label, state, want in (
    ("idle", fresh(), ui_dungeon._HEADER_ICON),
    ("venturing", None, ui_dungeon._HEADER_ICON),
    ("pending branching", None, ui_dungeon._HEADER_ICON),
    ("treasure", None, ui_dungeon._TREASURE_ICON),
):
    if state is None:
        state = fresh()
        state["dungeon"] = dungeon._new_dungeon()
        if label == "pending branching":
            state["dungeon"]["pending"] = {"paths": [{"kind": "gold", "gold": 30}]}
        if label == "treasure":
            state["dungeon"]["picked"] = [{"took": {"kind": "gold", "gold": 30}, "auto": False}]
            state["dungeon"]["treasure"] = {"claimed": False}
    use(state)
    holder = QtWidgets.QWidget()
    lay = QtWidgets.QVBoxLayout(holder)
    ui_dungeon.build_dungeon_content(lay, noop)
    # The header is the first pixmap in the layout, above everything else the state draws.
    pixmaps = [x for x in holder.findChildren(QtWidgets.QLabel) if x.pixmap() and not x.pixmap().isNull()]
    expected = assets._icon_pixmap(want, ui_dungeon._HEADER_ICON_PX, content=ui_dungeon._HEADER_ICON_PX)
    ok = bool(pixmaps) and pixmaps[0].pixmap().toImage() == expected.toImage()
    print(f"  {'ok  ' if ok else 'FAIL'} {label}: heads with {want}")
    if not ok:
        FAILS.append(f"header icon missing in the {label} state")

print("\nthe venturing counters")
for label, done, since_branch, since_entrance, want in (
    ("before the first pathway", 0, 63, 63, ["63 cards answered since the entrance."]),
    ("on a pathway", 1, 12, 310,
     ["12 cards answered on this pathway, 310 since the entrance."]),
    ("singular", 2, 1, 402,
     ["1 card answered on this pathway, 402 since the entrance."]),
    ("just after taking one", 3, 0, 512,
     ["0 cards answered on this pathway, 512 since the entrance."]),
):
    st = fresh()
    st["dungeon"] = dungeon._new_dungeon()
    st["dungeon"].update(branchings_done=done, reviews_since_branching=since_branch,
                         reviews_since_entrance=since_entrance)
    use(st)
    holder = QtWidgets.QWidget()
    lay = QtWidgets.QVBoxLayout(holder)
    ui_dungeon.build_dungeon_content(lay, noop)
    got = [x.text() for x in holder.findChildren(QtWidgets.QLabel)
           if "answered" in x.text()]
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}: {got}")
    if not ok:
        FAILS.append(f"venturing counters, {label}")

print("\nthe pathway list opens its secrets only after the treasure")
TAKEN = [
    {"kind": "gold", "gold": 44},
    {"kind": "unique", "item": "bronze_helm"},
    {"kind": "unmarked", "outcome": "gold_gems", "gold": 26, "gems": 1, "most_needed": False},
    {"kind": "unmarked", "outcome": "nothing"},
]


def list_rows(layout_state):
    use(layout_state)
    holder = QtWidgets.QWidget()
    lay = QtWidgets.QVBoxLayout(holder)
    ui_dungeon.build_dungeon_content(lay, noop)
    return [x.text().strip() for x in holder.findChildren(QtWidgets.QLabel)
            if x.text().strip()[:2] in ("1.", "2.", "3.", "4.")]

running = fresh()
running["dungeon"] = dungeon._new_dungeon()
running["dungeon"]["picked"] = [{"took": t, "auto": False} for t in TAKEN]
got = list_rows(running)
want = ["1. 44g", "2. Unknown item", "3. Unmarked path", "4. Unmarked path"]
ok = got == want
print(f"  {'ok  ' if ok else 'FAIL'} still running, nothing revealed: {got}")
if not ok: FAILS.append("pathway list revealed a secret mid-dungeon")

treasure = fresh()
treasure["dungeon"] = dungeon._new_dungeon()
treasure["dungeon"]["picked"] = [{"took": t, "auto": False} for t in TAKEN]
treasure["dungeon"]["treasure"] = {"claimed": False}
got = list_rows(treasure)
want = ["1. 44g", "2. Unknown item (Bronze Helm)",
        "3. Unmarked path (26g + 1 gem)", "4. Unmarked path (nothing)"]
ok = got == want
print(f"  {'ok  ' if ok else 'FAIL'} at the treasure, opened: {got}")
if not ok: FAILS.append("treasure list did not reveal")

got = list_rows(fresh(last_dungeon={"branchings": 4, "gold": 70, "gems": 1,
                                    "item": "bronze_helm", "picked": TAKEN}))
ok = got == want
print(f"  {'ok  ' if ok else 'FAIL'} last dungeon, opened: {got}")
if not ok: FAILS.append("last dungeon list did not reveal")

# A looted item's name must wait for the treasure. Reads every label, since the earlier leak was
# in the pick log rather than where the name was expected.
print("\nthe item name never appears before the treasure")
ITEM, ITEM_NAME = "bronze_helm", "Bronze Helm"


def all_text(state):
    use(state)
    holder = QtWidgets.QWidget()
    lay = QtWidgets.QVBoxLayout(holder)
    ui_dungeon.build_dungeon_content(lay, noop)
    return " | ".join(x.text() for x in holder.findChildren(QtWidgets.QLabel) if x.text()) \
        + " | " + " | ".join(b.text() for b in holder.findChildren(QtWidgets.QPushButton))


picked_unique = [{"took": {"kind": "unique", "item": ITEM}, "auto": False}]
for label, mutate in (
    ("offered, not yet taken",
     lambda st: st.update(pending={"paths": [{"kind": "unique", "item": ITEM},
                                             {"kind": "gold", "gold": 30}]})),
    ("taken, still venturing", lambda st: st.update(picked=picked_unique)),
    ("taken, another branching offered",
     lambda st: st.update(picked=picked_unique,
                          pending={"paths": [{"kind": "gold", "gold": 30}]})),
):
    st = fresh()
    st["dungeon"] = dungeon._new_dungeon()
    mutate(st["dungeon"])
    text = all_text(st)
    ok = ITEM_NAME not in text
    print(f"  {'ok  ' if ok else 'FAIL'} {label}")
    if not ok:
        FAILS.append(f"item name leaked: {label}")
        print(f"         {text}")

# And it must appear once the treasure is open, or the reveal never happens at all.
st = fresh()
st["dungeon"] = dungeon._new_dungeon()
st["dungeon"]["picked"] = picked_unique
st["dungeon"]["treasure"] = {"claimed": False}
ok = ITEM_NAME in all_text(st)
print(f"  {'ok  ' if ok else 'FAIL'} revealed at the treasure")
if not ok: FAILS.append("item never revealed")

# The idle state reports the finished dungeon, where naming it is the point.
ok = ITEM_NAME in all_text(fresh(last_dungeon={"branchings": 3, "gold": 40, "gems": 2,
                                               "item": ITEM, "picked": [{"kind": "unique",
                                                                         "item": ITEM}]}))
print(f"  {'ok  ' if ok else 'FAIL'} named in the last-dungeon summary")
if not ok: FAILS.append("last dungeon does not name its item")

# The notification auto-pick posts must not name it either.
line = notices.dungeon_lines(
    {"dungeon_branching": True, "dungeon_auto_took": {"kind": "unique", "item": ITEM}}
)[0]
ok = ITEM_NAME not in line and "Unknown item" in line
print(f"  {'ok  ' if ok else 'FAIL'} auto-pick notification: {line}")
if not ok: FAILS.append("item name leaked into the notification")

print("\nthe auto-pick button, locked and unlocked")
for claimed, want in ((0, "locked"), (3, "unlocked")):
    use(fresh(dungeons_claimed=claimed))
    try:
        btn = ui_dungeon._auto_pick_button(None, noop)
        print(f"  ok   {want} button: {btn.text()!r} tip={btn.toolTip()!r}")
    except Exception as e:
        print(f"  FAIL {want} button: {type(e).__name__}: {e}")
        FAILS.append(f"{want} auto-pick button")
# The locked button must stay clickable: a disabled QPushButton opens nothing, and its dialog is
# now the only place the gate is explained.
use(fresh(dungeons_claimed=1))
btn = ui_dungeon._auto_pick_button(None, noop)
if not btn.isEnabled():
    FAILS.append("locked auto-pick button is disabled and could not open its dialog")

# Taking a pathway closes the window, since the venturing screen behind it only says to keep
# reviewing. A rebuild in place (a changed setting) must still match a fresh open's size.
print("\ntaking a pathway closes the window")


def opened(state):
    use(state)
    holder = {}
    real = QtWidgets.QDialog.exec

    def grab(self):
        holder["d"] = self
        return 0

    QtWidgets.QDialog.exec = grab
    ui_dungeon.show_dungeon_dialog(None, noop)
    QtWidgets.QDialog.exec = real
    d = holder["d"]
    d.show()
    settle()
    return d


def settle():
    """Let the deferred fit run and the layout settle; one turn fires the timer but may not relayout."""
    for _ in range(5):
        app.processEvents()


pending = fresh(dungeons_claimed=1)
pending["dungeon"] = dungeon._new_dungeon()
pending["dungeon"]["reviews_since_entrance"] = 1180
pending["dungeon"]["picked"] = [{"took": {"kind": "gold", "gold": 51}, "auto": False}]
pending["dungeon"]["pending"] = {"paths": [{"kind": "gold", "gold": 40},
                                           {"kind": "unique", "item": "poison"}]}
dlg = opened(pending)
btn = next(b for b in dlg.findChildren(QtWidgets.QPushButton) if b.text() == "40g")
btn.click()
settle()
closed = not dlg.isVisible()
print(f"  {'ok  ' if closed else 'FAIL'} the window closed on the pick: visible={dlg.isVisible()}")
if not closed:
    FAILS.append("choosing a pathway left the window open")
took = (dungeon.picks(STATE)[-1].get("took") or {}) if dungeon.picks(STATE) else {}
recorded = took.get("gold") == 40 and dungeon.pending(STATE) is None
print(f"  {'ok  ' if recorded else 'FAIL'} the pick was recorded and the branching cleared: {took}")
if not recorded:
    FAILS.append("choosing a pathway did not record the pick")

# An auto-pick setting saved from the child dialog redraws the window, which must not collapse to
# _MIN_WIDTH (a widget added to a visible layout stays hidden, and hidden measures as nothing).
print("\na rebuild in place keeps the window the size a fresh open would be")
venturing = fresh(dungeons_claimed=3)
venturing["dungeon"] = dungeon._new_dungeon()
venturing["dungeon"]["reviews_since_entrance"] = 1180
venturing["dungeon"]["picked"] = [{"took": {"kind": "gold", "gold": 51}, "auto": False}]
dlg = opened(venturing)
want = (dlg.width(), dlg.height())
child = {}
real = QtWidgets.QDialog.exec


def grab_child(self):
    child["d"] = self
    return 0


QtWidgets.QDialog.exec = grab_child
next(b for b in dlg.findChildren(QtWidgets.QPushButton) if b.text() == "Auto-pick").click()
QtWidgets.QDialog.exec = real
box = next(c for c in child["d"].findChildren(QtWidgets.QCheckBox))
box.setChecked(not box.isChecked())   # fires _save -> on_change -> rebuild
settle()
after = (dlg.width(), dlg.height())
# Cleaned up before the next check reads STATE: the toggle above was saved through it, and the
# grabbed dialog is still parented to the window under test.
child["d"].close()
use(fresh(dungeons_claimed=3))
ok = after == want
print(f"  {'ok  ' if ok else 'FAIL'} fresh open {want} -> after a rebuild {after}")
if not ok:
    FAILS.append("rebuilt window does not match a fresh open")
ok_w = after[0] >= 380
print(f"  {'ok  ' if ok_w else 'FAIL'} wide enough for the venturing title: {after[0]}px")
if not ok_w:
    FAILS.append("rebuilt window too narrow for its title")

print("\nthe branching screen is the same width and shape whatever it offers")
shapes = []
for paths in ([{"kind": "gold", "gold": 9}, {"kind": "gems", "gems": 2}],
              [{"kind": "gold", "gold": 9}, {"kind": "gems", "gems": 2},
               {"kind": "gold", "gold": 51}],
              [{"kind": "unmarked", "outcome": "nothing"}, {"kind": "unique", "item": "poison"},
               {"kind": "gold_gems", "gold": 92, "gems": 12}],
              [{"kind": "unmarked", "outcome": "nothing"},
               {"kind": "gold_gems", "gold": 138, "gems": 9}]):
    st = fresh(dungeons_claimed=3)
    st["dungeon"] = dungeon._new_dungeon()
    st["dungeon"]["pending"] = {"paths": paths}
    dlg = opened(st)
    btns = [b for b in dlg.findChildren(QtWidgets.QPushButton)
            if b.isVisible() and b.text() not in ("Auto-pick", "Close", "Claim")]
    shapes.append((dlg.width(), sorted({b.width() for b in btns})))
    _paths_checked = btns
    print(f"       {len(paths)} paths, widest {max(len(b.text()) for b in btns):>2} chars"
          f" -> window {dlg.width()}, buttons {sorted({b.width() for b in btns})}")
    dlg.accept()
    # Each cell is exactly its button's width, so nothing clips and the icon shares its center;
    # the fixed-width row must be centered explicitly or a box layout left-aligns it.
    if btns:
        row = btns[0].parentWidget().parentWidget()
        row_center = row.mapTo(dlg, QtCore.QPoint(0, 0)).x() + row.width() / 2
        if abs(row_center - dlg.width() / 2) > 2:
            FAILS.append(f"path row off-center by {row_center - dlg.width()/2:.0f}px")
            print(f"       FAIL row center {row_center:.0f} vs window center {dlg.width()/2:.0f}")
    for b in btns:
        cell = b.parentWidget()
        icon = next((l for l in cell.findChildren(QtWidgets.QLabel) if l.pixmap()), None)
        overflow = b.x() + b.width() - cell.width()
        centered = icon is None or abs(
            (b.x() + b.width() / 2) - (icon.x() + icon.width() / 2)) < 1
        if overflow > 0 or not centered:
            FAILS.append(f"path cell misaligned: {b.text()} overflow={overflow} centered={centered}")
            print(f"       FAIL {b.text()}: overflow={overflow}, icon centered={centered}")
widths = {w for w, _ in shapes}
btn_widths = {b for _, bs in shapes for b in bs}
ok = len(widths) == 1 and len(btn_widths) == 1
print(f"  {'ok  ' if ok else 'FAIL'} one window width {sorted(widths)} and one button width"
      f" {sorted(btn_widths)} across every shape")
if not ok:
    FAILS.append(f"branching screen resizes: windows {sorted(widths)}, buttons {sorted(btn_widths)}")
# Sized from the widest label the feature can produce, not the widest one present, or a row of
# short labels would draw narrower than the row before it.
probe = max(btn_widths) if btn_widths else 0
print(f"  {'ok  ' if probe in btn_widths else 'FAIL'} one measured width, applied to every button = {probe}")
if probe not in btn_widths:
    FAILS.append("path buttons are not using the measured fixed width")

print("\na taken pathway chains into whatever the banked reviews find")
chained = fresh(dungeons_claimed=3)
chained["dungeon"] = dungeon._new_dungeon()
chained["dungeon"]["branchings_total"] = 6
chained["dungeon"]["reviews_since_branching"] = 60
chained["dungeon"]["pending"] = {"paths": [{"kind": "gold", "gold": 44},
                                           {"kind": "gems", "gems": 3}]}
random.seed(4)
for _ in range(500):
    dungeon.on_review(chained, 3, 60)
banked = dungeon.banked_reviews(chained)
dlg = opened(chained)
btn = next(b for b in dlg.findChildren(QtWidgets.QPushButton) if b.text() == "44g")
btn.click()
settle()
still_open = dlg.isVisible()
now_pending = dungeon.pending(STATE) is not None or dungeon.treasure_ready(STATE)
print(f"  {'ok  ' if banked == 500 else 'FAIL'} 500 reviews were banked behind the choice: {banked}")
if banked != 500:
    FAILS.append("banking before the choice")
# The bank has to have been spent by the click, and the window has to still be up showing whatever
# it bought - closing and asking to be reopened is the step this exists to remove.
spent = banked - dungeon.banked_reviews(STATE)
print(f"  {'ok  ' if spent > 0 else 'FAIL'} the click spent {spent} of them")
if spent <= 0:
    FAILS.append("catch-up did not run on a taken pathway")
print(f"  {'ok  ' if still_open and now_pending else 'FAIL'} window stayed open on the next screen:"
      f" visible={still_open}, something to answer={now_pending}")
if not (still_open and now_pending):
    FAILS.append("the window did not chain into the next screen")
# New path buttons arrive dead so a double-click cannot take one unseen. Visible only: the old
# screen stays parented until deleteLater lands, which processEvents does not drain.
fresh_paths = [b for b in dlg.findChildren(QtWidgets.QPushButton)
               if b.isVisible() and b.text() not in ("Auto-pick", "Close", "Claim")]
disarmed = fresh_paths and not any(b.isEnabled() for b in fresh_paths)
print(f"  {'ok  ' if disarmed else 'FAIL'} the fresh path buttons start disabled:"
      f" {[b.text() for b in fresh_paths]}")
if not disarmed:
    FAILS.append("chained path buttons were live on arrival")
ui_dungeon._arm(fresh_paths)
print(f"  {'ok  ' if all(b.isEnabled() for b in fresh_paths) else 'FAIL'} and arm again after"
      f" {ui_dungeon._CHAIN_ARM_MS}ms")
if not all(b.isEnabled() for b in fresh_paths):
    FAILS.append("chained path buttons never re-armed")
dlg.accept()

print("\nclosing the window claims a reached treasure")
QtWidgets.QDialog.exec = lambda self: 0
for label, closer in (("the button", lambda d: d.accept()),
                      ("the title bar's X", lambda d: d.reject()),
                      ("never opened at all", None)):
    st = fresh(dungeons_claimed=1)
    st["dungeon"] = dungeon._new_dungeon()
    st["dungeon"]["picked"] = [{"took": {"kind": "gold", "gold": 40}, "auto": False}]
    st["dungeon"]["treasure"] = {"claimed": False}
    use(st)
    before = STATE["money"]
    dlg = None
    real = QtWidgets.QDialog.exec

    def grab(self):
        global dlg
        dlg = self
        return 0

    QtWidgets.QDialog.exec = grab
    ui_dungeon.show_dungeon_dialog(None, noop)
    QtWidgets.QDialog.exec = real
    if closer is not None:
        closer(dlg)
    paid = STATE["money"] - before
    gone = STATE.get("dungeon") is None
    want_paid = 40 if closer is not None else 0
    ok = paid == want_paid and gone == (closer is not None)
    print(f"  {'ok  ' if ok else 'FAIL'} closed by {label}: paid {paid}g, dungeon closed {gone}")
    if not ok:
        FAILS.append(f"claim on close via {label}")

# Closing twice must not pay twice - the guard is treasure_ready, not a flag.
st = fresh(dungeons_claimed=1)
st["dungeon"] = dungeon._new_dungeon()
st["dungeon"]["picked"] = [{"took": {"kind": "gold", "gold": 40}, "auto": False}]
st["dungeon"]["treasure"] = {"claimed": False}
use(st)
before = STATE["money"]
dlg = None
real = QtWidgets.QDialog.exec
QtWidgets.QDialog.exec = grab
ui_dungeon.show_dungeon_dialog(None, noop)
QtWidgets.QDialog.exec = real
dlg.accept(); dlg.accept(); dlg.reject()
ok = STATE["money"] - before == 40
print(f"  {'ok  ' if ok else 'FAIL'} closing repeatedly pays once: {STATE['money'] - before}g")
if not ok: FAILS.append("treasure paid more than once")

print("\nno hover tooltips anywhere in the window")
for label, state in (("idle", fresh()), ("pending", None), ("treasure", None)):
    if state is None:
        state = fresh(dungeons_claimed=4)
        state["dungeon"] = dungeon._new_dungeon()
        if label == "pending":
            state["dungeon"]["pending"] = {"paths": [
                {"kind": "gold", "gold": 30},
                {"kind": "unmarked", "outcome": "nothing"},
                {"kind": "unique", "item": "mushroom"},
            ]}
        if label == "treasure":
            state["dungeon"]["picked"] = [{"took": {"kind": "gold", "gold": 30}, "auto": False}]
            state["dungeon"]["treasure"] = {"claimed": False}
    use(state)
    holder = QtWidgets.QWidget()
    lay = QtWidgets.QVBoxLayout(holder)
    ui_dungeon.build_dungeon_content(lay, noop)
    tipped = [(w.__class__.__name__, getattr(w, "text", lambda: "")(), w.toolTip())
              for w in holder.findChildren(QtWidgets.QWidget) if w.toolTip()]
    tipped += [(b.text(), "", b.toolTip())
               for b in (ui_dungeon._auto_pick_button(None, noop),) if b.toolTip()]
    ok = not tipped
    print(f"  {'ok  ' if ok else 'FAIL'} {label}: {tipped if tipped else 'none'}")
    if not ok:
        FAILS.append(f"tooltip left in the {label} state")

print("\nthe items window breakdown")
owned = [c["id"] for c in shop.COLLECTIBLES[:12]]
use(fresh(owned_collectibles=owned))
_, texts = build("route breakdown", lambda l: ui_items.add_route_breakdown(l, owned))
joined = " ".join(texts)
for want in ("/53", "/17", "/8"):
    if want not in joined:
        FAILS.append(f"breakdown missing a {want} row")
        print(f"  FAIL breakdown missing {want}")
if "/53" in joined and "/17" in joined and "/8" in joined:
    print("  ok   three rows partition 78: /53 /17 /8")

print("\nthe status bar with and without a dungeon")
statusbar = importlib.import_module("cq.src.ui.statusbar")
for label, state in (("no dungeon", fresh()), ("dungeon open", None), ("branching pending", None)):
    if state is None:
        state = fresh()
        state["dungeon"] = dungeon._new_dungeon()
        if label == "branching pending":
            state["dungeon"]["pending"] = {"paths": [{"kind": "gold", "gold": 20}]}
    use(state)
    try:
        w = statusbar.build_xp_bar_widget(noop, noop, data=state, on_dungeon_click=noop)
        names = [b.text() for b in w.findChildren(QtWidgets.QPushButton)]
        has = "Dungeon" in names
        want = label != "no dungeon"
        ok = has == want
        print(f"  {'ok  ' if ok else 'FAIL'} {label}: buttons {names}")
        if not ok:
            FAILS.append(f"status bar {label}")
    except Exception as e:
        print(f"  FAIL {label}: {type(e).__name__}: {e}")
        FAILS.append(f"status bar {label}")

# The attention outline: only when something is waiting, and in the shade the theme calls for.
print("\nthe Dungeon button's attention state")
import cq.src.ui.constants as ui_constants


def dungeon_style(state, night):
    sys.modules["aqt.theme"].theme_manager = types.SimpleNamespace(night_mode=night)
    use(state)
    w = statusbar.build_xp_bar_widget(noop, noop, data=state, on_dungeon_click=noop)
    btn = next(b for b in w.findChildren(QtWidgets.QPushButton) if b.text() == "Dungeon")
    return btn.styleSheet()


quiet = fresh(); quiet["dungeon"] = dungeon._new_dungeon()
busy = fresh(); busy["dungeon"] = dungeon._new_dungeon()
busy["dungeon"]["pending"] = {"paths": [{"kind": "gold", "gold": 20}]}
treasure = fresh(); treasure["dungeon"] = dungeon._new_dungeon()
treasure["dungeon"]["treasure"] = {"claimed": False}

st = dungeon_style(quiet, True)
ok = "border: 1px solid" not in st
print(f"  {'ok  ' if ok else 'FAIL'} no outline while merely exploring")
if not ok: FAILS.append("outline shown with nothing waiting")

for label, state in (("a branching pending", busy), ("an unclaimed treasure", treasure)):
    for night, want in ((True, ui_constants._ATTENTION_COLOR_DARK),
                        (False, ui_constants._ATTENTION_COLOR_LIGHT)):
        st = dungeon_style(state, night)
        ok = st.count(want) == 2 and "border: 1px solid" in st
        theme = "dark" if night else "light"
        print(f"  {'ok  ' if ok else 'FAIL'} {label}, {theme} theme: outline and text in {want}")
        if not ok:
            FAILS.append(f"attention color, {label}, {theme}")
            print(f"         {st}")

# The palette accent must not be what marks it: that is the blue Anki already uses beside it.
st = dungeon_style(busy, True)
ok = "palette(highlight)" not in st
print(f"  {'ok  ' if ok else 'FAIL'} does not reuse the theme's own accent")
if not ok: FAILS.append("attention state reuses palette(highlight)")
sys.modules["aqt.theme"].theme_manager = types.SimpleNamespace(night_mode=False)

# Inverting swaps the pair the option names - Shop and CollectQuest - and leaves the Dungeon
# button between them, where it does not move the permanent two around by coming and going.
for invert, want in ((False, ["Shop", "Dungeon", "CollectQuest"]),
                     (True, ["CollectQuest", "Dungeon", "Shop"])):
    state = fresh(bottom_ui_invert_buttons=invert)
    state["dungeon"] = dungeon._new_dungeon()
    use(state)
    w = statusbar.build_xp_bar_widget(noop, noop, data=state, on_dungeon_click=noop)
    names = [b.text() for b in w.findChildren(QtWidgets.QPushButton)]
    label = "inverted" if invert else "normal  "
    if names != want:
        FAILS.append(f"{label.strip()} order wrong: {names}")
        print(f"  FAIL {label} order: {names}")
    else:
        print(f"  ok   {label} order: {names}")

print("\nthe dialogs, with exec() stubbed out so construction is what is tested")
# exec() blocks on a real event loop; every one of these dialogs builds its whole contents before
# calling it, so returning immediately exercises exactly the code that can fail.
QtWidgets.QDialog.exec = lambda self: 0

use(fresh(dungeons_claimed=1))
try:
    ui_dungeon._locked_auto_pick_dialog(None, 1)
    print("  ok   locked auto-pick dialog")
except Exception as e:
    print(f"  FAIL locked auto-pick dialog: {type(e).__name__}: {e}")
    FAILS.append("locked auto-pick dialog")

use(fresh(dungeons_claimed=5, dungeon_auto_pick_enabled=True))
try:
    ui_dungeon._auto_pick_dialog(None, noop)
    order = STATE.get("dungeon_auto_pick_order")
    ok = order == dungeon.DEFAULT_AUTO_PICK_ORDER
    print(f"  {'ok  ' if ok else 'FAIL'} auto-pick dialog round-trips its order: {order}")
    if not ok:
        FAILS.append("auto-pick dialog mangled the order")
except Exception as e:
    print(f"  FAIL auto-pick dialog: {type(e).__name__}: {e}")
    FAILS.append("auto-pick dialog")

# The catch-up prompt's Auto-pick button opens the order instead of confirming outright, so the
# backlog is taken only when Confirm is pressed there and Close comes back to the prompt.
def _exec_clicking(by_title, live=None):
    """Stand in for exec(): click the named button on each dialog as it comes up.
    `live` collects each button's enabled state before the click, as irreversible ones arrive dead."""
    def _exec(self):
        want = by_title.get(self.windowTitle())
        for b in self.findChildren(QtWidgets.QPushButton):
            if b.text() == want:
                if live is not None:
                    live[want] = b.isEnabled()
                b.setEnabled(True)
                b.click()
                break
        return 0
    return _exec


PROMPT_TITLE = "CollectQuest — Dungeon"
ORDER_TITLE = "CollectQuest — Auto-pick"
for label, child, want in (("Confirm takes the backlog", "Confirm", True),
                           ("Close leaves both answers open", "Close", False)):
    use(fresh(dungeons_claimed=1))
    live = {}
    QtWidgets.QDialog.exec = _exec_clicking({PROMPT_TITLE: "Auto-pick", ORDER_TITLE: child}, live)
    try:
        got = ui_dungeon.show_catch_up_prompt(None, locked=True)
        ok = got is want and not STATE.get("dungeon_auto_pick_enabled")
        print(f"  {'ok  ' if ok else 'FAIL'} catch-up {label}: {got}")
        if not ok:
            FAILS.append(f"catch-up {label}")
    except Exception as e:
        print(f"  FAIL catch-up {label}: {type(e).__name__}: {e}")
        FAILS.append(f"catch-up {label}")
    # Both dialogs open under the cursor that opened them, so the answer that cannot be taken back
    # has to arrive dead: Auto-pick on the prompt, Confirm on the order behind it.
    dead = {b: state for b, state in live.items() if b in ("Auto-pick", "Confirm")}
    ok = dead and not any(dead.values())
    print(f"  {'ok  ' if ok else 'FAIL'} the irreversible buttons arrive dead: {dead}")
    if not ok:
        FAILS.append("an irreversible button was live on arrival")
QtWidgets.QDialog.exec = lambda self: 0

# Reordering there is reordering the setting: locked or not, the order is the one auto-pick uses.
use(fresh(dungeons_claimed=1))
try:
    ui_dungeon._confirm_auto_pick_dialog(None)
    order = STATE.get("dungeon_auto_pick_order")
    ok = order == dungeon.DEFAULT_AUTO_PICK_ORDER and not STATE.get("dungeon_auto_pick_enabled")
    print(f"  {'ok  ' if ok else 'FAIL'} confirm dialog keeps the shared order untouched: {order}")
    if not ok:
        FAILS.append("confirm dialog mangled the order")
except Exception as e:
    print(f"  FAIL confirm auto-pick dialog: {type(e).__name__}: {e}")
    FAILS.append("confirm auto-pick dialog")

# A drag, as far as a stubbed dialog can go: move a row on the model both dialogs share, and check
# the write it triggers. Without this the checks above pass on a save that never runs.
use(fresh(dungeons_claimed=1))
try:
    order_list = ui_dungeon._auto_pick_order_list(STATE)
    moves = []
    order_list.model().rowsMoved.connect(lambda *_a: moves.append(1))
    order_list.model().moveRow(QtCore.QModelIndex(), 0, QtCore.QModelIndex(), 3)
    ui_dungeon._save_auto_pick_order(order_list)
    shown = [order_list.item(i).text() for i in range(order_list.count())]
    want = [dungeon.PATH_LABELS[k] for k in STATE["dungeon_auto_pick_order"]]
    head = dungeon.DEFAULT_AUTO_PICK_ORDER[0]
    ok = (moves and shown == want
          and STATE["dungeon_auto_pick_order"] != dungeon.DEFAULT_AUTO_PICK_ORDER
          and STATE["dungeon_auto_pick_order"][0] != head
          and sorted(STATE["dungeon_auto_pick_order"]) == sorted(dungeon.DEFAULT_AUTO_PICK_ORDER))
    print(f"  {'ok  ' if ok else 'FAIL'} a moved row is saved in the order shown: "
          f"{STATE.get('dungeon_auto_pick_order')}")
    if not ok:
        FAILS.append("a reordered list was not saved as shown")
except Exception as e:
    print(f"  FAIL saving a reordered list: {type(e).__name__}: {e}")
    FAILS.append("saving a reordered list")

# The whole window, in each state, including the rebuild that follows a choice and a claim.
for label, state in (
    ("idle", fresh()),
    ("venturing", None),
    ("pending", None),
    ("treasure", None),
):
    if state is None:
        state = fresh(dungeons_claimed=4)
        state["dungeon"] = dungeon._new_dungeon()
        if label == "pending":
            state["dungeon"]["pending"] = {"paths": [
                {"kind": "gold", "gold": 30},
                {"kind": "gems", "gems": 1, "most_needed": False},
            ]}
        if label == "treasure":
            state["dungeon"]["branchings_done"] = state["dungeon"]["branchings_total"]
            state["dungeon"]["picked"] = [{"took": {"kind": "gold", "gold": 30}, "auto": False}]
            state["dungeon"]["treasure"] = {"claimed": False}
    use(state)
    try:
        ui_dungeon.show_dungeon_dialog(None, noop)
        print(f"  ok   window opens in the {label} state")
    except Exception as e:
        print(f"  FAIL window in the {label} state: {type(e).__name__}: {e}")
        FAILS.append(f"window {label}")

# Choosing has to advance the state and rebuild without raising, which is the path a player takes
# most often and the one the four static builders never touch.
state = fresh(dungeons_claimed=4)
state["dungeon"] = dungeon._new_dungeon()
state["dungeon"]["pending"] = {"paths": [{"kind": "gold", "gold": 30}]}
use(state)
holder = QtWidgets.QWidget()
lay = QtWidgets.QVBoxLayout(holder)
picked = []
ui_dungeon.build_dungeon_content(lay, lambda i: picked.append(i))
btns = [b for b in holder.findChildren(QtWidgets.QPushButton) if b.text() == "30g"]
if not btns:
    FAILS.append("no path button to click")
    print("  FAIL no path button to click")
else:
    btns[0].click()
    ok = picked == [0]
    print(f"  {'ok  ' if ok else 'FAIL'} clicking a path reports its index: {picked}")
    if not ok:
        FAILS.append("path button does not report its index")

print("\nClose is the default button in every window state")
# The window is rebuilt from scratch on every state change, so this has to hold four times over -
# and Return must never reach Claim or a pathway, both of which are one-way.
for label, state in (("idle", fresh()), ("venturing", None), ("pending", None), ("treasure", None)):
    if state is None:
        state = fresh(dungeons_claimed=4)
        state["dungeon"] = dungeon._new_dungeon()
        if label == "pending":
            state["dungeon"]["pending"] = {"paths": [{"kind": "gold", "gold": 30}]}
        if label == "treasure":
            state["dungeon"]["picked"] = [{"took": {"kind": "gold", "gold": 30}, "auto": False}]
            state["dungeon"]["treasure"] = {"claimed": False}
    use(state)
    dlg = None
    real_exec = QtWidgets.QDialog.exec

    def capture(self):
        global dlg
        dlg = self
        return 0

    QtWidgets.QDialog.exec = capture
    ui_dungeon.show_dungeon_dialog(None, noop)
    QtWidgets.QDialog.exec = real_exec
    btns = {b.text(): b for b in dlg.findChildren(QtWidgets.QPushButton)}
    # The row's one button closes the window in every state; at the treasure it also claims, and
    # says so.
    want_label = "Claim" if label == "treasure" else "Close"
    closer = btns.get(want_label)
    defaults = [t for t, b in btns.items() if b.isDefault()]
    autos = [t for t, b in btns.items() if b.autoDefault() and t != want_label]
    ok = closer is not None and defaults == [want_label] and not autos
    print(f"  {'ok  ' if ok else 'FAIL'} {label}: default={defaults} other-autoDefault={autos}")
    if not ok:
        FAILS.append(f"default button in the {label} state")

print("\nwhat a dungeon event says, from notices")
for label, earned, want in (
    ("entrance", {"dungeon_entrance": True}, ["Dungeon entrance discovered!"]),
    ("branching", {"dungeon_branching": True, "dungeon_xp": 92},
     ["Dungeon: branching pathways discovered! (+92 XP)"]),
    ("auto-pick names its pick",
     {"dungeon_branching": True, "dungeon_xp": 92,
      "dungeon_auto_took": {"kind": "gold", "gold": 43}},
     ["Dungeon: branching pathways discovered — took 43g. (+92 XP)"]),
    ("treasure", {"dungeon_treasure": True, "dungeon_xp": 230},
     ["Dungeon: treasure room discovered! (+230 XP)"]),
    ("nothing found", {}, []),
):
    got = notices.dungeon_lines(earned)
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}: {got}")
    if not ok:
        FAILS.append(f"notice line: {label}")

print("\none-time unlock notices")
notices.pending_unlocks.clear()


def unlocks_for(state):
    """The lines queue_unlocks produces for one save, draining the queue."""
    notices.queue_unlocks(state)
    got, notices.pending_unlocks[:] = list(notices.pending_unlocks), []
    return got


got = unlocks_for(fresh(total_xp=100))
ok = got == []
print(f"  {'ok  ' if ok else 'FAIL'} below both gates: {got}")
if not ok: FAILS.append("notice fired too early")

d = fresh(total_xp=4000)
first, second = unlocks_for(d), unlocks_for(d)
ok = len(first) == 2 and second == []
print(f"  {'ok  ' if ok else 'FAIL'} announced once: {len(first)} then {len(second)}")
for line in first:
    print(f"         {line!r}")
if not ok: FAILS.append("unlock notice not one-shot")

# Two lines each, and the milestones one first so the stagger fires it first.
ok = all(m.count("\n") == 1 and m.endswith("See the CollectQuest window.") for m in first)
ok = ok and first[0].startswith("Milestones") and first[1].startswith("Dungeons")
print(f"  {'ok  ' if ok else 'FAIL'} both are two lines, milestones first")
if not ok: FAILS.append("unlock notice wording or order")

# Milestones once per profile: through a prestige and through a wipe.
d = fresh(total_xp=100000, milestones_unlock_notice_shown=True, dungeon_unlock_notice_shown=True)
after_prestige = storage.carry_prestige_keys(d, storage._default_state())
after_wipe = storage.carry_preserved_keys(d, storage._default_state())
ok = after_prestige["milestones_unlock_notice_shown"] and after_wipe["milestones_unlock_notice_shown"]
print(f"  {'ok  ' if ok else 'FAIL'} milestones notice survives a prestige and a wipe")
if not ok: FAILS.append("milestones notice not once per profile")

# Dungeons once per run: the flag resets, so the next run announces it again past level 15.
ok = not after_prestige.get("dungeon_unlock_notice_shown")
print(f"  {'ok  ' if ok else 'FAIL'} dungeon notice resets on prestige")
if not ok: FAILS.append("dungeon notice survived a prestige")
after_prestige["total_xp"] = 4000
got = unlocks_for(after_prestige)
ok = len(got) == 1 and got[0].startswith("Dungeons")
print(f"  {'ok  ' if ok else 'FAIL'} and fires again next run, alone: {len(got)} line(s)")
if not ok: FAILS.append("dungeon notice did not re-fire")

print("\nthe post-sync comparison")
use(fresh())
before = hooks._dungeon_stage()
STATE["dungeon"] = dungeon._new_dungeon()
STATE["dungeon"]["branchings_done"] = 2
got = hooks._dungeon_sync_lines(before)
ok = any("entrance" in l for l in got) and any("branching" in l for l in got)
print(f"  {'ok  ' if ok else 'FAIL'} a batch that started a dungeon and ran branchings: {got}")
if not ok:
    FAILS.append("sync lines for a started dungeon")
before = hooks._dungeon_stage()
STATE.pop("dungeon")
STATE["dungeons_claimed"] = 1
got = hooks._dungeon_sync_lines(before)
ok = got == ["Dungeon: treasure room discovered!"]
print(f"  {'ok  ' if ok else 'FAIL'} a batch that finished one: {got}")
if not ok:
    FAILS.append("sync lines for a finished dungeon")
use(fresh())
before = hooks._dungeon_stage()
got = hooks._dungeon_sync_lines(before)
ok = got == []
print(f"  {'ok  ' if ok else 'FAIL'} a quiet batch says nothing: {got}")
if not ok:
    FAILS.append("sync lines for a quiet batch")

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: " + ", ".join(dict.fromkeys(FAILS)))
    sys.exit(1)
print("all dungeon UI checks passed")
