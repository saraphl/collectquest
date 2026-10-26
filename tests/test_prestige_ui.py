"""
Build the prestige window with PyQt6 standing in for aqt.qt on an offscreen display and check its
lines hold still: after a prestige the window shrinks even if KWin hands back the old height, spare
height collects above the buttons, and the Buy buttons share one width. Exit 1 = a check failed.

    python3 tests/test_prestige_ui.py
"""
import copy
import importlib
import os
import pathlib
import sys
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = pathlib.Path(__file__).resolve().parent.parent
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
storage = importlib.import_module("cq.src.storage")
assets = importlib.import_module("cq.src.ui.assets")
xp = importlib.import_module("cq.src.xp")
ui_prestige = importlib.import_module("cq.src.ui.prestige")

assets.addon_dir = lambda: str(ROOT)
assets._addon_dir_cache = str(ROOT)

FAILS = []
STATE = {}
# A copy, as the real load returns: rebuild() clears the dict it was handed before refilling it.
storage.load = lambda: copy.deepcopy(STATE)
storage.save = lambda d: (STATE.clear(), STATE.update(copy.deepcopy(d)))

DIALOGS = []
CONFIRM_PARENTS = []


def _capture(d):
    """Stands in for exec_dialog: show without blocking so the test can drive the window."""
    DIALOGS.append(d)
    d.show()
    settle()


def _confirm(parent, *a, **k):
    CONFIRM_PARENTS.append(parent)
    return QtWidgets.QMessageBox.StandardButton.Yes


ui_prestige.exec_dialog = _capture
ui_prestige.QMessageBox.question = staticmethod(_confirm)


def settle():
    """Run the zero-timers and deferred deletes a real event loop would."""
    for _ in range(5):
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete.value)
        app.processEvents()


def check(label, ok, detail=""):
    print(f"  {'ok  ' if ok else 'FAIL'} {label}{': ' + detail if detail else ''}")
    if not ok:
        FAILS.append(label)


def label_ys(d):
    """Where each visible line sits, keyed by its text up to the first digit (counts change)."""
    out = {}
    for lbl in d.findChildren(QtWidgets.QLabel):
        if lbl.isVisible() and lbl.text():
            key = lbl.text().split("\n")[0].rstrip("0123456789").strip()[:24]
            out[key] = lbl.mapTo(d, QtCore.QPoint(0, 0)).y()
    return out


def button(d, prefix):
    return next(b for b in d.findChildren(QtWidgets.QPushButton) if b.text().startswith(prefix))


def ready_state(level: int) -> dict:
    s = storage._default_state()
    total = 0
    while xp.level_from_total_xp(total) < level:
        total += 500
    s.update(total_xp=total, prestige_count=2, prestige_points_total=6, prestige_points_spent=6)
    return s


base_font = app.font()
for pt in (10, 14):
    print(f"\nprestige window at {pt}pt")
    f = QtGui.QFont(base_font)
    f.setPointSize(pt)
    app.setFont(f)
    STATE.clear()
    STATE.update(ready_state(62))
    CONFIRM_PARENTS.clear()
    # Opened over a window, as from the CollectQuest window; a box parented to that one would steal
    # the focus back from this window.
    owner = QtWidgets.QDialog()
    ui_prestige.show_prestige_dialog(owner, lambda: None)
    d = DIALOGS[-1]
    button(d, "Prestige now").click()
    settle()
    check("confirm box is parented to the prestige window", CONFIRM_PARENTS == [d])
    check("window shrinks after prestiging", d.height() == d.sizeHint().height(),
          f"height {d.height()}, needs {d.sizeHint().height()}")

    before = label_ys(d)
    # What KWin does when the confirm box hands focus back: restore the pre-refit height.
    old_height = d.height() + 66
    d.resize(d.width(), old_height)
    settle()
    taller = label_ys(d)
    moved = {k: (before[k], taller[k]) for k in before if k in taller and before[k] != taller[k]}
    check("spare height leaves the lines in place", not moved, str(moved))
    QtWidgets.QApplication.sendEvent(d, QtCore.QEvent(QtCore.QEvent.Type.WindowActivate))
    settle()
    check("reactivation refits the window", d.height() == d.sizeHint().height(),
          f"height {d.height()}, needs {d.sizeHint().height()}")

    after_prestige = label_ys(d)
    button(d, "Buy").click()
    settle()
    after_buy = label_ys(d)
    moved = {k: (after_prestige[k], after_buy[k]) for k in after_prestige
             if k in after_buy and after_prestige[k] != after_buy[k]}
    check("buying moves nothing", not moved, str(moved))

    # Only the first activation after a prestige refits; a dragged-taller window stays put later.
    d.resize(d.width(), d.height() + 50)
    settle()
    stretched = d.height()
    QtWidgets.QApplication.sendEvent(d, QtCore.QEvent(QtCore.QEvent.Type.WindowActivate))
    settle()
    check("later activations leave the size alone", d.height() == stretched)
    d.close()
    owner.close()

    print(f"\nBuy buttons at {pt}pt")
    STATE.clear()
    STATE.update(ready_state(1))
    STATE.update(prestige_points_total=20, prestige_points_spent=0, prestige_upgrades={"xp_percent": 9})
    ui_prestige.show_prestige_dialog(None, lambda: None)
    d = DIALOGS[-1]
    buys = [b for b in d.findChildren(QtWidgets.QPushButton) if b.text().startswith("Buy")]
    check("a two-digit cost is on offer", any("10 pt" in b.text() for b in buys))
    check("all Buy buttons share one width", len({b.width() for b in buys}) == 1,
          str(sorted({b.width() for b in buys})))
    d.close()

    print(f"\nKey unlocks at {pt}pt")
    STATE.clear()
    STATE.update(ready_state(62))
    STATE.update(prestige_points_total=11, prestige_points_spent=0)
    ui_prestige.show_prestige_dialog(None, lambda: None)
    d = DIALOGS[-1]
    unlock_btn = button(d, "Buy (5 pt)")
    locked = [l for l in d.findChildren(QtWidgets.QLabel) if l.text() == "Locked"]
    check("Silver key reads Locked until Bronze is bought",
          len(locked) == 1 and "Bronze key" in (locked[0].property("cq_hover_tip") or ""))
    silver_title = next(l for l in d.findChildren(QtWidgets.QLabel) if l.text().strip() == "Silver key")
    check("locked row is greyed", "#888" in locked[0].styleSheet() and "#888" in silver_title.styleSheet())
    before = label_ys(d)
    unlock_btn.click()
    settle()
    unlocked = [l for l in d.findChildren(QtWidgets.QLabel) if l.text() == "Unlocked"]
    check("bought unlock reads Unlocked", len(unlocked) == 1)
    # Read after the click: the Silver key's two-digit Buy now on offer may widen the column.
    upgrade_width = button(d, "Buy (1 pt)").width()
    check("Unlocked keeps the Buy column's width",
          bool(unlocked) and unlocked[0].width() == upgrade_width,
          f"{unlocked[0].width() if unlocked else None} vs {upgrade_width}")
    after = label_ys(d)
    moved = {k: (before[k], after[k]) for k in before if k in after and before[k] != after[k]}
    check("buying the unlock moves nothing", not moved, str(moved))
    check("points spent and Bronze key granted at once",
          STATE["prestige_points_spent"] == 5 and "key_bronze" in STATE["owned_collectibles"])
    silver_btn = button(d, "Buy (10 pt)")
    silver_title = next(l for l in d.findChildren(QtWidgets.QLabel) if l.text().strip() == "Silver key")
    check("Silver key row loses its grey once Bronze is bought", not silver_title.styleSheet())
    check("Silver key offered once Bronze is bought, but unaffordable", not silver_btn.isEnabled())
    button(d, "Prestige now").click()
    settle()
    check("next run starts with the Bronze key",
          STATE["level"] == 1 and STATE["owned_collectibles"] == ["key_bronze"]
          and STATE["prestige_unlocks"] == ["bronze_key"])
    check("unlock is still Unlocked after prestiging",
          any(l.text() == "Unlocked" for l in d.findChildren(QtWidgets.QLabel)))
    STATE.update(prestige_points_total=STATE["prestige_points_spent"] + 10)
    d.close()
    ui_prestige.show_prestige_dialog(None, lambda: None)
    d = DIALOGS[-1]
    button(d, "Buy (10 pt)").click()
    settle()
    check("Silver key granted at once",
          STATE["owned_collectibles"] == ["key_bronze", "key_silver"]
          and STATE["prestige_unlocks"] == ["bronze_key", "silver_key"])
    check("both unlocks read Unlocked",
          sum(l.text() == "Unlocked" for l in d.findChildren(QtWidgets.QLabel)) == 2)
    d.close()

prestige_mod = importlib.import_module("cq.src.prestige")
s = storage._default_state()
s.update(prestige_points_total=20)
check("Silver key can't be bought before Bronze",
      not prestige_mod.buy_unlock(s, "silver_key") and s["prestige_points_spent"] == 0)
s = {"prestige_unlocks": ["silver_key"], "owned_collectibles": None}
prestige_mod.grant_unlock_items(s)
check("a save without the Bronze unlock gets no Silver key, and a None collection is survived",
      s["owned_collectibles"] == [])

print("\nSections")
STATE.clear()
STATE.update(ready_state(1))
ui_prestige.show_prestige_dialog(None, lambda: None)
d = DIALOGS[-1]
ys = {}
for lbl in d.findChildren(QtWidgets.QLabel):
    ys.setdefault(lbl.text().split(" — ")[0].strip(), []).append(lbl.mapTo(d, QtCore.QPoint(0, 0)).y())
check("Starting gold is listed once, under Starting boosts",
      len(ys.get("Starting gold", [])) == 1 and ys["Starting gold"][0] > ys["Starting boosts"][0])
check("stat upgrades sit above Starting boosts",
      max(ys["XP bonus"] + ys["Dungeon exploration"]) < ys["Starting boosts"][0])
d.close()

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: " + ", ".join(dict.fromkeys(FAILS)))
    sys.exit(1)
print("all prestige UI checks passed")
