"""
CollectQuest — lightweight RPG-style progression for Anki (XP, daily quests, collectibles, shop).

Anki imports this module to load the add-on. It deliberately holds no logic: everything lives in
src/, and src/hooks.py owns the wiring into Anki's gui_hooks.
"""
from __future__ import annotations

from .src import hooks

hooks.register()
