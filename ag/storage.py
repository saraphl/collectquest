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

# First version that writes hashsave on disk (1.0.10). Older saves in JSON are converted on load.
_HASHSAVE_FROM_VERSION = (1, 0, 10)


def _parse_version(s: str) -> tuple[int, int, int]:
    """Parse '1.0.9' -> (1, 0, 9). Invalid/empty -> (0, 0, 0)."""
    if not s or not s.strip():
        return (0, 0, 0)
    parts = s.strip().split(".")
    try:
        major = int(parts[0]) if len(parts) > 0 else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
        return (major, minor, patch)
    except (ValueError, IndexError):
        return (0, 0, 0)


def _version_before(a: tuple[int, int, int], b: tuple[int, int, int]) -> bool:
    """True if a is strictly before b."""
    return a < b


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


def version_less(s: str, t: str) -> bool:
    """True if version s is strictly before version t (e.g. '1.0.20' < '1.1.1')."""
    return _version_before(_parse_version(s or ""), _parse_version(t or ""))


def load() -> dict[str, Any]:
    path = _path()
    if not os.path.isfile(path) and _profile_folder:
        # Migrate from legacy ankigame.json if present
        legacy = os.path.join(_profile_folder, "ankigame.json")
        if os.path.isfile(legacy):
            try:
                with open(legacy, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data = _migrate(data)
                save(data)
                return data
            except Exception:
                pass
    if not os.path.isfile(path):
        return _default_state()
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read().strip()
        from_json = raw.startswith("{")
        if from_json:
            data = json.loads(raw)
        else:
            data = decode_from_hashsave(raw)
        if _HASH_KEY in data:
            expected = data[_HASH_KEY]
            actual = compute_hash(data)
            if expected != actual:
                data["_hash_invalid"] = True
        data = _migrate(data)
        # Convert old JSON saves (1.0.9 or before) to hashsave on first load with 1.0.10+
        if from_json:
            saved_ver = _parse_version(data.get("saved_with_version", "") or "")
            if _version_before(saved_ver, _HASHSAVE_FROM_VERSION):
                save(data)
        return data
    except Exception:
        return _default_state()


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
    from .shop import default_gems
    return {
        "total_xp": 0,
        "level": 1,
        "last_date": "",  # YYYY-MM-DD
        "daily_xp": 0,
        "daily_quests": [],  # list of { "id", "target", "progress", "reward_xp" }
        "correct_today": 0,  # Good/Easy only today (persists across sessions)
        "reviews_today": 0,  # cards reviewed today; shop unlocks after N
        "unlocked": [],  # list of unlock keys (level-based)
        "money": 0,  # gold from level-up + quests; spent in shop
        "gems": default_gems(),  # blue, green, pink, purple, yellow; 5 of each = 1 collectible
        "owned_collectibles": [],  # collectible ids (bought or gem-crafted)
        "last_processed_revlog_id": 0,  # max revlog id we've applied (desktop + synced); avoids double-counting
        "shop_daily_slots": [],  # list of 3 slots: {"type": "collectible", "id": cid} or {"type": "gem", ...}
        "shop_last_refresh_time": 0,  # Unix timestamp of last shop refresh (auto-refreshes every hour)
        "shop_refresh_uses": 0,  # total refreshes used (cost = 15 + 15*this)
        "shop_gate_date": "",  # YYYY-MM-DD; 10 reviews needed per day to open shop
        "difficulty": "normal",  # easy/normal/hard; affects XP per review
        "streak_start_date": 0,  # legacy key (kept for backward compat); current streak uses current_streak_start_date/end_date
        "streak_reward_type": None,  # "xp"|"gem"|"gold" for current 7-day window (icon + grant); set when entering that window
        "streak_reward_type_block": -1,  # last 7-day block we set streak_reward_type for; next type chosen when entering new block
        "current_streak_start_date": 0,  # first day of current display streak (no reward); 0 = none; reset when broken
        "longest_streak_days": 0,  # longest previous streak (updated only when a streak breaks, if bigger)
        "last_saved_at": "",  # ISO UTC when last written (set on save)
        "saved_with_version": "",  # add-on version when last saved (set on save)
        "review_prompt_trigger_level": None,  # level at which to show "Do you enjoy CollectQuest?" once; 20 or (level+2) for existing 20+
        "review_prompt_shown_at_level": None,  # set when we've shown the prompt so we never show again
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
        "prestige_unlock_prompt_shown": False,  # whether we've shown the level-50 prestige unlock popup
        "onboarding_shown": False,  # whether we've shown the initial welcome/difficulty popup
        "shown_update_popup_for": "0",  # version we last showed the update popup for; "0" = never; set to current after showing once
    }


def _migrate_in_a_row_quests(data: dict[str, Any]) -> None:
    """Replace old 'correct_5' / 'correct_10' (in a row) quests with a brand-new 'correct today' quest. No transfer."""
    from . import quests
    daily_quests = data.get("daily_quests", [])
    difficulty = data.get("difficulty", "normal")
    for i in range(len(daily_quests)):
        if daily_quests[i].get("id") in ("correct_5", "correct_10"):
            daily_quests[i] = quests.roll_one_correct_today_quest(difficulty)


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
    _migrate_in_a_row_quests(data)
    # Streak: drop old fake days. Do NOT convert streak_days here (we don't have col → wrong "today").
    # Conversion happens in streak.refresh_streak() using today_epoch(col) so the 7-day window is correct.
    data.pop("streak_fake_days", None)
    return data
