"""
Check the CollectQuest window's Stats section: that its totals add prestige upgrades, the streak
accumulator and a live dungeon pity bonus to the items' own stats and leave temporary buffs out,
and that the section sits above Items, which keeps only its heading.
Exit 1 = a check failed.

    python3 tests/general/test_stats_section.py
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
dungeon = importlib.import_module("cq.src.dungeon")
milestones = importlib.import_module("cq.src.milestones")
stats = importlib.import_module("cq.src.stats")
shop = importlib.import_module("cq.src.shop")
progress = importlib.import_module("cq.src.ui.progress")

assets.addon_dir = lambda: str(ROOT)
assets._addon_dir_cache = str(ROOT)

FAILS = []
STATE = {}
storage.load = lambda: STATE
storage.save = lambda d: STATE.update(d)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f": {got!r}, want {want!r}"))
    if not ok:
        FAILS.append(label)


def save(**fields):
    d = storage._default_state()
    d.update(fields)
    return d


def picked(data, *keys):
    total = stats.total_stats(data)
    return tuple(round(total[k], 6) for k in keys)


# Stone is +1% XP, Package +3% gem luck, Training shield +12% shard luck, Island +10% streak and
# +2% XP.
ITEMS = ["stone", "package", "training_shield", "island"]

print("totals")
d = save(owned_collectibles=ITEMS)
check("items alone match the Items window's figures",
      stats.total_stats(d), stats.item_stats(ITEMS))

d = save(owned_collectibles=ITEMS, prestige_upgrades={
    "xp_percent": 1, "gold_percent": 2, "quest_reward": 1, "shard_luck": 1,
    "dungeon_discover": 1, "dungeon_explore": 2,
})
check("prestige upgrades add to each stat",
      picked(d, "xp_bonus_percent", "gold_bonus_percent", "luck_gem_chance_percent",
             "luck_shard_chance_percent", "dungeon_discover_percent", "dungeon_explore_percent"),
      (33, 60, 33, 42, 20, 40))

d = save(owned_collectibles=ITEMS, prestige_upgrades={"streak_bonus": 1})
check("the streak upgrade adds to the items", picked(d, "streak_reward_bonus_percent"), (40,))

# Milestone #1 done grants the +5% cap; the charge is stored.
d = save(owned_collectibles=ITEMS)
ms = milestones.get_state(d)
ms.update(started="y", active=2, accumulator_percent=4.0)
check("the accumulator adds to XP only",
      picked(d, "xp_bonus_percent", "gold_bonus_percent"), (7, 0))
ms.update(active=15, magnet_stage=len(milestones.MAGNET_STAGES))
check("and to gold once the last magnet stage is done",
      picked(d, "xp_bonus_percent", "gold_bonus_percent"), (7, 4))

d = save(**{dungeon.KEY_SEARCH_REVIEWS: dungeon.PITY_FLOOR_REVIEWS - 1})
check("no discovery pity below the floor", picked(d, "dungeon_discover_percent"), (0,))
d[dungeon.KEY_SEARCH_REVIEWS] = dungeon.PITY_FLOOR_REVIEWS + dungeon.PITY_STEP_REVIEWS
check("the discovery pity is added",
      picked(d, "dungeon_discover_percent", "dungeon_explore_percent"), (4, 0))

d = save(dungeon={"active": True, "reviews_since_branching": dungeon.PITY_FLOOR_REVIEWS})
check("the exploration pity is added inside a dungeon",
      picked(d, "dungeon_discover_percent", "dungeon_explore_percent"), (0, 2))
d["dungeon"]["pending"] = {"paths": [{"kind": "gold"}]}
check("but not while a branching waits", picked(d, "dungeon_explore_percent"), (0,))
del d["dungeon"]["pending"]
d["dungeon"]["treasure"] = {"claimed": False}
check("nor with the treasure waiting", picked(d, "dungeon_explore_percent"), (0,))

d = save(owned_collectibles=ITEMS)
milestones.get_state(d)["active_buffs"] = [
    {"id": milestones.BUFF_REVIEWS_XP, "started_epoch": 1},
    {"id": milestones.BUFF_DUNGEONS, "started_epoch": 1},
]
check("temporary buffs are running", milestones.buff_is_active(d, milestones.BUFF_REVIEWS_XP), True)
check("and stay out of the totals", stats.total_stats(d), stats.item_stats(ITEMS))

print("\nsection")


# A stat's spaces, hyphen and slash are made non-breaking; compared as plain text.
PLAIN = {0xA0: " ", 0x2060: None}


def panel_texts(data, for_panel=False):
    STATE.clear()
    STATE.update(data)
    root = progress.build_progress_content_widget(None, lambda: None, for_panel=for_panel)
    return [l.text().translate(PLAIN) for l in root.findChildren(QtWidgets.QLabel) if l.text()]


texts = panel_texts(save())
check("hidden with no stats", "Stats" in texts, False)
check("Items is still listed", "Items" in texts, True)

d = save(owned_collectibles=ITEMS, prestige_upgrades={"xp_percent": 1})
d[dungeon.KEY_SEARCH_REVIEWS] = dungeon.PITY_FLOOR_REVIEWS
for for_panel in (False, True):
    where = "dock" if for_panel else "window"
    texts = panel_texts(d, for_panel)
    at, items_at = texts.index("Stats"), texts.index("Items")
    check(f"{where}: the totals follow the Stats heading", texts[at + 1:items_at], [
        "+33% XP",
        "+3% gem luck  ·  +12% shard luck  ·  +10% 7-day streak rewards",
        "+2% chance to find a dungeon",
    ])
    count = f"{len(ITEMS)}/{len(shop.catalog(d))}"
    check(f"{where}: Items keeps only its count",
          (texts[items_at + 1].strip(), [t for t in texts[items_at + 2:] if "%" in t]), (count, []))

print("\nopening size")
docks = importlib.import_module("cq.src.ui.docks")
RESIZED = []


class RecordingDialog(QtWidgets.QDialog):
    """Notes each size the window asks for; offscreen, Qt corrects a too-tall one by itself."""

    def resize(self, *size):
        RESIZED.append(size)
        super().resize(*size)


docks.QDialog = RecordingDialog
OPENED = []
docks.exec_dialog = lambda dialog: (OPENED.append(dialog), dialog.show())
STATE.clear()
STATE.update(d)
docks.show_progress_dialog(None, lambda: None)
for _ in range(5):
    app.processEvents()
width, height = RESIZED[-1]
# Wrapping lines make sizeHint taller than the window needs: it measures a narrower window.
check("opens at the height its content needs at the opening width",
      height, assets.content_height(OPENED[0], width))
check("which is less than the size hint's", height < OPENED[0].sizeHint().height(), True)

sys.exit(1 if FAILS else 0)
