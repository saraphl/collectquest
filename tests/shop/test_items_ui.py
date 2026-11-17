"""
Build the Items window with PyQt6 standing in for aqt.qt on an offscreen display and check its
header gap, that the Refine buttons line up with Close unless a scrollbar needs the room and share
one width, which stat line each bonus lands on, the level or "dungeon" note after each item's
name, what the Sort and Show drop-downs list, and that the sort is remembered.
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
stats = importlib.import_module("cq.src.stats")
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


# A stat's spaces, hyphen and slash are made non-breaking; compared as plain text.
PLAIN = {0xA0: " ", 0x2060: None}


def stat_lines(owned):
    box = QtWidgets.QWidget()
    ui_items.add_stats_rows(QtWidgets.QVBoxLayout(box), stats.item_stats(owned))
    return [l.text().translate(PLAIN) for l in box.findChildren(QtWidgets.QLabel)]


# Stone is XP, Package gem luck, Training shield shard luck, Island the streak bonus and XP.
got = stat_lines(["stone", "package", "training_shield", "island"])
want = ["+3% XP", "+3% gem luck  \u00b7  +12% shard luck  \u00b7  +10% 7-day streak rewards"]
check("both lucks share the streak bonus's line", got == want, str(got))
got = stat_lines(["package"])
check("a line with no stats is skipped", got == ["+3% gem luck"], str(got))
# Cup is +2g/level: worded as the item is, not as a bare "+2g".
got = stat_lines(["stone", "cup"])
check("gold per level keeps its name", got == ["+1% XP  \u00b7  +2g/level"], str(got))

print("\nstat lines wrap between stats only")


def wrapped(text, font, width):
    """`text` as Qt word-wraps it at `width`, one string per line."""
    layout = QtGui.QTextLayout(text, font)
    option = QtGui.QTextOption()
    option.setWrapMode(QtGui.QTextOption.WrapMode.WordWrap)
    layout.setTextOption(option)
    layout.beginLayout()
    out = []
    while (line := layout.createLine()).isValid():
        line.setLineWidth(width)
        out.append(text[line.textStart():line.textStart() + line.textLength()])
    layout.endLayout()
    return [l.translate(PLAIN).strip() for l in out]


# Island's "7-day streak rewards" has a hyphen and Cup's "+2g/level" a slash, where Qt would break.
box = QtWidgets.QWidget()
owned = ["stone", "cup", "package", "island"]
ui_items.add_stats_rows(QtWidgets.QVBoxLayout(box), stats.item_stats(owned))
split = set()
for label in box.findChildren(QtWidgets.QLabel):
    whole = set(label.text().translate(PLAIN).split("  \u00b7  "))
    for width in range(30, 500, 3):
        for line in wrapped(label.text(), label.font(), width):
            parts = line.rstrip("\u00b7").strip().split("  \u00b7  ")
            split |= {part for part in parts if part not in whole}
check("no stat is ever split across lines", not split, str(sorted(split)))

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

print("\nsort and filter")


def open_view(owned, **state):
    STATE.clear()
    STATE.update(storage._default_state())
    STATE.update(total_xp=10**7, owned_collectibles=owned, **state)
    ui_items.show_items_dialog(None, lambda: None)
    return DIALOGS[-1]


def combos(d):
    """The drop-downs as they stand now: Sort, then Show once refinement is unlocked."""
    return [c for c in d.findChildren(QtWidgets.QComboBox) if c.isVisible()]


def pick(combo, label):
    index = combo.findText(label)
    assert index >= 0, f"no {label!r} among {[combo.itemText(i) for i in range(combo.count())]}"
    combo.setCurrentIndex(index)
    settle()


def shown_names(d):
    return [l.text().split(" <span")[0] for l in d.findChildren(assets.NotedNameLabel) if l.isVisible()]


def row_heights(d):
    """Each listed row's height, by its item's name."""
    rows = d.findChildren(QtWidgets.QScrollArea)[0].widget().layout()
    items = [rows.itemAt(i) for i in range(rows.count())]
    return dict(zip(shown_names(d), [i.geometry().height() for i in items if i.layout()]))


def frame(d):
    """Where the window's fixed parts sit: its height, the Sort drop-down and Close."""
    close = next(b for b in d.findChildren(QtWidgets.QPushButton) if b.text() == "Close")
    return d.height(), combos(d)[0].mapTo(d, QtCore.QPoint(0, 0)).y(), close.mapTo(d, QtCore.QPoint(0, 0)).y()


# Oldest first. Levels 1, 1, 3, 24 and 35, then a dungeon item and a key, which has no stats.
OWNED = ["stone", "cup", "fish", "hammer_2", "axe_3", "bronze_helm", "key_bronze"]
# Refinement reaches level 30. One Shard pays for a Normal item's step, not for Fine Cup's.
REFINING = {"shards": 1, "prestige_upgrades": {"refinement": 1},
            shop.QUALITY_KEY: {"cup": shop.QUALITY_FINE, "fish": shop.QUALITY_SUPERIOR}}

d = open_view(OWNED)
check("no Show before refinement is unlocked", [c.currentText() for c in combos(d)] == ["Newest first"],
      str([c.currentText() for c in combos(d)]))
pick(combos(d)[0], "Lowest level first")
check("Sort works without it", shown_names(d)[:2] == ["Cup", "Stone"], str(shown_names(d)))
d.close()

d = open_view(OWNED, **REFINING)
sort, flt = combos(d)
check("opens newest first and unfiltered",
      (sort.currentText(), flt.currentText()) == ("Newest first", "All items"))
labels = [l for l in d.findChildren(QtWidgets.QLabel) if l.text().endswith(":") and l.isVisible()]
check("the drop-downs are labeled Sort and Show",
      [l.text() for l in labels] == ["Sort:", "Show:"] and [l.buddy() for l in labels] == [sort, flt],
      str([l.text() for l in labels]))
options = [flt.itemText(i) for i in range(flt.count())]
check("Show lists its three options", options == ["All items", "Refinable", "Have shards"], str(options))
widths = (sort.width(), flt.width())
check("Sort is as wide as its longest option needs, and Show matches it",
      widths == (sort.sizeHint().width(),) * 2 and flt.sizeHint().width() < flt.width(), str(widths))
# The plain list and the trimmed arrow are for Anki's style sheet; the native style keeps its own.
check("with no style sheet over them, the drop-downs are left as the style draws them",
      (sort.styleSheet(), flt.styleSheet()) == ("", "")
      and not any(type(c.itemDelegate()) is QtWidgets.QStyledItemDelegate for c in (sort, flt)),
      str([type(c.itemDelegate()).__name__ for c in (sort, flt)]))
close = next(b for b in d.findChildren(QtWidgets.QPushButton) if b.text() == "Close")
ends = (right(sort, d), right(flt, d))
check("and both end at the right edge, where Close does", ends == (right(close, d),) * 2,
      f"{ends} vs {right(close, d)}")
focused = d.focusWidget()
check("the window opens with Close focused, not a drop-down",
      isinstance(focused, QtWidgets.QPushButton) and focused.text() == "Close", repr(focused))
want = ["Bronze key", "Bronze helm", "Epic axe", "Great hammer", "Superior Fish", "Fine Cup", "Stone"]
check("newest first is the collection backwards", shown_names(d) == want, str(shown_names(d)))
full_frame, full_rows = frame(d), row_heights(d)
pick(sort, "Lowest level first")
want = ["Fine Cup", "Stone", "Superior Fish", "Bronze key", "Great hammer", "Epic axe", "Bronze helm"]
check("lowest level first, a level's items by name, loot last", shown_names(d) == want, str(shown_names(d)))
pick(sort, "Highest level first")
want = ["Bronze helm", "Epic axe", "Great hammer", "Bronze key", "Superior Fish", "Fine Cup", "Stone"]
check("highest level first, loot leading, a level's items still by name", shown_names(d) == want,
      str(shown_names(d)))
pick(sort, "Name (A\u2013Z)")
want = ["Bronze helm", "Bronze key", "Fine Cup", "Epic axe", "Superior Fish", "Great hammer", "Stone"]
check("by name, whatever the quality in front", shown_names(d) == want, str(shown_names(d)))
check("sorting moves nothing else", frame(d) == full_frame, f"{frame(d)} vs {full_frame}")

pick(sort, "Newest first")
pick(flt, "Refinable")
# Fish is Superior, Epic axe above level 30, and the helm and the key never refinable.
check("Refinable keeps every row with a Refine button",
      shown_names(d) == ["Great hammer", "Fine Cup", "Stone"] and len(refine_buttons(d)) == 3,
      f"{shown_names(d)}, {len(refine_buttons(d))} button(s)")
check("a shorter list leaves the window as it was", frame(d) == full_frame, f"{frame(d)} vs {full_frame}")
got = row_heights(d)
check("and its rows unstretched, at the top", all(got[n] == full_rows[n] for n in got), f"{got} vs {full_rows}")
pick(flt, "Have shards")
check("Have shards keeps the ones that can be paid for",
      shown_names(d) == ["Great hammer", "Stone"] and all(b.isEnabled() for b in refine_buttons(d)),
      str(shown_names(d)))
pick(sort, "Lowest level first")
check("sorted while filtered", shown_names(d) == ["Stone", "Great hammer"], str(shown_names(d)))

STATE["shards"] = 0
pick(flt, "All items")
pick(flt, "Have shards")
notes = [l for l in d.findChildren(QtWidgets.QLabel)
         if l.text() == "No items match this filter." and l.isVisible()]
check("a filter nothing passes says so", not shown_names(d) and len(notes) == 1, str(shown_names(d)))
check("in a window still as it was", frame(d) == full_frame, f"{frame(d)} vs {full_frame}")

# Refining rebuilds the whole window; the picks have to outlive it.
STATE["shards"] = 9
pick(flt, "Refinable")
pick(sort, "Name (A\u2013Z)")
refine_buttons(d)[0].click()  # Fine Cup, to Superior
settle()
picks = [c.currentText() for c in combos(d)]
check("a refine keeps both picks", picks == ["Name (A\u2013Z)", "Refinable"], str(picks))
check("and drops the row it finished", shown_names(d) == ["Great hammer", "Stone"], str(shown_names(d)))
check("in a window still as it was", frame(d) == full_frame, f"{frame(d)} vs {full_frame}")
d.close()

# A lucky refine makes its item Superior, which Refinable would hide along with the tag.
d = open_view(["stone", "fish"], shards=9, prestige_upgrades={"refinement": 1},
              milestones={"started": True, "active": 18})
pick(combos(d)[1], "Refinable")
shop.random.random = lambda: 0.0
refine_buttons(d)[0].click()  # newest first: Fish
settle()
check("a lucky refine keeps its row under a filter",
      shown_names(d) == ["Superior Fish", "Stone"] and len(lucky_tags(d)) == 1,
      f"{shown_names(d)}, {len(lucky_tags(d))} tag(s)")
shop.random.random = lambda: 0.999
refine_buttons(d)[0].click()  # Stone
settle()
check("until the next refine", shown_names(d) == ["Fine Stone"] and not lucky_tags(d), str(shown_names(d)))
shop.random.random = real_random
d.close()

# Twelve rows need the scrollbar; all but two are Fine, so one Shard isn't enough for them.
ids = [c["id"] for c in shop.COLLECTIBLES][:12]
d = open_view(ids, shards=1, prestige_upgrades={"refinement": 1},
              **{shop.QUALITY_KEY: {cid: shop.QUALITY_FINE for cid in ids[2:]}})
sort, flt = combos(d)
bar = d.findChildren(QtWidgets.QScrollArea)[0].verticalScrollBar()
bar.setValue(bar.maximum())
pick(sort, "Name (A\u2013Z)")
refine, close, showing = edges(d)
check("sorting scrolls back to the top", showing and bar.value() == 0, str(bar.value()))
check("and keeps the gap before the scrollbar", refine == {close - gap - bar.width()},
      f"{refine} vs {close} - {gap} - {bar.width()}")
pick(flt, "Have shards")
refine, close, showing = edges(d)
check("filtered down to no scrollbar, the buttons line up with Close",
      not showing and len(shown_names(d)) == 2 and refine == {close}, f"{refine} vs {close}")
pick(flt, "All items")
refine, close, showing = edges(d)
check("and step back when it returns", showing and refine == {close - gap - bar.width()},
      f"{refine} vs {close} - {gap} - {bar.width()}")
d.close()

# Anki's style sheet pads the arrow of every drop-down; ours give most of that up to be narrower.
ANKI_COMBO = ("QComboBox { padding: 1px 4px 2px 6px; } QComboBox::drop-down { subcontrol-origin: border;"
              " padding: 2px 4px; width: 16px; border: 1px solid transparent; }"
              " QComboBox::item { color: black; background: white; }")
app.setStyleSheet(ANKI_COMBO)
d = open_view(OWNED, **REFINING)
sort, flt = combos(d)
# Qt's own delegate ticks the current option under that sheet's item rules; a plain one doesn't.
check("under Anki's style sheet the drop-downs list their options without a tick",
      all(type(c.itemDelegate()) is QtWidgets.QStyledItemDelegate for c in (sort, flt)),
      str([type(c.itemDelegate()).__name__ for c in (sort, flt)]))
stock = QtWidgets.QComboBox(d)
stock.addItems([sort.itemText(i) for i in range(sort.count())])
stock.ensurePolished()
saved = stock.sizeHint().width() - sort.width()
check("and trim the arrow's padding", saved == 11,
      f"{sort.width()} vs a stock {stock.sizeHint().width()}")
metrics, option = sort.fontMetrics(), QtWidgets.QStyleOptionComboBox()
sort.initStyleOption(option)
field = sort.style().subControlRect(QtWidgets.QStyle.ComplexControl.CC_ComboBox, option,
                                    QtWidgets.QStyle.SubControl.SC_ComboBoxEditField, sort)
longest = max(metrics.horizontalAdvance(sort.itemText(i)) for i in range(sort.count()))
check("and still show the longest option whole", field.width() >= longest, f"{field.width()} for {longest}")
check("at one width, against the right edge",
      sort.width() == flt.width() and right(sort, d) == right(flt, d) == edges(d)[1],
      f"{sort.width()} and {flt.width()}")
d.close()
app.setStyleSheet("")

# The sort is saved as it's picked and opens the window next time; the filter starts over.
SAVES = []
storage.save = lambda data: (SAVES.append(data.get("items_sort")), STATE.update(data))
d = open_view(OWNED, **REFINING)
sort, flt = combos(d)
pick(flt, "Refinable")
check("a filter pick saves nothing", not SAVES, str(SAVES))
pick(sort, "Highest level first")
check("a sort pick is saved", SAVES == ["level_down"] and STATE["items_sort"] == "level_down", str(SAVES))
d.close()
ui_items.show_items_dialog(None, lambda: None)  # the same save, not a fresh one
d = DIALOGS[-1]
picks = [c.currentText() for c in combos(d)]
check("the window reopens on that sort, unfiltered", picks == ["Highest level first", "All items"], str(picks))
want = ["Bronze helm", "Epic axe", "Great hammer", "Bronze key", "Superior Fish", "Fine Cup", "Stone"]
check("with its list in that order", shown_names(d) == want, str(shown_names(d)))
d.close()
STATE["items_sort"] = "by_color"  # not a sort this build has
ui_items.show_items_dialog(None, lambda: None)
d = DIALOGS[-1]
check("an unknown saved sort opens newest first",
      combos(d)[0].currentText() == "Newest first" and shown_names(d)[0] == "Bronze key", str(shown_names(d)))
d.close()
kept = storage.carry_preserved_keys({"items_sort": "name"}, storage._default_state())
check("a wipe or a prestige keeps the sort", kept["items_sort"] == "name"
      and "items_sort" in storage.PRESERVED_ON_PRESTIGE_KEYS, str(kept["items_sort"]))
storage.save = lambda data: STATE.update(data)

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: " + ", ".join(dict.fromkeys(FAILS)))
    sys.exit(1)
print("all Items UI checks passed")
