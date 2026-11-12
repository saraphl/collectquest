"""
Build the Items window with PyQt6 standing in for aqt.qt on an offscreen display and check its
header gap and that the Refine buttons line up with Close unless a scrollbar needs the room.
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

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: " + ", ".join(dict.fromkeys(FAILS)))
    sys.exit(1)
print("all Items UI checks passed")
