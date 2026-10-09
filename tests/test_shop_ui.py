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


def drawn_button(d, label):
    """A button whose row of drawn widgets includes a label reading `label`."""
    return next((b for b in d.findChildren(QtWidgets.QPushButton)
                 if any(l.text() == label for l in b.findChildren(QtWidgets.QLabel))), None)


def trade_button(d):
    return drawn_button(d, "Trade")


def drawn_icons(btn):
    return sum(1 for l in btn.findChildren(QtWidgets.QLabel) if l.pixmap() and not l.pixmap().isNull())


STATE.clear()
STATE.update(fresh_state())
STATE["gems"] = {"blue": 3, "green": 2, "pink": 2, "purple": 5, "yellow": 2}
d = open_shop()
width_without = d.width()
check("no Trade button without the Prism", trade_button(d) is None and not buttons(d, "Trade ("))
nxt = shop.get_collectible(STATE["next_craft_id"])
want = f"Craft a level {shop.craft_band_label(nxt)} item ({shop.craft_price_each(nxt)} of each)"
check("craft names the next item's band and price", bool(buttons(d, want)), want)
d.close()
STATE["owned_collectibles"].append(shop.PRISM_ID)
d = open_shop()
btn = trade_button(d)
check("Trade button shown with the Prism", btn is not None and btn.isEnabled())
check("its gem icons are drawn", btn is not None and drawn_icons(btn) == 2)
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

print("\nthe priced craft")
milestones = importlib.import_module("cq.src.milestones")
STATE.clear()
STATE.update(fresh_state())
STATE["gems"] = {"blue": 1, "green": 9, "pink": 9, "purple": 9, "yellow": 9}
# Skull (level 40) costs 2 of each, one more blue than held.
STATE["next_craft_id"] = "skull"
d = open_shop()
craft = buttons(d, "Craft a level 31\u201360 item (2 of each)")
check("a 2-of-each craft names its band", bool(craft))
check("and is disabled with 1 blue", bool(craft) and not craft[0].isEnabled())
d.close()

real_buff_is_active = milestones.buff_is_active
milestones.buff_is_active = lambda data, buff_id, col=None: buff_id == milestones.BUFF_CRAFT_CHEAPER
d = open_shop()
icon_btn = drawn_button(d, "Craft a level 31\u201360 item")
check("the discount buff draws the craft as icons", icon_btn is not None)
icons = drawn_icons(icon_btn) if icon_btn else 0
check("four of them, blue waived", icons == 4 and "blue" not in icon_btn.accessibleName(), str(icons))
check("and enabled, since blue isn't charged", icon_btn is not None and icon_btn.isEnabled())
row_width = icon_btn.layout().sizeHint().width() if icon_btn else 0
check("its text isn't clipped", icon_btn is not None and icon_btn.minimumWidth() >= row_width > 0,
      f"{icon_btn.minimumWidth()} vs {row_width}" if icon_btn else "")
# The panel isn't rebuilt when gems change: a stale button must not charge colors it doesn't show.
STATE["gems"] = {"blue": 9, "green": 9, "pink": 9, "purple": 1, "yellow": 9}
if icon_btn is not None:
    icon_btn.click()
    settle()
check("a stale button crafts nothing", STATE["gems"] == {"blue": 9, "green": 9, "pink": 9, "purple": 1, "yellow": 9}
      and STATE["next_craft_id"] == "skull", str(STATE["gems"]))
STATE["gems"] = {"blue": 1, "green": 9, "pink": 9, "purple": 9, "yellow": 9}
d.close()
d = open_shop()
icon_btn = drawn_button(d, "Craft a level 31\u201360 item")
if icon_btn is not None:
    icon_btn.click()
    settle()
check("crafting charges 2 of each but blue", STATE["gems"] == {"blue": 1, "green": 7, "pink": 7, "purple": 7, "yellow": 7},
      str(STATE["gems"]))
check("and rolls the next", STATE["next_craft_id"] not in (None, "skull"))
milestones.buff_is_active = real_buff_is_active
d.close()

print("\nstale panels")
STATE.clear()
STATE.update(fresh_state())
STATE.update(shop_daily_slots=[{"type": "collectible", "id": "crown"}],
             shop_last_refresh_time=int(QtCore.QDateTime.currentSecsSinceEpoch()))
d = open_shop()
buy = [b for b in buttons(d, "Buy") if b.isEnabled()]
STATE["shop_daily_slots"] = []  # restocked, or a prestige, while the panel stayed open
if buy:
    buy[0].click()
    settle()
check("a stale Buy sells nothing", bool(buy) and "crown" not in STATE["owned_collectibles"]
      and STATE["money"] == 5000, str(STATE["money"]))
d.close()

STATE.clear()
STATE.update(fresh_state())
STATE.update(next_craft_id="skull", gems={c: 9 for c, _ in shop.GEM_COLORS})
d = open_shop()
craft = buttons(d, "Craft a level 31\u201360 item (2 of each)")
STATE["gems"] = {c: 1 for c, _ in shop.GEM_COLORS}  # spent elsewhere, e.g. on a prestige point
if craft:
    craft[0].click()
    settle()
check("a stale Craft it can't pay for crafts nothing", bool(craft) and "skull" not in STATE["owned_collectibles"])
check("and is redrawn disabled", any(not b.isEnabled() for b in buttons(DIALOGS[-1], "Craft a level")))
d.close()

STATE.clear()
STATE.update(fresh_state())
STATE.update(owned_collectibles=[c["id"] for c in shop.shop_supplied_collectibles()])
d = open_shop()
trade = buttons(d, "Trade all gold")
STATE["owned_collectibles"] = STATE["owned_collectibles"][1:]  # a prestige, say, behind the panel
if trade:
    trade[0].click()
    settle()
check("a stale gold trade trades nothing", bool(trade) and STATE["money"] == 5000, str(STATE["money"]))
d.close()

STATE.clear()
STATE.update(fresh_state())
STATE.update(total_xp=0, owned_collectibles=[c["id"] for c in shop.collectibles_for_gems() if c["unlock_at_level"] <= 1])
d = open_shop()
labels = [l.text() for l in d.findChildren(QtWidgets.QLabel)]
check("nothing at this level: only the button says so", bool(buttons(d, "Nothing left to craft at your level"))
      and "Your next craft is priced by its level." not in labels)
d.close()

print("\nthe late-game stages")
supplied = [c["id"] for c in shop.shop_supplied_collectibles()]
craftable = {c["id"] for c in shop.collectibles_for_gems()}
gold_items = {c["id"] for c in shop.collectibles_for_gold()}
stages = (
    ("D, every gold item", [c for c in supplied if c not in ("oath_ring", "hourglass")], True, False),
    ("A, every craftable item", [c for c in supplied if c in craftable or c not in ("lamp_enchanted", "tome_ascent")], False, True),
    ("C, everything", supplied, True, True),
)
for name, owned_ids, gold_trade, gem_trade in stages:
    STATE.clear()
    STATE.update(fresh_state())
    STATE.update(owned_collectibles=list(owned_ids), gems={c: 5 for c, _ in shop.GEM_COLORS})
    d = open_shop()
    check(f"{name}: gold trade {'shown' if gold_trade else 'hidden'}", bool(buttons(d, "Trade all gold")) == gold_trade)
    check(f"{name}: gem trade {'shown' if gem_trade else 'hidden'}", bool(buttons(d, "Trade all gems")) == gem_trade)
    check(f"{name}: Craft only while something is left to craft", bool(buttons(d, "Craft a level")) != gem_trade)
    check(f"{name}: gems still on sale", any(s.get("type") == "gem" for s in STATE["shop_daily_slots"]))
    check(f"{name}: restock still offered", bool(buttons(d, "Restock")))
    check(f"{name}: the Prism trade stays", trade_button(d) is not None or bool(buttons(d, "Trade (nothing")))
    d.close()

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: " + ", ".join(dict.fromkeys(FAILS)))
    sys.exit(1)
print("all shop UI checks passed")
