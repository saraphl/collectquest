"""
Build the milestones window with PyQt6 standing in for aqt.qt on an offscreen display and check that
only granted rewards are in full color and that Close has the CollectQuest window's width.
Exit 1 = a check failed.

    python3 tests/milestones/test_milestones_ui.py
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
milestones = importlib.import_module("cq.src.milestones")
ui_milestones = importlib.import_module("cq.src.ui.milestones")

assets.addon_dir = lambda: str(ROOT)
assets._addon_dir_cache = str(ROOT)

FAILS = []
STATE = {}
storage.load = lambda: STATE
storage.save = lambda d: STATE.update(d)

DIALOGS = []


def _capture(d):
    """Stands in for exec_dialog: show without blocking so the test can read the window."""
    DIALOGS.append(d)
    d.show()
    for _ in range(5):
        app.processEvents()


ui_milestones.exec_dialog = _capture


def check(label, ok, detail=""):
    print(f"  {'ok  ' if ok else 'FAIL'} {label}{': ' + detail if detail else ''}")
    if not ok:
        FAILS.append(label)


ACTIVE = 3  # two granted, one in progress, the rest locked
base_font = app.font()
for pt in (10, 14):
    print(f"\nmilestones window at {pt}pt")
    f = QtGui.QFont(base_font)
    f.setPointSize(pt)
    app.setFont(f)
    STATE.clear()
    STATE.update(storage._default_state())
    STATE.update(total_xp=100_000, milestones={"started": True, "active": ACTIVE})
    ui_milestones.show_milestones_dialog(None)
    d = DIALOGS[-1]

    grid = next(g for g in d.findChildren(QtWidgets.QGridLayout))
    muted = {}
    for i in range(1, milestones.TRACK_LENGTH + 1):
        item = grid.itemAtPosition(i, ui_milestones._COL_REWARD)
        muted[i] = "#888" in item.widget().styleSheet()
    check("granted rewards are in full color", not any(muted[i] for i in range(1, ACTIVE)))
    check("the reward in progress is muted", muted[ACTIVE])
    check("locked rewards are muted",
          all(muted[i] for i in range(ACTIVE + 1, milestones.TRACK_LENGTH + 1)))

    close = next(b for b in d.findChildren(QtWidgets.QPushButton) if b.text() == "Close")
    want = max(close.sizeHint().width(), constants._DIALOG_BUTTON_MIN_WIDTH)
    check("Close has the CollectQuest window's width", close.width() == want, f"{close.width()} vs {want}")
    d.close()

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: " + ", ".join(dict.fromkeys(FAILS)))
    sys.exit(1)
print("all milestones UI checks passed")
