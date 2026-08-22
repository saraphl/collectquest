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


def get_version() -> str:
    """Read add-on version from manifest.json."""
    try:
        addon_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        manifest_path = os.path.join(addon_dir, "manifest.json")
        if os.path.isfile(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as f:
                return json.load(f).get("version", "")
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
        # The file exists but could not be read (truncated by a crash mid-write, or written by a
        # version that stored a different format). Returning a default state here means the next
        # save writes an empty game straight over it, so move it aside first — progress is then
        # recoverable by hand instead of being destroyed silently.
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


def reset() -> None:
    """Reset all game progress to default. Deletes current data."""
    save(_default_state())


def _default_state() -> dict[str, Any]:
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
        # Which of today's revlog rows have already been paid out, so a review synced from another
        # device is credited even when its timestamp predates one already handled here. Keyed by
        # scheduler day, so it never holds more than a day of ids. See src/revlog_sync.py.
        "credited_revlog_date": "",  # YYYY-MM-DD the ids below belong to
        "credited_revlog_ids": [],  # revlog ids credited on that day
        "shop_daily_slots": [],  # list of 3 slots: {"type": "collectible", "id": cid} or {"type": "gem", ...}
        "shop_last_refresh_time": 0,  # Unix timestamp of last shop refresh (see get_refresh_interval)
        "shop_refresh_uses": 0,  # total refreshes used (cost = 15 + 15*this)
        "shop_gate_date": "",  # YYYY-MM-DD; 10 reviews needed per day to open shop
        # Last item produced by a gem craft, shown under the Craft button. Persisted so the
        # shop still names it after a restart; cleared by prestige along with the collection.
        "shop_last_crafted_id": None,
        # Clear-the-day quest (see review_rewards.ensure_cleared_bonus_reward). The claim date is
        # cleared by undo so the quest can be re-earned; the reward roll keeps its own date and is
        # not, so undo/redo cannot re-roll it.
        "cleared_bonus_date": "",  # YYYY-MM-DD the quest was last paid
        "cleared_bonus_reward_date": "",  # YYYY-MM-DD the gold-or-gem choice was made
        "cleared_bonus_gem_colors": [],  # colors of the gems that day pays alongside its gold
        # Kept in step with the list above, and load-bearing: _migrate backfills the list into every
        # save, so the bool is what tells a day settled by an older build apart from one that rolled
        # no gems. See review_rewards.cleared_bonus_gem_colors.
        "cleared_bonus_reward_is_gem": False,
        "cleared_bonus_gem_color": None,
        "difficulty": "normal",  # easy/normal/hard; affects XP per review
        "streak_reward_type": None,  # "xp"|"gem"|"gold" for current 7-day window (icon + grant); set when entering that window
        "streak_reward_type_block": -1,  # last 7-day block we set streak_reward_type for; next type chosen when entering new block
        # Lets refresh_streak skip its 400-day revlog scan when nothing can have changed.
        # {"day": scheduler day epoch, "before_today": rows in the window older than today}
        "streak_scan": {},
        "current_streak_start_date": 0,  # first day of current display streak (no reward); 0 = none; reset when broken
        "longest_streak_days": 0,  # longest previous streak (updated only when a streak breaks, if bigger)
        "last_saved_at": "",  # ISO UTC when last written (set on save)
        "saved_with_version": "",  # add-on version when last saved (set on save)
        # Bottom UI (status bar) visibility and order
        "bottom_ui_show_streak": True,
        "bottom_ui_show_level_xp": True,
        "bottom_ui_show_gold_gems": True,
        "bottom_ui_show_quests": True,
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
        "prestige_unlock_prompt_shown": False,  # whether we've shown the level-50 prestige unlock popup
        "onboarding_shown": False,  # whether we've shown the initial welcome/difficulty popup
        "shown_update_popup_for": "0",  # version we last showed the update popup for; "0" = never; set to current after showing once
    }


def _migrate(data: dict[str, Any]) -> dict[str, Any]:
    """
    Merge with defaults: only add missing keys (never overwrite existing).
    So on update, new keys (e.g. current_streak_start_date, longest_streak_days) get default 0.
    Current streak is then recomputed from revlog on first refresh_streak; longest can be
    backfilled from revlog in streak._update_display_streak when 0.
    """
    defaults = _default_state()
    for k, v in defaults.items():
        if k not in data:
            data[k] = v
    # Quests from an older catalog (session_*, tiered reviews_*, correct_5/10) are not rewritten
    # here: rolling a replacement needs the collection for the due baseline, which storage has no
    # access to. quests.ensure_daily_quests swaps them on the next refresh instead.
    # Streak state is not touched here: it is recomputed from revlog in streak.refresh_streak(),
    # which has the collection and so knows the correct day boundary.
    return data
