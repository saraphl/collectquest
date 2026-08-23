"""
Shop, gems, and collectibles.

- Shop: 3 random slots per day. Each slot can be a collectible (gold at level) OR one of 6 gem options (5 colors at 25–50g, or "1 random gem" at 30g). So gems can appear instead of one of the 3 daily items. Optional refresh (key-unlocked).
- Gems: 5 colors. Obtained on level-up, quest complete, or buy from a daily slot when it's a gem. Spend 5 gems → one random collectible you are already high enough level to unlock (never above your level).
- Gold: from level-up + daily quests. Spent on today's 3 slots (collectibles or gems) or refresh.
- Keys (bronze/silver/gold): special collectibles; can unlock pay-to-refresh or free refresh (later).
"""
from __future__ import annotations

import random
from datetime import datetime
from typing import Any

# Shop unlocks after this many reviews today
SHOP_MIN_REVIEWS = 10

# Daily shop: this many random items (gold-purchasable at level)
SHOP_ITEMS_PER_DAY = 3  # Base count; milestone #7 raises it. See shop_slot_count().

# Daily shop: 3 slots. Each slot is either a collectible OR one gem option (in the same pool).
# The three gem options are priced by how much say the player gets over the color, and the ladder
# has to be monotone: a named color is never worse than a random one, since you know what you are
# buying before you spend, so it must never cost less. The prices these replaced were rolled over
# 20-50g, which undercut the random gem two rolls in seven.
GEM_COST_RANDOM = 30       # color decided on purchase
GEM_COST_SPECIFIC = 45     # a color the shop names
GEM_COST_MOST_NEEDED = 60  # the color the player holds fewest of

# Refresh (unlocked by owning a key): 1 free per day (2 with Golden Key), then 15g first paid, +15g per use.
REFRESH_COST_BASE = 15
REFRESH_COST_INCREMENT = 15

# Shop auto-refresh interval (seconds): depends on owned keys
# The wait everyone gets, key or not. Named DEFAULT rather than BRONZE because no key is
# required for it — the old name implied the Bronze Key granted it, which it never did.
SHOP_REFRESH_INTERVAL_DEFAULT = 14400  # 4 hours (no key needed)
SHOP_REFRESH_INTERVAL_SILVER = 7200   # 2 hours (Silver Key upgrade)

# Key collectible ids and their effects
KEY_BRONZE_ID = "key_bronze"  # Unlocks refresh (2h cooldown)
KEY_SILVER_ID = "key_silver"  # Halves the auto-refresh wait to 2h
KEY_GOLD_ID = "key_gold"      # 2 free refreshes per day (others: 1 free/day)

# Gem color -> image path (under images/)
GEM_COLORS: list[tuple[str, str]] = [
    ("blue", "gems/Gem - Blue.png"),
    ("green", "gems/Gem - Green.png"),
    ("pink", "gems/Gem - Pink.png"),
    ("purple", "gems/Gem - Purple.png"),
    ("yellow", "gems/Gem - Yellow.png"),
]

# Collectible: id, name, image, cost_gold (None = no gold price), unlock_with_gems, unlock_at_level, effect, effect_description, rarity.
# Better spread: same items/costs as original; unlock levels moved UP with gaps (no item every level). End game stays high (55/65/75/85).
# Bag, Star, Ticket are UI-only (not in this list). See docs/ITEMS_AND_ATTRIBUTES.md.
COLLECTIBLES: list[dict[str, Any]] = [
    # ============ EARLY — Level 1, then gaps; unlocks at 1, 5, 8, 10, 14 ============
    {"id": "stone", "name": "Stone", "image": "collectibles/equip_icon_stone.png", "cost_gold": 32, "unlock_with_gems": True, "unlock_at_level": 1, "effect": {"xp_flat": 1}, "effect_description": "+1 XP/review", "rarity": "common"},
    {"id": "cup", "name": "Cup", "image": "collectibles/Cup.png", "cost_gold": 25, "unlock_with_gems": True, "unlock_at_level": 1, "effect": {"gold_flat": 2}, "effect_description": "+2g earned", "rarity": "common"},
    {"id": "bracelet", "name": "Bracelet", "image": "collectibles/equip_icon_bracelet.png", "cost_gold": 40, "unlock_with_gems": True, "unlock_at_level": 1, "effect": {"gold_flat": 2, "xp_bonus_percent": 1}, "effect_description": "+2g earned, +1% XP", "rarity": "common"},
    {"id": "fish", "name": "Fish", "image": "collectibles/equip_icon_fish.png", "cost_gold": 42, "unlock_with_gems": True, "unlock_at_level": 1, "effect": {"luck_gem_chance_percent": 5}, "effect_description": "+5% gem luck", "rarity": "common"},
    {"id": "potion_red_0", "name": "Red Potion", "image": "collectibles/equip_icon_potion_red_0.png", "cost_gold": 40, "unlock_with_gems": True, "unlock_at_level": 1, "effect": {"xp_bonus_percent": 2}, "effect_description": "+2% XP", "rarity": "common"},
    {"id": "package", "name": "Package", "image": "collectibles/Package.png", "cost_gold": 28, "unlock_with_gems": True, "unlock_at_level": 1, "effect": {"luck_gem_chance_percent": 3}, "effect_description": "+3% gem luck", "rarity": "common"},
    # --- Level 5 (gap 2–4) ---
    {"id": "hard_tooth", "name": "Hard Tooth", "image": "collectibles/equip_icon_hard_tooth.png", "cost_gold": 45, "unlock_with_gems": True, "unlock_at_level": 5, "effect": {"gold_flat": 3}, "effect_description": "+3g earned", "rarity": "common"},
    {"id": "poison_tooth", "name": "Poison Tooth", "image": "collectibles/equip_icon_posion_tooth.png", "cost_gold": 50, "unlock_with_gems": True, "unlock_at_level": 5, "effect": {"luck_gem_chance_percent": 5}, "effect_description": "+5% gem luck", "rarity": "common"},
    {"id": "tooth_red", "name": "Red Teeth", "image": "collectibles/equip_icon_teeth_red.png", "cost_gold": 48, "unlock_with_gems": True, "unlock_at_level": 5, "effect": {"gold_flat": 2, "gold_bonus_percent": 2}, "effect_description": "+2g earned, +2% gold", "rarity": "common"},
    {"id": "potion_blue_0", "name": "Blue Potion", "image": "collectibles/equip_icon_potion_blue_0.png", "cost_gold": 55, "unlock_with_gems": True, "unlock_at_level": 5, "effect": {"xp_flat": 1}, "effect_description": "+1 XP/review", "rarity": "common"},
    # --- Level 8 (gap 6–7) ---
    {"id": "crystal", "name": "Crystal", "image": "collectibles/equip_icon_cyristal.png", "cost_gold": 65, "unlock_with_gems": True, "unlock_at_level": 8, "effect": {"xp_flat": 2}, "effect_description": "+2 XP/review", "rarity": "common"},
    {"id": "axe", "name": "Axe", "image": "collectibles/equip_icon_axe_0.png", "cost_gold": 60, "unlock_with_gems": True, "unlock_at_level": 8, "effect": {"xp_bonus_percent": 2, "gold_bonus_percent": 1}, "effect_description": "+2% XP, +1% gold", "rarity": "common"},
    {"id": "leaf", "name": "Leaf", "image": "collectibles/equip_icon_leaf.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 8, "effect": {"luck_gem_chance_percent": 6}, "effect_description": "+6% gem luck", "rarity": "rare"},
    {"id": "shield_wood", "name": "Wood Shield", "image": "collectibles/equip_icon_shield_wood.png", "cost_gold": 70, "unlock_with_gems": True, "unlock_at_level": 8, "effect": {"luck_gem_chance_percent": 2, "gold_flat": 1}, "effect_description": "+2% gem luck, +1g earned", "rarity": "common"},
    # --- Level 10 ---
    {"id": "hammer", "name": "Hammer", "image": "collectibles/equip_icon_hammer_0.png", "cost_gold": 80, "unlock_with_gems": True, "unlock_at_level": 10, "effect": {"gold_flat": 4}, "effect_description": "+4g earned", "rarity": "common"},
    {"id": "potion_red_1", "name": "Red Potion II", "image": "collectibles/equip_icon_potion_red_1.png", "cost_gold": 75, "unlock_with_gems": True, "unlock_at_level": 10, "effect": {"xp_bonus_percent": 3}, "effect_description": "+3% XP", "rarity": "common"},
    # --- Level 12 ---
    {"id": "key_bronze", "name": "Bronze Key", "image": "collectibles/icon_key_bronze.png", "cost_gold": 120, "unlock_with_gems": True, "unlock_at_level": 12, "effect": {}, "effect_description": "Unlocks manual shop refresh: 1 free/day, then 15g+", "rarity": "common"},
    {"id": "axe_1", "name": "Strong Axe", "image": "collectibles/equip_icon_axe_1.png", "cost_gold": 95, "unlock_with_gems": True, "unlock_at_level": 14, "effect": {"xp_bonus_percent": 2, "gold_bonus_percent": 2}, "effect_description": "+2% XP, +2% gold", "rarity": "common"},
    {"id": "hammer_1", "name": "Strong Hammer", "image": "collectibles/equip_icon_hammer_1.png", "cost_gold": 120, "unlock_with_gems": True, "unlock_at_level": 16, "effect": {"gold_flat": 4, "gold_bonus_percent": 5}, "effect_description": "+4g earned, +5% gold", "rarity": "common"},
    {"id": "potion_blue_1", "name": "Blue Potion II", "image": "collectibles/equip_icon_potion_blue_1.png", "cost_gold": 105, "unlock_with_gems": True, "unlock_at_level": 14, "effect": {"xp_flat": 2}, "effect_description": "+2 XP/review", "rarity": "common"},

    # ============ MID — 18, 22, 26, 30, 35 ============
    {"id": "ring_blue", "name": "Blue Ring", "image": "collectibles/equip_icon_ring_blue.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 18, "effect": {"xp_bonus_percent": 4, "xp_flat": 1}, "effect_description": "+4% XP, +1 XP/review", "rarity": "rare"},
    {"id": "cloverleaf", "name": "Lucky Clover", "image": "collectibles/Cloverleaf.png", "cost_gold": 333, "unlock_with_gems": True, "unlock_at_level": 18, "effect": {"luck_gem_chance_percent": 10}, "effect_description": "+10% gem luck", "rarity": "rare"},
    {"id": "axe_2", "name": "Great Axe", "image": "collectibles/equip_icon_axe_2.png", "cost_gold": 150, "unlock_with_gems": True, "unlock_at_level": 22, "effect": {"xp_bonus_percent": 4, "gold_bonus_percent": 3}, "effect_description": "+4% XP, +3% gold", "rarity": "rare"},
    {"id": "hammer_2", "name": "Great Hammer", "image": "collectibles/equip_icon_hammer_2.png", "cost_gold": 190, "unlock_with_gems": True, "unlock_at_level": 24, "effect": {"gold_bonus_percent": 8}, "effect_description": "+8% gold", "rarity": "rare"},
    {"id": "potion_red_2", "name": "Red Potion III", "image": "collectibles/equip_icon_potion_red_2.png", "cost_gold": 145, "unlock_with_gems": True, "unlock_at_level": 22, "effect": {"xp_bonus_percent": 5}, "effect_description": "+5% XP", "rarity": "rare"},
    {"id": "key_silver", "name": "Silver Key", "image": "collectibles/icon_key_silver.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 22, "effect": {}, "effect_description": "Shop auto-refresh every 2 hours instead of 4", "rarity": "rare"},
    {"id": "island", "name": "Island", "image": "collectibles/Island.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 26, "effect": {"streak_reward_bonus_percent": 15}, "effect_description": "+15% 7-day streak rewards", "rarity": "rare"},
    {"id": "dragon_tooth", "name": "Dragon Teeth", "image": "collectibles/equip_icon_dragon_teeth.png", "cost_gold": 200, "unlock_with_gems": True, "unlock_at_level": 26, "effect": {"luck_gem_chance_percent": 8}, "effect_description": "+8% gem luck", "rarity": "rare"},
    {"id": "potion_blue_2", "name": "Blue Potion III", "image": "collectibles/equip_icon_potion_blue_2.png", "cost_gold": 231, "unlock_with_gems": True, "unlock_at_level": 26, "effect": {"xp_flat": 3}, "effect_description": "+3 XP/review", "rarity": "rare"},
    {"id": "ring_gold", "name": "Gold Ring", "image": "collectibles/equip_icon_ring_gold.png", "cost_gold": 250, "unlock_with_gems": True, "unlock_at_level": 30, "effect": {"gold_bonus_percent": 10}, "effect_description": "+10% gold", "rarity": "rare"},
    {"id": "coins_chest", "name": "Coin Chest", "image": "currency/Coins - Chest.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 30, "effect": {"gold_flat": 8, "gold_bonus_percent": 5}, "effect_description": "+8g earned, +5% gold", "rarity": "rare"},
    {"id": "axe_3", "name": "Epic Axe", "image": "collectibles/equip_icon_axe_3.png", "cost_gold": 290, "unlock_with_gems": True, "unlock_at_level": 35, "effect": {"xp_bonus_percent": 6, "gold_bonus_percent": 4}, "effect_description": "+6% XP, +4% gold", "rarity": "epic"},
    {"id": "potion_red_3", "name": "Red Potion IV", "image": "collectibles/equip_icon_potion_red_3.png", "cost_gold": 280, "unlock_with_gems": True, "unlock_at_level": 35, "effect": {"xp_bonus_percent": 8}, "effect_description": "+8% XP", "rarity": "epic"},

    # ============ LATE — 40, 45, 50 ============
    {"id": "hammer_3", "name": "Epic Hammer", "image": "collectibles/equip_icon_hammer_3.png", "cost_gold": 300, "unlock_with_gems": True, "unlock_at_level": 40, "effect": {"gold_bonus_percent": 12}, "effect_description": "+12% gold", "rarity": "epic"},
    {"id": "skull", "name": "Skull", "image": "collectibles/Skull (Border).png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 40, "effect": {"gold_bonus_percent": 10, "luck_gem_chance_percent": 10}, "effect_description": "+10% gold, +10% gem luck", "rarity": "rare"},
    {"id": "sword", "name": "Sword", "image": "collectibles/Sword (Border).png", "cost_gold": 350, "unlock_with_gems": True, "unlock_at_level": 45, "effect": {"luck_gem_chance_percent": 16}, "effect_description": "+16% gem luck", "rarity": "epic"},
    {"id": "potion_blue_3", "name": "Blue Potion IV", "image": "collectibles/equip_icon_potion_blue_3.png", "cost_gold": 374, "unlock_with_gems": True, "unlock_at_level": 45, "effect": {"xp_flat": 4}, "effect_description": "+4 XP/review", "rarity": "epic"},
    {"id": "key_gold", "name": "Golden Key", "image": "collectibles/icon_key_gold.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 45, "effect": {}, "effect_description": "2 free manual shop refreshes per day instead of 1", "rarity": "epic"},
    {"id": "cup_border", "name": "Trophy Cup", "image": "collectibles/Cup (Border).png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 50, "effect": {"gold_bonus_percent": 15}, "effect_description": "+15% gold", "rarity": "epic"},
    {"id": "eye_blue", "name": "Void's Eye", "image": "collectibles/equip_icon_eye_blue.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 50, "effect": {"xp_bonus_percent": 6, "gold_bonus_percent": 6, "luck_gem_chance_percent": 10}, "effect_description": "+6% XP, +6% gold, +10% gem luck", "rarity": "epic"},
    {"id": "gem_red", "name": "Red Gem", "image": "collectibles/equip_icon_gem_red.png", "cost_gold": 400, "unlock_with_gems": True, "unlock_at_level": 50, "effect": {"streak_reward_bonus_percent": 20}, "effect_description": "+20% 7-day streak rewards", "rarity": "rare"},
    {"id": "potion_red_4", "name": "Red Potion V", "image": "collectibles/equip_icon_potion_red_4.png", "cost_gold": 420, "unlock_with_gems": True, "unlock_at_level": 55, "effect": {"xp_bonus_percent": 10}, "effect_description": "+10% XP", "rarity": "epic"},
    {"id": "potion_blue_4", "name": "Blue Potion V", "image": "collectibles/equip_icon_potion_blue_4.png", "cost_gold": 473, "unlock_with_gems": True, "unlock_at_level": 55, "effect": {"xp_flat": 5}, "effect_description": "+5 XP/review", "rarity": "epic"},
    {"id": "shield_blue", "name": "Blue Shield", "image": "collectibles/equip_icon_shield_blue.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 55, "effect": {"luck_gem_chance_percent": 40}, "effect_description": "+40% gem luck", "rarity": "epic"},

    # ============ END GAME — 60, 70, 80, 85 (moved UP, never down) ============
    {"id": "palm_tree", "name": "Palm Tree", "image": "collectibles/Palm Tree.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 60, "effect": {"gold_flat": 8}, "effect_description": "+8g earned", "rarity": "rare"},
    {"id": "crown", "name": "Crown", "image": "collectibles/Crown.png", "cost_gold": 500, "unlock_with_gems": True, "unlock_at_level": 60, "effect": {"xp_bonus_percent": 4, "gold_bonus_percent": 8}, "effect_description": "+4% XP, +8% gold", "rarity": "rare"},
    {"id": "shield", "name": "Shield", "image": "collectibles/Shield.png", "cost_gold": 550, "unlock_with_gems": True, "unlock_at_level": 70, "effect": {"xp_bonus_percent": 8, "gold_bonus_percent": 4}, "effect_description": "+8% XP, +4% gold", "rarity": "rare"},
    {"id": "gemstone", "name": "Gemstone", "image": "collectibles/icon_gemstone.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 70, "effect": {"gold_bonus_percent": 12, "luck_gem_chance_percent": 13}, "effect_description": "+12% gold, +13% gem luck", "rarity": "epic"},
    {"id": "hammer_4", "name": "Legendary Hammer", "image": "collectibles/equip_icon_hammer_4.png", "cost_gold": 580, "unlock_with_gems": True, "unlock_at_level": 80, "effect": {"gold_bonus_percent": 18}, "effect_description": "+18% gold", "rarity": "epic"},
    {"id": "gemstone_rune", "name": "Rune Gemstone", "image": "collectibles/icon_gemstone_rune.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 80, "effect": {"xp_bonus_percent": 10, "gold_bonus_percent": 10}, "effect_description": "+10% XP, +10% gold", "rarity": "epic"},
    {"id": "axe_4", "name": "Legendary Axe", "image": "collectibles/equip_icon_axe_4.png", "cost_gold": 800, "unlock_with_gems": True, "unlock_at_level": 85, "effect": {"xp_bonus_percent": 15, "gold_bonus_percent": 5}, "effect_description": "+15% XP, +5% gold", "rarity": "epic"},
    # ============ VERY LATE GAME — 65+ (many gold-only, no gem craft) ============
    {"id": "meat_feast", "name": "Meat Feast", "image": "collectibles/icon_food_meat.png", "cost_gold": 380, "unlock_with_gems": False, "unlock_at_level": 65, "effect": {"xp_flat": 2, "gold_flat": 3}, "effect_description": "+2 XP/review, +3g earned (gold-only)", "rarity": "rare"},
    {"id": "shield_reinf", "name": "Reinforced Shield", "image": "collectibles/icon_equip_shield.png", "cost_gold": 650, "unlock_with_gems": False, "unlock_at_level": 78, "effect": {"gold_bonus_percent": 8, "xp_bonus_percent": 4}, "effect_description": "+8% gold, +4% XP (gold-only)", "rarity": "epic"},
    {"id": "arrow_sharp", "name": "Falcon Bow", "image": "collectibles/icon_equip_arrow.png", "cost_gold": 520, "unlock_with_gems": True, "unlock_at_level": 72, "effect": {"luck_gem_chance_percent": 24}, "effect_description": "+24% gem luck", "rarity": "epic"},
    {"id": "lucky_necklace", "name": "Lucky Necklace", "image": "collectibles/icon_accessories_necklace.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 78, "effect": {"xp_bonus_percent": 2, "gold_bonus_percent": 2}, "effect_description": "+2% XP, +2% gold", "rarity": "epic"},
    {"id": "tome_begin", "name": "Tome of Beginnings", "image": "collectibles/icon_book_0.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 90, "effect": {"prestige_bonus_points": 1}, "effect_description": "+1 prestige point per prestige", "rarity": "legendary"},
    {"id": "candle_focus", "name": "Candle of Focus", "image": "collectibles/icon_candle.png", "cost_gold": 750, "unlock_with_gems": False, "unlock_at_level": 90, "effect": {"luck_gem_chance_percent": 32}, "effect_description": "+32% gem luck (gold-only)", "rarity": "legendary"},
    {"id": "piggy_bank", "name": "Piggy Bank", "image": "collectibles/icon_piggy.png", "cost_gold": 900, "unlock_with_gems": False, "unlock_at_level": 95, "effect": {"gold_flat": 5, "gold_bonus_percent": 10}, "effect_description": "+5g earned, +10% gold (gold-only)", "rarity": "legendary"},
    {"id": "tome_ascent", "name": "Chronicle of Ascension", "image": "collectibles/icon_book_1.png", "cost_gold": 1500, "unlock_with_gems": False, "unlock_at_level": 100, "effect": {"prestige_bonus_points": 1, "xp_bonus_percent": 5}, "effect_description": "+1 prestige point per prestige, +5% XP (gold-only)", "rarity": "legendary"},
    {"id": "flag_snow", "name": "Snow Banner", "image": "collectibles/icon_flag_snow.png", "cost_gold": 850, "unlock_with_gems": False, "unlock_at_level": 105, "effect": {"streak_reward_bonus_percent": 30}, "effect_description": "+30% 7-day streak rewards (gold-only)", "rarity": "legendary"},
    {"id": "lamp_enchanted", "name": "Enchanted Lamp", "image": "collectibles/icon_lamp.png", "cost_gold": 900, "unlock_with_gems": False, "unlock_at_level": 110, "effect": {"gold_bonus_percent": 10, "luck_gem_chance_percent": 16}, "effect_description": "+10% gold, +16% gem luck (gold-only)", "rarity": "legendary"},
    {"id": "hammer_utility", "name": "War Hammer", "image": "collectibles/icon_equip_hammer.png", "cost_gold": 900, "unlock_with_gems": False, "unlock_at_level": 90, "effect": {"gold_bonus_percent": 20, "xp_bonus_percent": 2}, "effect_description": "+20% gold, +2% XP (gold-only)", "rarity": "legendary"},
    {"id": "axe_utility", "name": "Battle Axe", "image": "collectibles/icon_equip_ax.png", "cost_gold": 900, "unlock_with_gems": False, "unlock_at_level": 95, "effect": {"xp_bonus_percent": 17, "gold_bonus_percent": 5}, "effect_description": "+17% XP, +5% gold (gold-only)", "rarity": "legendary"},
]


def default_gems() -> dict[str, int]:
    return {color: 0 for color, _ in GEM_COLORS}


# --- Key helpers ---

# Keys are a tier chain: one can only be obtained once the tier below it is owned. Bronze has no
# prerequisite and unlocks below the other two, so the chain is always completable from nothing —
# whenever a gated key is level-eligible its prerequisite is too, and an unowned prerequisite is
# always in the pool, which is what keeps the pool from stranding.
TIER_PREREQUISITE = {
    KEY_SILVER_ID: KEY_BRONZE_ID,
    KEY_GOLD_ID: KEY_SILVER_ID,
}


def tier_unlocked(cid: str, owned_ids: list[str] | set[str]) -> bool:
    """
    True if the tier chain allows this collection to obtain `cid` yet.

    Applied to both ways in — crafting and the shop's sale pool — so the chain does not silently
    depend on Silver and Golden happening to have no gold price.
    """
    prereq = TIER_PREREQUISITE.get(cid)
    return prereq is None or prereq in owned_ids


def has_bronze_key(owned_ids: list[str]) -> bool:
    """True if player owns Bronze Key (unlocks shop refresh)."""
    return KEY_BRONZE_ID in owned_ids


def has_silver_key(owned_ids: list[str]) -> bool:
    """True if player owns Silver Key (faster refresh)."""
    return KEY_SILVER_ID in owned_ids


def has_gold_key(owned_ids: list[str]) -> bool:
    """True if player owns Golden Key (free daily refresh)."""
    return KEY_GOLD_ID in owned_ids


def can_refresh_shop(owned_ids: list[str]) -> bool:
    """True if player can use shop refresh (owns any key)."""
    return has_bronze_key(owned_ids) or has_silver_key(owned_ids) or has_gold_key(owned_ids)


def get_refresh_interval(owned_ids: list[str]) -> int:
    """Get shop refresh interval in seconds based on owned keys."""
    if has_silver_key(owned_ids):
        return SHOP_REFRESH_INTERVAL_SILVER  # 2 hours
    return SHOP_REFRESH_INTERVAL_DEFAULT  # 4 hours, with or without a key


def craft_required_colors(gems: dict[str, int], data: dict[str, Any] | None = None) -> list[str]:
    """
    The gem colors a craft charges for: every color, or all but one while the discount buff runs.

    The waived color is the one the player holds fewest of. "Costs 4 gems instead of 5" has to name
    *which* four, and waiving the scarcest is the only choice that makes the buff reliably worth
    something — any fixed color would do nothing on the days the player is short of a different one,
    which is most days. Ties break on GEM_COLORS order so the shop's preview and the spend below
    always waive the same color.
    """
    colors = [c for c, _ in GEM_COLORS]
    if data is None:
        return colors
    from . import milestones

    if not milestones.buff_is_active(data, milestones.BUFF_CRAFT_CHEAPER):
        return colors
    scarcest = min(colors, key=lambda c: (gems.get(c, 0), colors.index(c)))
    return [c for c in colors if c != scarcest]


def can_craft(gems: dict[str, int], data: dict[str, Any] | None = None) -> bool:
    """True if the player has at least 1 of every color the craft charges for."""
    return all(gems.get(c, 0) >= 1 for c in craft_required_colors(gems, data))


def _unlock_at_level(c: dict[str, Any]) -> int:
    """Level at which this collectible becomes visible in the shop (default 1)."""
    return c.get("unlock_at_level", 1)


def discounted_gold(data: dict[str, Any] | None, cost: int) -> int:
    """
    A shop price after the discount buff, rounded up so nothing ever costs a fraction of a gold.

    Every gold price the shop shows or charges goes through here, and the display and the charge
    call the same function rather than each applying the discount themselves — a price the player
    is quoted and a price they are billed have to be the same number.

    Never below 1: a discount that reached zero would turn "20% off" into "free", which is a
    different buff.
    """
    from . import milestones

    if cost <= 0 or data is None:
        return cost
    if not milestones.buff_is_active(data, milestones.BUFF_SHOP_DISCOUNT):
        return cost
    return max(1, -(-cost * (100 - milestones.BUFF_SHOP_DISCOUNT_PERCENT) // 100))


def effective_cost_gold(c: dict[str, Any], level: int = 0, data: dict[str, Any] | None = None) -> int:
    """Gold cost for this collectible (base price; no level scaling), after any shop discount."""
    base = c.get("cost_gold")
    if base is None:
        return 0
    return discounted_gold(data, max(1, base))


def slot_cost(data: dict[str, Any], slot: dict[str, Any], default: int = 0) -> int:
    """
    What a gem or Magnet slot charges right now.

    Read from the slot rather than baked into it when it was rolled: a price frozen at roll time
    would keep the discount after the buff expired, and lose it on a slot rolled just before the
    buff landed.
    """
    return discounted_gold(data, int(slot.get("cost", default) or 0))


def collectibles_for_gold() -> list[dict[str, Any]]:
    """Collectibles that can be bought with gold (have a gold price). Use collectibles_for_gold_at_level(level) to filter by level."""
    return [c for c in COLLECTIBLES if c.get("cost_gold") is not None]


def collectibles_for_gold_at_level(level: int) -> list[dict[str, Any]]:
    """Collectibles buyable with gold that are unlocked at this level."""
    return [c for c in collectibles_for_gold() if level >= _unlock_at_level(c)]


def gem_only_collectibles() -> list[dict[str, Any]]:
    """Collectibles with no gold price — the ones a gem craft is the only route to."""
    return [c for c in COLLECTIBLES if c.get("cost_gold") is None]


def collectibles_for_gems() -> list[dict[str, Any]]:
    """Collectibles that can be unlocked with 5 gems. Use collectibles_for_gems_at_level(level) to filter by level."""
    return [c for c in COLLECTIBLES if c.get("unlock_with_gems", True)]


def collectibles_for_gems_at_level(level: int) -> list[dict[str, Any]]:
    """Collectibles unlockable with 5 gems that are unlocked at this level."""
    return [c for c in collectibles_for_gems() if level >= _unlock_at_level(c)]


def get_collectible(cid: str) -> dict[str, Any] | None:
    for c in COLLECTIBLES:
        if c["id"] == cid:
            return c
    return None


def _today_str() -> str:
    """Scheduler day (honors 'Next day starts at'), not civil midnight."""
    from . import streak
    return streak.today_str()


def _all_at_level(level: int) -> list[dict[str, Any]]:
    """All collectibles (gold + gem-only) available at this level."""
    return [c for c in COLLECTIBLES if level >= _unlock_at_level(c)]


# Three entries, not one: each gem kind competes for a slot on its own, so a refresh can offer any
# mix of them - including all of them. The single entry this replaced meant at most one gem could
# ever be offered, with the three kinds sharing that one slot's probability rather than each having
# their own. The kind is fixed when the pool is built rather than rolled afterwards, which is what
# lets them appear together.
_GEM_PLACEHOLDERS: tuple[dict[str, Any], ...] = (
    {"type": "gem_placeholder", "kind": "random"},
    {"type": "gem_placeholder", "kind": "most_needed"},
    {"type": "gem_placeholder", "kind": "specific"},
)


def most_needed_gem_color(gems: dict[str, int]) -> str:
    """The color the player holds fewest of. Ties broken at random, which is the common case.

    Deliberately not called "rarest": with five colors a player is usually level on several of
    them, and naming one of a tie "rarest" would claim a distinction that does not exist.
    """
    counts = [(gems.get(c, 0), c) for c, _ in GEM_COLORS]
    fewest = min(n for n, _ in counts)
    return random.choice([c for n, c in counts if n == fewest])


def _gem_slot_of_kind(kind: str, gems: dict[str, int] | None = None) -> dict[str, Any]:
    """
    Build the gem slot a placeholder of this kind resolves to.

    The most-needed color is resolved here, at roll time, rather than at purchase: the slot shows
    the gem's own icon, so it has to name a color to draw. A gem gained between the roll and the
    purchase therefore does not retarget it — the offer is what it said it was.
    """
    if kind == "random":
        return {"type": "gem", "random": True, "cost": GEM_COST_RANDOM}
    if kind == "most_needed":
        color = most_needed_gem_color(gems if gems is not None else default_gems())
        return {"type": "gem", "color": color, "most_needed": True, "cost": GEM_COST_MOST_NEEDED}
    color = random.choice([c for c, _ in GEM_COLORS])
    return {"type": "gem", "color": color, "cost": GEM_COST_SPECIFIC}


def shop_slot_count(data: dict[str, Any] | None = None) -> int:
    """How many slots the shop offers. The track raises this once; everyone starts at the base."""
    if data is None:
        return SHOP_ITEMS_PER_DAY
    from . import milestones

    return int(milestones.granted_value(data, "shop_slots", SHOP_ITEMS_PER_DAY))


def craft_pool(level: int, owned: set[str], data: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """
    The items a gem craft can produce: unowned, unlocked at this level, tier prerequisite met.

    With targeted craft the pool narrows to the items that have no gold price — the only ones
    crafting is the sole route to. It falls back to the full pool once those are all owned, because
    the reward is meant to aim crafting rather than to switch it off: a narrowed pool that emptied
    would turn a milestone reward into a milestone punishment.
    """
    # collectibles_for_gems_at_level, not _all_at_level: nine items are marked gold-only and their
    # own descriptions say so, but the craft pool was drawing from every collectible regardless, so
    # a craft could hand you one. The helper that filters them already existed and simply was not
    # being used here.
    pool = [
        c for c in collectibles_for_gems_at_level(level)
        if c["id"] not in owned and tier_unlocked(c["id"], owned)
    ]
    if data is None:
        return pool
    from . import milestones

    if not milestones.has_targeted_craft(data):
        return pool
    gem_only = [c for c in pool if c.get("cost_gold") is None]
    return gem_only or pool


def craft_pool_is_targeted(data: dict[str, Any], level: int) -> bool:
    """
    Whether the craft is currently narrowed to gem-only items.

    Not the same question as "has the reward been granted": once every gem-only item at this level
    is owned the pool falls back to the full one, and the shop should say so rather than keep
    promising a pool the craft is no longer drawing from.
    """
    from . import milestones

    if not milestones.has_targeted_craft(data):
        return False
    owned = set(data.get("owned_collectibles", []))
    return any(c.get("cost_gold") is None for c in craft_pool(level, owned, data))


def _build_daily_slot_pool(level: int, owned: set[str] | None = None) -> list[dict[str, Any]]:
    """
    Pool for shop slots: collectibles (gold at level, not owned) plus one entry per gem kind.
    Each gem kind competes for a slot on its own, so a refresh can offer several gems at once.
    """
    owned = owned or set()
    pool: list[dict[str, Any]] = []
    for c in collectibles_for_gold_at_level(level):
        if c["id"] not in owned and tier_unlocked(c["id"], owned):
            pool.append({"type": "collectible", "id": c["id"]})
    pool.extend(dict(g) for g in _GEM_PLACEHOLDERS)
    return pool


def _now_timestamp() -> int:
    """Current time as Unix timestamp (seconds)."""
    return int(datetime.now().timestamp())


def get_shop_refresh_remaining(data: dict[str, Any]) -> int:
    """Seconds until shop auto-refreshes. 0 if refresh is due."""
    last_refresh = data.get("shop_last_refresh_time", 0)
    elapsed = _now_timestamp() - last_refresh
    owned = data.get("owned_collectibles", [])
    interval = get_refresh_interval(owned)
    # Clamped to the interval as well as to zero: a stored timestamp in the future (system clock
    # moved back, or a save restored from a machine running ahead) would otherwise report a wait
    # longer than the interval itself and hold the shop shut until real time caught up.
    remaining = interval - elapsed
    return max(0, min(interval, remaining))


def get_daily_slots(data: dict[str, Any], level: int) -> list[dict[str, Any]]:
    """
    Shop's 3 slots. At most one is a gem; the rest are collectibles (not owned).
    Rolls new 3 when: no slots, or the auto-refresh timer expired. Mutates data.
    """
    slots = data.get("shop_daily_slots", [])
    remaining = get_shop_refresh_remaining(data)
    if not slots or remaining == 0:
        owned = set(data.get("owned_collectibles", []))
        pool = _build_daily_slot_pool(level, owned)
        n = min(shop_slot_count(data), len(pool))
        if n > 0:
            chosen = random.sample(pool, n)
        else:
            chosen = []
        out: list[dict[str, Any]] = []
        for s in chosen:
            if s.get("type") == "gem_placeholder":
                out.append(_gem_slot_of_kind(s.get("kind", "specific"), data.get("gems", default_gems())))
            else:
                out.append(s)
        _maybe_place_magnet_slot(data, out)
        data["shop_last_refresh_time"] = _now_timestamp()
        data["shop_daily_slots"] = out
        slots = data["shop_daily_slots"]
    return slots


# Why a Magnet purchase failed. Returned instead of a bare False so the shop can say which of the
# four it was - "Not enough gold" is wrong for three of them, and the stage-finished case is one
# buy_magnet documents as reachable.
MAGNET_BUY_SOLD = "sold"
MAGNET_BUY_UNAVAILABLE = "unavailable"
MAGNET_BUY_NO_STAGE = "no_stage"
MAGNET_BUY_POOR = "poor"

MAGNET_BUY_MESSAGES = {
    MAGNET_BUY_SOLD: "Already bought.",
    MAGNET_BUY_UNAVAILABLE: "Magnets are not on sale.",
    MAGNET_BUY_NO_STAGE: "No accumulator upgrade is waiting for a magnet.",
    MAGNET_BUY_POOR: "Not enough gold.",
}


def _maybe_place_magnet_slot(data: dict[str, Any], slots: list[dict[str, Any]]) -> None:
    """
    Turn one of a freshly built slot list into a Magnet, at MAGNET_DROP_PERCENT.

    Rolled per restock rather than held as a standing offer: with the collection nearly complete the
    item list is short, and a Magnet holding a slot outright would be in front of the player at
    every single restock. Never more than one, which the rebuild-from-scratch by both callers gives
    for free. Reachable only while a stage is in progress, and never at a complete collection —
    the caller does not draw the item grid then, so it does not restock at all.

    Shared by the automatic restock and the manual refresh. They built their slots identically and
    only the automatic one rolled for a Magnet, so paying for a refresh, or spending the free daily
    one, guaranteed the player would not see it.
    """
    from . import milestones

    if not slots:
        return
    if not milestones.magnets_sold_in_shop(data):
        return
    if milestones.magnet_upgrade_in_progress(data) is None:
        return
    if random.randint(0, 99) >= milestones.MAGNET_DROP_PERCENT:
        return
    slots[random.randrange(len(slots))] = {"type": "magnet", "cost": MAGNET_COST_GOLD}


def buy_magnet(data: dict[str, Any], slot: dict[str, Any]) -> dict[str, Any] | bool | str:
    """
    Buy the Magnet slot. Returns the stage it completed, True if it merely counted, or one of the
    MAGNET_BUY_* reasons if it was not bought.

    Marked sold rather than removed, like a gem slot: the row stays where it was so the grid does
    not reflow under the player's cursor the moment they click.
    """
    from . import milestones

    if slot.get("sold"):
        return MAGNET_BUY_SOLD
    if not milestones.magnets_sold_in_shop(data):
        return MAGNET_BUY_UNAVAILABLE
    if milestones.magnet_upgrade_in_progress(data) is None:
        # The stage finished between the restock and the click - a bonus quest drops Magnets too.
        return MAGNET_BUY_NO_STAGE
    cost = slot_cost(data, slot, MAGNET_COST_GOLD)
    if cost <= 0 or data.get("money", 0) < cost:
        return MAGNET_BUY_POOR
    data["money"] = data["money"] - cost
    slot["sold"] = True
    return milestones.award_magnet(data) or True


def buy_gem_option(data: dict[str, Any], slot: dict[str, Any]) -> bool:
    """
    Buy one gem from a daily slot. Slot is {"color": "blue", "cost": 45} or {"random": True,
    "cost": 30}; a most-needed slot carries its color like any other named one, so it needs no case
    of its own here — the choice was already made when the slot was rolled.
    Gem slots are one-time: after purchase the slot is marked sold. Mutates data (money, gems) and slot (sold).
    Returns True if purchased.
    """
    if slot.get("sold"):
        return False
    cost = slot_cost(data, slot)
    if cost <= 0 or data.get("money", 0) < cost:
        return False
    data["money"] = data["money"] - cost
    if slot.get("random"):
        data["gems"] = award_random_gem(data.get("gems", default_gems()))
    else:
        color = slot.get("color")
        if color not in [c for c, _ in GEM_COLORS]:
            return False
        g = data.get("gems", default_gems())
        g[color] = g.get(color, 0) + 1
        data["gems"] = g
    slot["sold"] = True
    return True


# Gem craft: items closer to player level get higher weight (max distance 15).
GEM_CRAFT_MAX_DISTANCE = 15


def spend_gems_get_random(data: dict[str, Any], level: int) -> tuple[str | None, dict[str, Any] | None]:
    """
    Spend 5 gems (one of each color) → get one random collectible from pool.
    Pool = collectibles unlocked at this level or below, not yet owned (never above your level),
    minus any whose tier prerequisite is unmet (see TIER_PREREQUISITE).
    Weighted by level: items closer to your level are more likely.
    Returns (cid, collectible) or (None, None) if can't craft or pool empty.
    Mutates data (gems, owned_collectibles).
    """
    gems = data.get("gems", default_gems())
    if not can_craft(gems, data):
        return (None, None)
    owned = set(data.get("owned_collectibles", []))
    pool = craft_pool(level, owned, data)
    if not pool:
        return (None, None)
    weights = []
    for c in pool:
        dist = max(0, level - _unlock_at_level(c))
        dist = min(dist, GEM_CRAFT_MAX_DISTANCE)
        weights.append(1.0 / (1 + dist))
    c = random.choices(pool, weights=weights, k=1)[0]
    cid = c["id"]
    charged = set(craft_required_colors(gems, data))
    new_gems = {color: gems[color] - (1 if color in charged else 0) for color, _ in GEM_COLORS}
    data["gems"] = new_gems
    data.setdefault("owned_collectibles", []).append(cid)

    # Counted here rather than at the call site so every path that crafts an item is counted,
    # including any future one. Deferred import: shop is imported by most of the package.
    from . import milestones

    milestones.note_event(data, milestones.OBJ_CRAFT)
    milestones.advance_if_complete(data)
    return (cid, c)


def has_refresh_unlocked(data: dict[str, Any]) -> bool:
    """True if player owns any key (bronze, silver, gold) that unlocks the shop refresh button."""
    owned = data.get("owned_collectibles", [])
    return can_refresh_shop(owned)


def has_free_refresh_available(data: dict[str, Any]) -> bool:
    """True if player has free refresh(es) left today. Any key: 1 free/day; Golden Key: 2 free/day."""
    if not has_refresh_unlocked(data):
        return False
    today = _today_str()
    last_date = data.get("shop_last_free_refresh_date", "")
    used_today = data.get("shop_free_refreshes_used_today", 0) if (last_date == today) else 0
    free_per_day = 2 if has_gold_key(data.get("owned_collectibles", [])) else 1
    return used_today < free_per_day


def get_refresh_cost(data: dict[str, Any]) -> int:
    """
    Gold cost for next refresh. 0 if free refresh left today; else 15g first paid use, +15g per use.
    Returns 0 if free refresh available or if refresh not unlocked.
    """
    if not has_refresh_unlocked(data):
        return 0
    if has_free_refresh_available(data):
        return 0
    # Falls through to the escalating price below, which the discount then applies to.
    uses = data.get("shop_refresh_uses", 0)
    return discounted_gold(data, REFRESH_COST_BASE + REFRESH_COST_INCREMENT * uses)


def refresh_shop(data: dict[str, Any], level: int) -> bool:
    """
    Roll new 3 shop items. Only available if player owns a key.
    Uses free refresh if any left today (1/day with any key, 2/day with Golden Key); else 15g first paid, +15g per use.
    Also resets the auto-refresh timer. Returns True if refreshed.
    """
    if not has_refresh_unlocked(data):
        return False
    is_free = has_free_refresh_available(data)
    cost = 0 if is_free else get_refresh_cost(data)
    money = data.get("money", 0)
    if not is_free and money < cost:
        return False
    owned = set(data.get("owned_collectibles", []))
    pool = _build_daily_slot_pool(level, owned)
    n = min(shop_slot_count(data), len(pool))
    if n > 0:
        chosen = random.sample(pool, n)
    else:
        chosen = []
    out = []
    for s in chosen:
        if s.get("type") == "gem_placeholder":
            # The player's own gems, not default_gems(): this path used to pass nothing, so a
            # most-needed slot bought from a manual refresh was aimed at an all-zero gem dict and
            # named whichever color won that tie rather than the one actually short.
            out.append(_gem_slot_of_kind(s.get("kind", "specific"), data.get("gems", default_gems())))
        else:
            out.append(s)
    _maybe_place_magnet_slot(data, out)
    today = _today_str()
    if is_free:
        if data.get("shop_last_free_refresh_date", "") != today:
            data["shop_free_refreshes_used_today"] = 0
        data["shop_last_free_refresh_date"] = today
        data["shop_free_refreshes_used_today"] = data.get("shop_free_refreshes_used_today", 0) + 1
    else:
        data["money"] = money - cost
        data["shop_refresh_uses"] = data.get("shop_refresh_uses", 0) + 1
    data["shop_daily_slots"] = out
    data["shop_last_refresh_time"] = _now_timestamp()
    return True


def _sum_effect(owned_ids: list[str], key: str) -> float:
    """Sum a numeric effect across owned collectibles."""
    total = 0.0
    for cid in owned_ids:
        c = get_collectible(cid)
        if c and c.get("effect"):
            total += c["effect"].get(key, 0)
    return total


def xp_bonus_percent(owned_ids: list[str]) -> float:
    """Total XP bonus from owned collectibles (e.g. 3 for +3%)."""
    return _sum_effect(owned_ids, "xp_bonus_percent")


def gold_bonus_percent(owned_ids: list[str]) -> float:
    """Total gold bonus from owned collectibles (e.g. 2 for +2%)."""
    return _sum_effect(owned_ids, "gold_bonus_percent")


def gold_flat(owned_ids: list[str]) -> int:
    """Total flat gold bonus from owned collectibles (added to level-up gold)."""
    return int(_sum_effect(owned_ids, "gold_flat"))


def xp_flat(owned_ids: list[str]) -> int:
    """Total flat XP bonus from owned collectibles (added to review XP, except Again/Hard-in-hard-mode)."""
    return int(_sum_effect(owned_ids, "xp_flat"))


def streak_reward_bonus_percent(owned_ids: list[str]) -> float:
    """Total 7-day streak reward bonus (primarily gems) from owned collectibles."""
    return _sum_effect(owned_ids, "streak_reward_bonus_percent")


def luck_gem_chance_percent(owned_ids: list[str]) -> float:
    """Total luck chance (e.g. 5 = 5% chance +1 extra gem on quest/level-up)."""
    return _sum_effect(owned_ids, "luck_gem_chance_percent")


def prestige_bonus_points(owned_ids: list[str]) -> int:
    """Extra prestige points granted per prestige by owned collectibles (the two tomes)."""
    return int(_sum_effect(owned_ids, "prestige_bonus_points"))


def all_collectibles_owned(data: dict[str, Any]) -> bool:
    """True if the player owns every collectible in COLLECTIBLES."""
    owned = set(data.get("owned_collectibles", []))
    all_ids = {c["id"] for c in COLLECTIBLES}
    return all_ids.issubset(owned)


# A Magnet on sale. Flat, because what it buys is flat: a Magnet is the same Magnet at every stage,
# since a later stage asks for more of them rather than dearer ones. 50 sits with the gem slots'
# 30-60, the right neighborhood for something bought repeatedly rather than once.
MAGNET_COST_GOLD = 50

# Endgame trade rates (when all collectibles owned)
TRADE_GOLD_TO_XP_RATE = 3   # 1 gold -> 3 XP
# Priced at GEM_COST_RANDOM * TRADE_GOLD_TO_XP_RATE: a gem is worth what the cheapest gem slot
# charges for one. A completed collection hides the gem slots, and at any higher rate the player
# would be losing XP to a shop they can no longer buy from; matching the two means the hidden slots
# cost them nothing. Anchored to the cheapest of the three prices rather than the middle one, so
# the endgame trade stays conservative.
TRADE_GEM_TO_XP_RATE = GEM_COST_RANDOM * TRADE_GOLD_TO_XP_RATE  # 1 gem -> 90 XP


def _pay_level_up(data: dict[str, Any]) -> None:
    """Update the stored level for the XP a trade just paid, and grant the level-ups it bought.

    Every other XP award reaches the level-up through review_rewards.apply_one_review; a trade pays
    total_xp directly, so it has to ask for the same treatment or the level goes stale (it is read
    as a live figure elsewhere — streak.grant_streak_reward scales by level // 10) and the levels
    the trade bought pay nothing.

    Imported inside the function because review_rewards imports this module at import time; the same
    deferred import quests.py and streak.py use to cross the same boundary.
    """
    from . import review_rewards

    review_rewards.grant_level_up(
        data, data.get("level", 1), data.get("owned_collectibles", [])
    )


def trade_gold_for_xp(data: dict[str, Any]) -> int:
    """
    Convert all gold to XP at 1g = 3 XP. Mutates data (money -> 0, total_xp += money * 3).
    Only valid when all collectibles are owned. Returns XP added.

    Levels crossed pay their normal level-up, so the purse may hold gold again afterwards.
    """
    money = data.get("money", 0)
    if money <= 0:
        return 0
    xp_added = money * TRADE_GOLD_TO_XP_RATE
    data["money"] = 0
    data["total_xp"] = data.get("total_xp", 0) + xp_added
    # After the gold is spent, so a level-up's own gold lands in an emptied purse rather than being
    # zeroed by the trade that earned it.
    _pay_level_up(data)
    return xp_added


def trade_gems_for_xp(data: dict[str, Any]) -> int:
    """
    Convert all gems to XP at TRADE_GEM_TO_XP_RATE per gem. Mutates data (gems -> 0, total_xp += ...).
    Only valid when all collectibles are owned. Returns XP added.

    Levels crossed each pay their normal level-up, so a large trade returns gold and a meaningful
    share of the gems back — a measured 33-level trade returned 28 of the 50 gems it consumed.
    """
    gems = data.get("gems", default_gems())
    total_gems = sum(gems.values())
    if total_gems <= 0:
        return 0
    xp_added = total_gems * TRADE_GEM_TO_XP_RATE
    data["gems"] = default_gems()  # reset all gems to 0
    data["total_xp"] = data.get("total_xp", 0) + xp_added
    # After the reset, for the same reason trade_gold_for_xp pays after emptying the purse.
    _pay_level_up(data)
    return xp_added




def random_gem_color() -> str:
    """One gem color at random. Lets a caller decide the colors up front and award them together."""
    return random.choice([c for c, _ in GEM_COLORS])


def award_random_gem(gems: dict[str, int]) -> dict[str, int]:
    """Add 1 random gem. Returns updated gems dict (copy)."""
    out = dict(gems)
    color = random.choice([c for c, _ in GEM_COLORS])
    out[color] = out.get(color, 0) + 1
    return out


def award_gem_of_color(gems: dict[str, int], color: str) -> dict[str, int]:
    """Add 1 gem of the given color. Returns updated gems dict (copy). Use for fixed rewards (quest/level) so undo doesn't reroll."""
    valid = [c for c, _ in GEM_COLORS]
    if color not in valid:
        color = random.choice(valid)
    out = dict(gems)
    out[color] = out.get(color, 0) + 1
    return out
