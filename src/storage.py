"""Persistent storage for CollectQuest (XP, level, daily quests, unlocks). Stored in profile folder, not add-on folder.
On disk we store the hashsave (base64-encoded canonical JSON) so the raw JSON is never visible."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any

# Will be set by main __init__.py when mw is available
_profile_folder: str | None = None

# Keys we never include in the hash (meta only)
_HASH_KEY = "_hash"


def set_profile_folder(folder: str) -> None:
    global _profile_folder
    _profile_folder = folder


def _path() -> str:
    if _profile_folder is None:
        raise RuntimeError("CollectQuest storage: profile folder not set")
    return os.path.join(_profile_folder, "collectquest.json")


def _canonical_json(obj: dict[str, Any]) -> str:
    """Deterministic JSON for hashing (sort keys, no extra whitespace)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def compute_hash(data: dict[str, Any]) -> str:
    """SHA-256 of the save payload (all keys except _hash)."""
    payload = {k: v for k, v in data.items() if k != _HASH_KEY}
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def encode_to_hashsave(data: dict[str, Any]) -> str:
    """Encode save data to hashsave string (base64 of canonical JSON). Same format as on disk and copy/paste."""
    return base64.b64encode(_canonical_json(data).encode("utf-8")).decode("ascii")


def decode_from_hashsave(blob: str) -> dict[str, Any]:
    """Decode hashsave string to save data. Caller should verify _hash if needed."""
    return json.loads(base64.b64decode(blob).decode("utf-8"))


# Cached manifest version: every load() asks for it, and it cannot change without restarting Anki.
_version_cache: str | None = None


def get_version() -> str:
    """Read add-on version from manifest.json. Cached after the first successful read."""
    global _version_cache
    if _version_cache is not None:
        return _version_cache
    try:
        addon_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        manifest_path = os.path.join(addon_dir, "manifest.json")
        if os.path.isfile(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as f:
                version = json.load(f).get("version", "")
            if version:
                # Only a real version is cached: an unreadable manifest stays retryable rather than
                # pinning every later caller to "".
                _version_cache = version
            return version
    except Exception:
        pass
    return ""


def load() -> dict[str, Any]:
    path = _path()
    if not os.path.isfile(path):
        return _default_state()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = decode_from_hashsave(f.read().strip())
        if _HASH_KEY in data:
            if data[_HASH_KEY] != compute_hash(data):
                data["_hash_invalid"] = True
        return _migrate(data)
    except Exception:
        # Unreadable file (crash mid-write, other format): move it aside, or the next save would
        # silently overwrite it with an empty game.
        _quarantine_unreadable_save(path)
        return _default_state()


def _quarantine_unreadable_save(path: str) -> None:
    """Rename a save we failed to decode, so the next save cannot overwrite it. Never raises."""
    try:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        os.rename(path, f"{path}.unreadable-{stamp}")
    except Exception:
        pass


def save(data: dict[str, Any]) -> None:
    path = _path()
    data.pop("_hash_invalid", None)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data["last_saved_at"] = now
    data["saved_with_version"] = get_version()
    payload = {k: v for k, v in data.items() if k != _HASH_KEY}
    data[_HASH_KEY] = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    with open(path, "w", encoding="utf-8") as f:
        f.write(encode_to_hashsave(data))
        f.flush()
        os.fsync(f.fileno())


# What a progress wipe must not touch: add-on setup and how long the profile has had it
# (streak_floor_epoch, or the streak would drop to a day).
PRESERVED_ON_WIPE_KEYS = (
    "bottom_ui_show_streak",
    "bottom_ui_show_level_xp",
    "bottom_ui_show_gold_gems",
    "bottom_ui_show_quests",
    "bottom_ui_invert_buttons",
    "use_dock_panels",
    "streak_floor_epoch",
    # The milestone unlock notice shows once per profile, surviving prestige and wipe; the dungeon
    # one is in neither list, so it fires each run.
    "milestones_unlock_notice_shown",
)


# A prestige also keeps difficulty, the streak counters and the day's counters (but not
# correct_today, which the quest reads).
PRESERVED_ON_PRESTIGE_KEYS = PRESERVED_ON_WIPE_KEYS + (
    "difficulty",
    "onboarding_shown",
    "streak_rewards_claimed",
    "streak_reward_type",
    "streak_reward_type_block",
    "last_date",
    "reviews_today",
    "shop_gate_date",
    "prestige_unlock_prompt_shown",
    "game_finished_prompt_shown",
    # Dungeons: the auto-pick settings are preferences, and dungeons_claimed is their gate (a run
    # holds fewer than three). An open `dungeon` and `last_dungeon` are dropped with the run.
    "dungeons_claimed",
    "dungeon_auto_pick_enabled",
    "dungeon_auto_pick_order",
)


def _carry(keys: tuple[str, ...], old_data: dict[str, Any], new_data: dict[str, Any]) -> dict[str, Any]:
    """Copy the listed keys from an outgoing save into a freshly built one. Returns new_data."""
    for key in keys:
        if key in old_data:
            new_data[key] = old_data[key]
    return new_data


def carry_preserved_keys(old_data: dict[str, Any], new_data: dict[str, Any]) -> dict[str, Any]:
    """Copy the keys a wipe must not reset. Returns new_data."""
    return _carry(PRESERVED_ON_WIPE_KEYS, old_data, new_data)


def carry_prestige_keys(old_data: dict[str, Any], new_data: dict[str, Any]) -> dict[str, Any]:
    """Copy the keys a prestige must not reset. A superset of carry_preserved_keys."""
    return _carry(PRESERVED_ON_PRESTIGE_KEYS, old_data, new_data)


def reset() -> None:
    """Reset all game progress to default. Deletes current data, but keeps settings (see PRESERVED_ON_WIPE_KEYS)."""
    save(carry_preserved_keys(load(), _default_state()))


def _default_state() -> dict[str, Any]:
    from .dungeon import DEFAULT_AUTO_PICK_ORDER
    from .milestones import default_state as default_milestones
    from .shop import default_gems
    return {
        "total_xp": 0,
        # Sub-1 amounts left over from bonuses, carried to the next award. See src/carry.py.
        "xp_fraction": 0.0,
        "gold_fraction": 0.0,
        "level": 1,
        "last_date": "",  # YYYY-MM-DD
        "daily_quests": [],  # list of { "id", "target", "progress", "reward_xp" }
        "correct_today": 0,  # Good/Easy only today (persists across sessions)
        # Start-of-day due counts, the basis for quest targets. See src/due_baseline.py.
        # {"date": "YYYY-MM-DD", "total": int, "decks": {deck_id: {"name", "due", "filtered"}}}
        "quest_due_baseline": {},
        "reviews_today": 0,  # cards reviewed today; shop unlocks after N
        "unlocked": [],  # list of unlock keys (level-based)
        "money": 0,  # gold from level-up + quests; spent in shop
        "gems": default_gems(),  # blue, green, pink, purple, yellow; 5 of each = 1 collectible
        "owned_collectibles": [],  # collectible ids (bought or gem-crafted)
        "last_processed_revlog_id": 0,  # newest revlog id credited; used to spot an undone review
        # Today's already-paid revlog ids, so older-timestamped synced reviews still get credited.
        # See revlog_sync.py.
        "credited_revlog_date": "",  # YYYY-MM-DD the ids below belong to
        "credited_revlog_ids": [],  # revlog ids credited on that day
        "shop_daily_slots": [],  # list of 3 slots: {"type": "collectible", "id": cid} or {"type": "gem", ...}
        "shop_last_refresh_time": 0,  # Unix timestamp of last shop refresh (see get_refresh_interval)
        "shop_refresh_uses": 0,  # total refreshes used (cost = 15 + 15*this)
        "shop_gate_date": "",  # YYYY-MM-DD; 10 reviews needed per day to open shop
        # Last item produced by a gem craft, shown under the Craft button. Persisted so the
        # shop still names it after a restart; cleared by prestige along with the collection.
        "shop_last_crafted_id": None,
        # Clear-the-day quest (see review_rewards.ensure_cleared_bonus_reward). Undo clears the
        # claim date; the reward roll's date stays, so undo/redo can't reroll it.
        "cleared_bonus_date": "",  # YYYY-MM-DD the quest was last paid
        # Read only while the date above is today, so undo clearing that date unfreezes the row
        # and this needs no undo handling of its own.
        "cleared_bonus_total": 0,  # the objective the quest was paid at
        "cleared_bonus_reward_date": "",  # YYYY-MM-DD the gold-or-gem choice was made
        "cleared_bonus_gem_colors": [],  # colors of the gems that day pays alongside its gold
        # Kept in step with the list above: it tells an older build's settled day from one that
        # rolled no gems. See review_rewards.cleared_bonus_gem_colors.
        "cleared_bonus_reward_is_gem": False,
        "cleared_bonus_gem_color": None,
        # YYYY-MM-DD the day was announced out of reach, so it speaks once; cleared if the cards
        # come back. See due_baseline.cleared_voided.
        "cleared_bonus_void_date": "",
        "difficulty": "normal",  # easy/normal/hard; affects XP per review
        "streak_reward_type": None,  # "xp"|"gem"|"gold" for current 7-day window (icon + grant); set when entering that window
        "streak_reward_type_block": -1,  # last 7-day block we set streak_reward_type for; next type chosen when entering new block
        # First scheduler day this profile ran CollectQuest; the streak can't reach behind it. None
        # until stamped by streak._ensure_streak_floor; older saves get 0.
        "streak_floor_epoch": None,
        "current_streak_start_date": 0,  # first day of current display streak (no reward); 0 = none; reset when broken
        "longest_streak_days": 0,  # longest previous streak (updated only when a streak breaks, if bigger)
        "last_saved_at": "",  # ISO UTC when last written (set on save)
        "saved_with_version": "",  # add-on version when last saved (set on save)
        # Status bar visibility and order. Fresh profiles show only the Level/XP bar; existing saves
        # keep the full bar (see _migrate).
        "bottom_ui_show_streak": False,
        "bottom_ui_show_level_xp": True,
        "bottom_ui_show_gold_gems": False,
        "bottom_ui_show_quests": False,
        "bottom_ui_invert_buttons": False,  # Swap Shop / CollectQuest order (right/left)
        "use_dock_panels": False,  # If True, use drag-and-drop side panels (experimental); else simple popup dialogs
        # Streak rewards
        "streak_rewards_claimed": 0,  # how many 7-day reward windows we've already granted in the current run
        # Prestige (meta-progression across full resets)
        "prestige_count": 0,  # number of times the player has prestiged (for star grid and label)
        "prestige_points_total": 0,  # lifetime prestige points earned
        "pending_prestige_points_from_gems": 0,  # +1 per "3 of each gem" trade; granted on next prestige only
        "prestige_points_spent": 0,  # total points spent on prestige upgrades
        "prestige_upgrades": {  # per-upgrade levels
            "xp_percent": 0,
            "gold_percent": 0,
            "start_gold": 0,
            "streak_bonus": 0,
            "quest_reward": 0,
        },
        # Milestone track: which milestone is active, since when, and its counter. Survives a
        # prestige (see hooks._do_prestige), which is why it is not reset with the rest of the run.
        "milestones": default_milestones(),
        # Dungeons (src/dungeon.py). "dungeon" and "last_dungeon" are absent until there is one:
        # absence means "never started", as it does for the milestone track.
        "dungeons_claimed": 0,  # claimed treasures; unlocks auto-pick at 3, survives a prestige
        "dungeons_claimed_run": 0,  # claimed this run; absent from the preserved keys, so a
                                    # prestige resets it while the lifetime count above carries on
        "milestones_unlock_notice_shown": False,
        "dungeon_unlock_notice_shown": False,
        "dungeon_auto_pick_enabled": False,
        "dungeon_auto_pick_order": list(DEFAULT_AUTO_PICK_ORDER),
        "dungeon_undo_block": 0,  # reviews the dungeon sits out, one per undone review; not a
                                  # preserved key, so a prestige clears the debt with the run
        "dungeon_search_reviews": 0,  # answers spent looking for an entrance, for the pity bonus
        "dungeon_banked_reviews": 0,  # answered while the dungeon was blocked, replayed on unblock
        "dungeon_banked_agains": 0,   # how many of those were Again, which rolls at a fifth
        "prestige_unlock_prompt_shown": False,  # whether we've shown the level-50 prestige unlock popup
        "onboarding_shown": False,  # whether we've shown the initial welcome/difficulty popup
        # Version the update popup last showed for. Fresh profiles start at the current version (the
        # welcome popup introduces them); older saves get "0", see _migrate.
        "shown_update_popup_for": get_version() or "0",
    }


def _migrate(data: dict[str, Any]) -> dict[str, Any]:
    """Merge with defaults, only adding missing keys. Streak fields are then recomputed from revlog
    on the first refresh."""
    # The minimal bottom-UI defaults are for fresh profiles: a save predating these keys has been
    # showing the full bar all along, so backfill it as it was.
    for k in ("bottom_ui_show_streak", "bottom_ui_show_gold_gems", "bottom_ui_show_quests"):
        if k not in data:
            data[k] = True
    # Same for the two first-run popups: an existing player needs no welcome, but did just update.
    if "onboarding_shown" not in data:
        data["onboarding_shown"] = True
    if "shown_update_popup_for" not in data:
        data["shown_update_popup_for"] = "0"
    # 0, not None: an existing player's streak was earned under the add-on, so there is nothing to
    # floor. Only a fresh profile gets today stamped.
    if "streak_floor_epoch" not in data:
        data["streak_floor_epoch"] = 0
    data.pop("streak_scan", None)  # cache of the old 400-day streak scan, no longer kept
    defaults = _default_state()
    for k, v in defaults.items():
        if k not in data:
            data[k] = v
    # Old-catalog quests are swapped by quests.ensure_daily_quests on the next refresh, which has
    # the collection.
    return data
