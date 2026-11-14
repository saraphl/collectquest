"""Standing bonuses by stat, as the windows list them: the collection's own, or every source
summed."""
from __future__ import annotations

from typing import Any

from . import dungeon, review_rewards, shop, streak

# The stats on each of the three gray lines, by their shop.EFFECT_PHRASES key: XP and gold, both
# lucks with the streak bonus, then the dungeon pair, which is long enough to need its own line.
STAT_LINES = (
    ("xp_bonus_percent", "xp_flat", "gold_bonus_percent", "gold_flat"),
    ("luck_gem_chance_percent", "luck_shard_chance_percent", "streak_reward_bonus_percent"),
    ("dungeon_discover_percent", "dungeon_explore_percent"),
)


def item_stats(owned: list, quality: dict | None = None) -> dict[str, float]:
    """What the owned items alone add up to, keyed as shop.EFFECT_PHRASES is. `quality` is
    shop.quality_map."""
    return {key: shop._sum_effect(owned, key, quality) for line in STAT_LINES for key in line}


def total_stats(data: dict[str, Any]) -> dict[str, float]:
    """Items, prestige upgrades, the streak accumulator and a live dungeon pity bonus, summed.
    Temporary buffs stay out: they have their own section and most scale something narrower."""
    owned = data.get("owned_collectibles") or []
    quality = shop.quality_map(data)
    return {
        "xp_bonus_percent": review_rewards.total_xp_bonus_percent(data, owned),
        "xp_flat": shop.xp_flat(owned, quality),  # items are its only source, as for gold_flat
        "gold_bonus_percent": review_rewards.total_gold_bonus_percent(data, owned),
        "gold_flat": shop.gold_flat(owned, quality),
        "luck_gem_chance_percent": review_rewards.gem_luck_percent(data, owned),
        "luck_shard_chance_percent": review_rewards.shard_luck_percent(data, owned),
        "streak_reward_bonus_percent": streak.reward_bonus_percent(data),
        "dungeon_discover_percent": (
            dungeon.discover_bonus_percent(data) + dungeon.discover_pity_percent(data)
        ),
        "dungeon_explore_percent": (
            dungeon.explore_bonus_percent(data) + dungeon.live_explore_pity_percent(data)
        ),
    }
