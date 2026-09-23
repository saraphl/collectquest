"""CollectQuest: RPG-style progression for Anki (XP, daily quests, collectibles, shop). Holds no
logic; src/hooks.py wires everything into Anki."""
from __future__ import annotations

from .src import hooks

hooks.register()
