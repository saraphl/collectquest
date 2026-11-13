"""
Build the Items window with PyQt6 standing in for aqt.qt on an offscreen display and check its
header gap, that the Refine buttons line up with Close unless a scrollbar needs the room and share
one width, which stat line each bonus lands on, and the level or "dungeon" note after each item's
name.
Exit 1 = a check failed.

    python3 tests/shop/test_items_ui.py
"""
import importlib
import os
import pathlib
import sys
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT.parent))

import PyQt6.QtCore as QtCore
import PyQt6.QtGui as QtGui
import PyQt6.QtWidgets as QtWidgets

# Same flat aqt.qt stand-in as test_dungeon_ui.py.
qt = types.ModuleType("aqt.qt")
for src in (QtCore, QtGui, QtWidgets):
    for name in dir(src):
        if name.startswith("Q") or name == "Qt":
            setattr(qt, name, getattr(src, name))
sys.modules["aqt.qt"] = qt

aqt = types.ModuleType("aqt")
aqt.mw = None
aqt.qt = qt
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
assets = importlib.import_module("cq.src.ui.assets")
constants = importlib.import_module("cq.src.ui.constants")
shop = importlib.import_module("cq.src.shop")
ui_items = importlib.import_module("cq.src.ui.items")

assets.addon_dir = lambda: str(ROOT)
assets._addon_dir_cache = str(ROOT)

FAILS = []
STATE = {}
storage.load = lambda: STATE
storage.save = lambda d: STATE.update(d)
REAL_REFINE_STATUS = shop.refine_status
# Every row refinable, so each one has a button to line up.
ui_items.shop_mod.refine_status = lambda data, cid: shop.REFINE_READY

DIALOGS = []


def settle():
    for _ in range(5):
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete.value)
        app.processEvents()


def _capture(d):
    """Stands in for exec_dialog: show without blocking so the test can read the window."""
    DIALOGS.append(d)
    d.show()
    settle()


ui_items.exec_dialog = _capture


def check(label, ok, detail=""):
    print(f"  {'ok  ' if ok else 'FAIL'} {label}{': ' + detail if detail else ''}")
    if not ok:
        FAILS.append(label)


def open_items(n):
    s = storage._default_state()
    s.update(total_xp=100_000, owned_collectibles=[c["id"] for c in shop.COLLECTIBLES][:n])
    STATE.clear()
    STATE.update(s)
    ui_items.show_items_dialog(None, lambda: None)
    return DIALOGS[-1]


def right(w, d):
    return w.mapTo(d, QtCore.QPoint(w.width(), 0)).x()


def edges(d):
    """(right edges of the visible Refine buttons, Close's right edge, scrollbar shown)."""
    refine = {right(b, d) for b in d.findChildren(QtWidgets.QPushButton)
              if b.accessibleName().startswith("Refine") and b.isVisible()}
    close = next(b for b in d.findChildren(QtWidgets.QPushButton) if b.text() == "Close")
    bar = d.findChildren(QtWidgets.QScrollArea)[0].verticalScrollBar()
    return refine, right(close, d), bar.isVisible()


gap = ui_items._ROW_RIGHT_GAP
base_font = app.font()
for pt in (10, 14):
    print(f"\nItems window at {pt}pt")
    f = QtGui.QFont(base_font)
    f.setPointSize(pt)
    app.setFont(f)

    d = open_items(5)
    title = next(l for l in d.findChildren(QtWidgets.QLabel) if l.text() == "Items")
    bag = next(l for l in d.findChildren(QtWidgets.QLabel) if l.pixmap() and not l.pixmap().isNull())
    got = title.mapTo(d, QtCore.QPoint(0, 0)).x() - right(bag, d)
    check("the bag keeps the header gap from its text", got == constants._HEADER_ICON_GAP, str(got))

    refine, close, bar = edges(d)
    check("a short list lines up with Close", not bar and refine == {close}, f"{refine} vs {close}")
    d.resize(d.width(), d.minimumSizeHint().height())
    settle()
    refine, close, bar = edges(d)
    bar_w = d.findChildren(QtWidgets.QScrollArea)[0].verticalScrollBar().width()
    check("squeezed into a scrollbar, it leaves the gap",
          bar and refine == {close - gap - bar_w}, f"{refine} vs {close} - {gap} - {bar_w}")
    d.resize(d.width(), 2000)
    settle()
    refine, close, bar = edges(d)
    check("given the room back, it lines up again", not bar and refine == {close}, f"{refine} vs {close}")
    d.close()

    d = open_items(12)
    refine, close, bar = edges(d)
    bar_w = d.findChildren(QtWidgets.QScrollArea)[0].verticalScrollBar().width()
    check("a long list leaves the gap before its scrollbar",
          bar and refine == {close - gap - bar_w}, f"{refine} vs {close} - {gap} - {bar_w}")
    d.close()

print("\nstat lines")


def stat_lines(owned):
    box = QtWidgets.QWidget()
    ui_items.add_items_stats_row(QtWidgets.QVBoxLayout(box), owned)
    return [l.text() for l in box.findChildren(QtWidgets.QLabel)]


# Stone is XP, Package gem luck, Training shield shard luck, Island the streak bonus.
got = stat_lines(["stone", "package", "training_shield", "island"])
want = ["+1% XP", "+3% gem luck  \u00b7  +12% shard luck  \u00b7  +30% 7-day streak rewards"]
check("both lucks share the streak bonus's line", got == want, str(got))
got = stat_lines(["package"])
check("a line with no stats is skipped", got == ["+3% gem luck"], str(got))

print("\nRefine button widths")
# Stone costs 1 Shard to refine and a tome 15, so their buttons differ by a digit.
tome = next(c for c in shop.COLLECTIBLES if shop.refine_cost(c) >= 10)
STATE.clear()
STATE.update(storage._default_state())
STATE.update(owned_collectibles=["stone", tome["id"]])
ui_items.show_items_dialog(None, lambda: None)
d = DIALOGS[-1]
btns = [b for b in d.findChildren(QtWidgets.QPushButton) if b.accessibleName().startswith("Refine")]
widths = {b.accessibleName(): b.width() for b in btns}
check("one- and two-digit costs share a width", len(btns) == 2 and len(set(widths.values())) == 1, str(widths))
check("wide enough for the longer one", all(b.width() >= b.layout().sizeHint().width() for b in btns), str(widths))
d.close()

print("\nlevel notes")


def name_labels(d):
    """Each row's name as shown, split from its small gray note."""
    texts = [l.text().replace("&nbsp;", " ") for l in d.findChildren(QtWidgets.QLabel) if "<span" in l.text()]
    return {t.split(" <span")[0]: t.split(">")[1].split("<")[0] for t in texts if t.endswith(")</span>")}


loot = shop.loot_collectibles()[0]
STATE.clear()
STATE.update(storage._default_state())
STATE.update({"owned_collectibles": ["stone", loot["id"]], shop.QUALITY_KEY: {loot["id"]: shop.QUALITY_FINE}})
ui_items.show_items_dialog(None, lambda: None)
d = DIALOGS[-1]
got = name_labels(d)
check("a shop item is followed by its level", got.get("Stone") == "(lvl 1)", str(got))
check("dungeon loot says so instead", got.get(f"Fine {loot['name']}") == "(dungeon)", str(got))
d.close()
_, cell = assets.item_row_widgets(shop.get_collectible("stone"))
check("the shop's rows carry no note", [l.text() for l in cell.findChildren(QtWidgets.QLabel)][0] == "Stone")

# The longest name there is, beside the widest Refine button, at a font too big for one line.
f = QtGui.QFont(base_font)
f.setPointSize(18)
app.setFont(f)
longest = max(shop.COLLECTIBLES, key=lambda c: len(c["name"]) if shop.is_refinable(c) else 0)
STATE.update({"owned_collectibles": [longest["id"]], shop.QUALITY_KEY: {longest["id"]: shop.QUALITY_FINE}})
ui_items.show_items_dialog(None, lambda: None)
d = DIALOGS[-1]
name = next(l for l in d.findChildren(assets.NotedNameLabel))
check("a name too long for its row wraps", name.height() > 1.5 * name.fontMetrics().height(),
      f"{name.height()} vs a {name.fontMetrics().height()}px line")
refine, close, bar = edges(d)
check("and keeps its Refine button in view", not bar and refine == {close}, f"{refine} vs {close}")
d.close()

# A lucky refine (milestone #17) leaves a tag where the Refine button was, until the next refine.
print("\nlucky refine tag")
app.setFont(base_font)
ui_items.shop_mod.refine_status = REAL_REFINE_STATUS


def lucky_tags(d):
    return [l for l in d.findChildren(QtWidgets.QLabel) if l.text() == "Lucky refine!" and l.isVisible()]


def refine_buttons(d):
    return [b for b in d.findChildren(QtWidgets.QPushButton)
            if b.isVisible() and b.findChildren(QtWidgets.QLabel)]


STATE.clear()
STATE.update(storage._default_state())
STATE.update(total_xp=10**7, owned_collectibles=["stone", "fish"], shards=9,
             prestige_upgrades={"refinement": 1}, milestones={"started": True, "active": 18})
real_random = shop.random.random
shop.random.random = lambda: 0.0  # every roll lands
ui_items.show_items_dialog(None, lambda: None)
d = DIALOGS[-1]
check("no tag on opening", not lucky_tags(d))
width = refine_buttons(d)[0].width()
refine_buttons(d)[0].click()  # newest first: Fish
settle()
tags, left = lucky_tags(d), refine_buttons(d)
check("a lucky refine tags its row", len(tags) == 1 and STATE[shop.QUALITY_KEY] == {"fish": 2},
      f"{len(tags)} tag(s), {STATE.get(shop.QUALITY_KEY)}")
check("in the Refine button's column",
      bool(tags and left) and (tags[0].width(), right(tags[0], d)) == (left[0].width(), right(left[0], d)))
check("without widening the buttons", bool(left) and left[0].width() == width,
      f"{left[0].width() if left else None} vs {width}")
shop.random.random = lambda: 0.999  # no roll lands
left[0].click()
settle()
check("the next refine clears it", not lucky_tags(d) and STATE[shop.QUALITY_KEY] == {"fish": 2, "stone": 1})
d.close()

# At 18pt the tag's text is wider than a Refine button, and must not stretch the buttons to match.
f = QtGui.QFont(base_font)
f.setPointSize(18)
app.setFont(f)
STATE[shop.QUALITY_KEY] = {}
STATE["shards"] = 9
shop.random.random = lambda: 0.0
ui_items.show_items_dialog(None, lambda: None)
d = DIALOGS[-1]
width = refine_buttons(d)[0].width()
refine_buttons(d)[0].click()
settle()
tags, left = lucky_tags(d), refine_buttons(d)
check("a tag wider than the buttons leaves them alone",
      bool(tags and left) and tags[0].width() > width == left[0].width(),
      f"tag {tags[0].width() if tags else None}, button {left[0].width() if left else None} vs {width}")
check("and still ends where they do", bool(tags and left) and right(tags[0], d) == right(left[0], d))
shop.random.random = real_random
app.setFont(base_font)
d.close()

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: " + ", ".join(dict.fromkeys(FAILS)))
    sys.exit(1)
print("all Items UI checks passed")
