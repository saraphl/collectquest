"""
Drive the in-window hover tips with synthetic Enter/Leave events on an offscreen display.
Exit 1 = a check failed.

    python3 tests/test_hover_tip.py
"""
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
from PyQt6.QtTest import QTest

qt = types.ModuleType("aqt.qt")
for src in (QtCore, QtGui, QtWidgets):
    for name in dir(src):
        if name.startswith("Q") or name == "Qt":
            setattr(qt, name, getattr(src, name))
sys.modules["aqt.qt"] = qt

aqt = types.ModuleType("aqt")
aqt.mw = None
aqt.qt = qt
sys.modules["aqt"] = aqt
theme = types.ModuleType("aqt.theme")
theme.theme_manager = types.SimpleNamespace(night_mode=False)
sys.modules["aqt.theme"] = theme
for name in ("aqt.utils", "anki", "anki.collection"):
    mod = types.ModuleType(name)
    mod.__getattr__ = lambda n: (lambda *a, **k: None)
    sys.modules.setdefault(name, mod)

pkg = types.ModuleType("cq")
pkg.__path__ = [str(ROOT)]
sys.modules["cq"] = pkg

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
ht = importlib.import_module("cq.src.ui.hover_tip")
constants = importlib.import_module("cq.src.ui.constants")

FAILS = []


def check(label, ok):
    print(f"  {'ok  ' if ok else 'FAIL'} {label}")
    if not ok:
        FAILS.append(label)


def enter(w):
    p = QtCore.QPointF(3, 3)
    app.sendEvent(w, QtGui.QEnterEvent(p, p, w.mapToGlobal(p)))
    app.processEvents()


def leave(w):
    app.sendEvent(w, QtCore.QEvent(QtCore.QEvent.Type.Leave))
    app.processEvents()


def tip(win):
    t = win.findChild(ht._HoverTip)
    return (t.text() if t is not None and t.isVisible() else None), t


def delete(w):
    w.deleteLater()
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete.value)
    app.processEvents()


def settle():
    """Past the fall-asleep window, so the next Enter waits for the wake-up delay again."""
    QTest.qWait(int(ht._filter()._asleep_s * 1000) + 200)


win = QtWidgets.QWidget()
win.resize(500, 300)
lay = QtWidgets.QVBoxLayout(win)
a, b = QtWidgets.QLabel("A"), QtWidgets.QPushButton("B")
row = QtWidgets.QWidget()
row_l = QtWidgets.QHBoxLayout(row)
inner = QtWidgets.QLabel("inner")
row_l.addWidget(inner)
for w in (a, b, row):
    lay.addWidget(w)
ht.set_hover_tip(a, "tip A")
ht.set_hover_tip(b, "tip B")
ht.set_hover_tip(row, "row tip")
ht.set_hover_tip(inner, "inner tip")
win.show()
app.processEvents()
wake = ht._filter()._wake_ms

print("timing")
enter(a)
check("waits for the wake-up delay", tip(win)[0] is None)
QTest.qWait(wake + 100)
check("shows after it", tip(win)[0] == "tip A")
QTest.qWait(3000)
check("still up after 3s", tip(win)[0] == "tip A")
leave(a)
check("hides on leave", tip(win)[0] is None)
enter(b)
check("next one shows at once", tip(win)[0] == "tip B")
leave(b)
settle()

print("\nnesting")
enter(row)
QTest.qWait(wake + 100)
enter(inner)
check("child's tip replaces the parent's", tip(win)[0] == "inner tip")
QtGui.QCursor.setPos(row.mapToGlobal(QtCore.QPoint(1, 1)))
leave(inner)
check("back on the parent: its tip returns", tip(win)[0] == "row tip")
leave(row)
settle()

print("\ndeleted widgets")
enter(b)
QTest.qWait(wake + 100)
delete(b)
check("hides when its widget is deleted", tip(win)[0] is None)
enter(a)
check("works afterwards", tip(win)[0] == "tip A")
leave(a)
w2 = QtWidgets.QWidget()
c = QtWidgets.QLabel("C", w2)
ht.set_hover_tip(c, "tip C")
w2.show()
enter(c)
delete(w2)
enter(a)
check("survives its window being deleted", tip(win)[0] == "tip A")
leave(a)
settle()

print("\npending tip")
enter(a)
leave(a)
QTest.qWait(wake + 100)
check("left before the delay: never shows", tip(win)[0] is None)
settle()

print("\ndragging")
press_at = a.mapTo(win, QtCore.QPoint(3, 3))
QTest.mousePress(win.windowHandle(), QtCore.Qt.MouseButton.LeftButton, pos=press_at)
enter(a)
QTest.qWait(wake + 100)
check("no tip while a button is held", tip(win)[0] is None)
QTest.mouseRelease(win.windowHandle(), QtCore.Qt.MouseButton.LeftButton, pos=press_at)
leave(a)
settle()

print("\ntext and theme")
ht.set_hover_tip(a, "Daily quests:\n  Review <N5> & more: 0/10")
enter(a)
QTest.qWait(wake + 100)
text, t = tip(win)
check("plain text kept as is", text == "Daily quests:\n  Review <N5> & more: 0/10")
check("two lines tall", t is not None and t.height() > 2 * t.fontMetrics().height())
check("light colors", t is not None and constants._HOVER_TIP_COLORS_LIGHT[0] in t.styleSheet())
leave(a)
theme.theme_manager.night_mode = True
enter(a)
check("dark colors after a theme switch", constants._HOVER_TIP_COLORS_DARK[0] in tip(win)[1].styleSheet())
leave(a)
settle()

print("\nplacement")
big = QtWidgets.QMainWindow()
big.resize(900, 500)
big.setCentralWidget(QtWidgets.QTextEdit())
bottom = QtWidgets.QPushButton("Shop")
big.statusBar().addPermanentWidget(bottom)
ht.set_hover_tip(bottom, "x" * 200)
big.show()
app.processEvents()
enter(bottom)
QTest.qWait(wake + 100)
_, t = tip(big)
g = t.geometry() if t is not None else QtCore.QRect()
anchor_top = bottom.mapTo(big, QtCore.QPoint(0, 0)).y()
check("above an anchor at the window's bottom", t is not None and g.bottom() < anchor_top)
check("inside the window and capped in width", g.left() >= 0 and g.right() < big.width() and g.width() <= ht._MAX_WIDTH)
leave(bottom)

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: " + ", ".join(FAILS))
    sys.exit(1)
print("all hover tip checks passed")
