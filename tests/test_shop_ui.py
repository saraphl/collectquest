"""
Build the shop dialog with PyQt6 standing in for aqt.qt on an offscreen display and check its
sizing: the window widens when a rebuild needs more room, sold rows keep the Buy column, and the
bottom buttons have the intended widths. Exit 1 = a check failed.

    python3 tests/test_shop_ui.py
"""
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
shop = importlib.import_module("cq.src.shop")
assets = importlib.import_module("cq.src.ui.assets")
constants = importlib.import_module("cq.src.ui.constants")
ui_shop = importlib.import_module("cq.src.ui.shop")

assets.addon_dir = lambda: str(ROOT)
assets._addon_dir_cache = str(ROOT)

FAILS = []
STATE = {}
storage.load = lambda: STATE
storage.save = lambda d: STATE.update(d)
ui_shop.shop_mod.open_for_today = lambda data, today: True

DIALOGS = []


def _capture(d):
    """Stands in for exec_dialog: show without blocking so the test can drive the window."""
    DIALOGS.append(d)
    d.show()
    settle()


ui_shop.exec_dialog = _capture


def settle():
    """Run the zero-timers and deferred deletes a real event loop would."""
    for _ in range(5):
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete.value)
        app.processEvents()


def check(label, ok, detail=""):
    print(f"  {'ok  ' if ok else 'FAIL'} {label}{': ' + detail if detail else ''}")
    if not ok:
        FAILS.append(label)


def fresh_state():
    d = storage._default_state()
    key = next(c["id"] for c in shop.COLLECTIBLES if c["id"].startswith("key_"))
    d.update(total_xp=100_000, money=5000, owned_collectibles=[key])
    return d


def open_shop():
    ui_shop.show_shop_dialog()
    return DIALOGS[-1]


def buttons(d, prefix):
    return [b for b in d.findChildren(QtWidgets.QPushButton) if b.text().startswith(prefix) and not b.isHidden()]


def price_grid(d):
    return d.findChildren(QtWidgets.QGridLayout)[0]


print("refit_dialog widens a window whose rebuilt content outgrew its pinned width")
d = QtWidgets.QDialog()
lay = QtWidgets.QVBoxLayout(d)
btn = QtWidgets.QPushButton("x")
lay.addWidget(btn)
d.setMinimumWidth(200)
d.setMaximumWidth(250)
d.show()
settle()
btn.setFixedWidth(400)
assets.refit_dialog(d)
settle()
need = d.minimumSizeHint().width()
check("window at least as wide as its content", d.width() >= need, f"width {d.width()}, needs {need}")
d.close()

base_font = app.font()
for pt in (10, 14, 18):
    print(f"\nshop at {pt}pt")
    f = QtGui.QFont(base_font)
    f.setPointSize(pt)
    app.setFont(f)
    random.seed(pt)  # the day's slots are rolled at random
    STATE.clear()
    STATE.update(fresh_state())
    d = open_shop()

    close = buttons(d, "Close")[0]
    want = max(close.sizeHint().width(), constants._DIALOG_BUTTON_MIN_WIDTH)
    check("Close has the CollectQuest window's floor", close.width() == want, f"{close.width()} vs {want}")

    # The free restock turns the label into the longer paid one.
    buttons(d, "Restock")[0].click()
    settle()
    restock = buttons(d, "Restock")[0]
    check("restock label now shows the price", "g)" in restock.text(), restock.text())
    check("restock keeps its own width", restock.width() >= restock.sizeHint().width())
    need = d.minimumSizeHint().width()
    check("window widened to fit the longer label", d.width() >= need, f"width {d.width()}, needs {need}")

    grid = price_grid(d)
    # Measured from the right edge: the reopened window can differ in width, the gap to it can't.
    unsold_gap = [d.width() - grid.itemAtPosition(r, 3).geometry().x() for r in range(grid.rowCount()) if grid.itemAtPosition(r, 3)]
    for slot in STATE["shop_daily_slots"]:
        slot["sold"] = True
        if slot.get("type") == "collectible":
            STATE["owned_collectibles"].append(slot["id"])
    d.close()
    d = open_shop()
    grid = price_grid(d)
    cells = [grid.itemAtPosition(r, 3) for r in range(grid.rowCount())]
    cells = [c for c in cells if c]
    check("every sold row keeps a Buy cell", len(cells) == len(unsold_gap), f"{len(cells)} of {len(unsold_gap)}")
    check("the Buy cells are hidden", all(not c.widget().isVisible() for c in cells))
    check("the Buy column keeps its width", all(c.geometry().width() > 0 for c in cells))
    gap = [d.width() - c.geometry().x() for c in cells]
    check("the Buy column stays in place", gap == unsold_gap, f"{gap} vs {unsold_gap}")
    d.close()

print("\nthe gem trade")
day = ["2026-10-09"]
_real_today_str = shop._today_str
shop._today_str = lambda: day[0]
d = {"gems": {"blue": 3, "green": 2, "pink": 2, "purple": 5, "yellow": 2}, "owned_collectibles": []}
check("no trade without the Prism", shop.trade_gem_colors(d) is None)
d["owned_collectibles"].append(shop.PRISM_ID)
offer = shop.gem_trade_offer(d)
check("gives the biggest pile, 2 for 1", offer is not None and offer[:2] == ("purple", 2), str(offer))
check("gets one of the tied smallest", offer is not None and offer[2] in ("green", "pink", "yellow"))
check("a tie's pick holds until the gems change",
      all(shop.gem_trade_offer(d) == offer for _ in range(20)))
got = offer[2]
check("the trade is the one offered", shop.trade_gem_colors(d) == offer)
check("gems moved", (d["gems"]["purple"], d["gems"][got]) == (3, 3), str(d["gems"]))
check("the next costs one more", shop.gem_trade_cost(d) == 3)
check("no trade that leaves the colors worse", shop.gem_trade_offer(d) is None)
day[0] = "2026-10-10"
check("a new day starts at 2 again", shop.gem_trade_cost(d) == 2)
d["gems"] = {"blue": 4, "green": 3, "pink": 1, "purple": 1, "yellow": 1}
check("4 vs 1 trades 2 for 1", (shop.gem_trade_offer(d) or (0, 0))[1] == 2)
d["gems"] = {"blue": 3, "green": 3, "pink": 1, "purple": 1, "yellow": 1}
check("3 vs 1 would end 1 vs 2, so no trade", shop.gem_trade_offer(d) is None)
shop._today_str = _real_today_str


def trade_button(d):
    return next((b for b in d.findChildren(QtWidgets.QPushButton)
                 if any(l.text() == "Trade" for l in b.findChildren(QtWidgets.QLabel))), None)


STATE.clear()
STATE.update(fresh_state())
STATE["gems"] = {"blue": 3, "green": 2, "pink": 2, "purple": 5, "yellow": 2}
d = open_shop()
width_without = d.width()
check("no Trade button without the Prism", trade_button(d) is None and not buttons(d, "Trade ("))
check("craft label is unchanged", bool(buttons(d, "Craft (1 gem of each)")))
d.close()
STATE["owned_collectibles"].append(shop.PRISM_ID)
d = open_shop()
btn = trade_button(d)
check("Trade button shown with the Prism", btn is not None and btn.isEnabled())
check("its gem icons are drawn", btn is not None and sum(1 for l in btn.findChildren(QtWidgets.QLabel) if l.pixmap() and not l.pixmap().isNull()) == 2)
check("the shop keeps its width", d.width() == width_without, f"{d.width()} vs {width_without}")
craft = buttons(d, "Craft")[0]
check("Trade is as tall as Craft", btn is not None and btn.height() == craft.height(), f"{btn.height() if btn else None} vs {craft.height()}")
btn.click()
settle()
check("clicking trades", STATE["gems"]["purple"] == 3, str(STATE["gems"]))
check("then nothing is left to even out", bool(buttons(d, "Trade (nothing to even out)"))
          and not buttons(d, "Trade (nothing to even out)")[0].isEnabled())
d.close()

# A button built before the gems changed must not make a different trade than it names.
STATE["gems"] = {"blue": 3, "green": 2, "pink": 2, "purple": 5, "yellow": 2}
STATE["gem_trade_uses"] = 0  # back to 2 for 1
d = open_shop()
btn = trade_button(d)
STATE["gems"] = {"blue": 6, "green": 1, "pink": 2, "purple": 2, "yellow": 2}
btn.click()
settle()
check("an out-of-date button trades nothing", STATE["gems"]["blue"] == 6 and STATE["gems"]["purple"] == 2,
      str(STATE["gems"]))
fresh_btn = trade_button(d)
check("and is rebuilt to the current trade", fresh_btn is not None and "blue" in fresh_btn.accessibleName(),
      fresh_btn.accessibleName() if fresh_btn else "none")
d.close()

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: " + ", ".join(dict.fromkeys(FAILS)))
    sys.exit(1)
print("all shop UI checks passed")
