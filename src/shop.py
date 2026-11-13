"""Shop, gems and collectibles: the restocking shop slots (collectibles, gem kinds, a Magnet), gem
crafting, key-unlocked refreshes, and the endgame XP trades. Rules for players are in the wiki."""
from __future__ import annotations

import random
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

# Shop unlocks after this many reviews today
SHOP_MIN_REVIEWS = 10


def reviews_counted_today(data: dict[str, Any], today: str) -> int:
    """reviews_today, or 0 while it still holds yesterday's count (reset by the day's first answer)."""
    return int(data.get("reviews_today", 0) or 0) if data.get("last_date") == today else 0


def is_open_today(data: dict[str, Any], today: str) -> bool:
    """Open once today's review count is reached, and for the rest of the day once opened, so undo
    can't lock it again."""
    return (
        data.get("shop_gate_date", "") == today
        or reviews_counted_today(data, today) >= SHOP_MIN_REVIEWS
    )


def open_for_today(data: dict[str, Any], today: str) -> bool:
    """is_open_today, stamping the gate on success so the shop stays open all day. Caller saves."""
    if not is_open_today(data, today):
        return False
    data["shop_gate_date"] = today
    return True


# Daily shop: this many random items (gold-purchasable at level)
SHOP_ITEMS_PER_DAY = 3  # Base count; milestone #7 raises it. See shop_slot_count().

# Each slot is either a collectible or one gem option, from the same pool. Gem prices rise with how
# much say the player gets over the color, and the ladder must stay monotone.
GEM_COST_RANDOM = 30       # color decided on purchase
GEM_COST_SPECIFIC = 45     # a color the shop names
GEM_COST_MOST_NEEDED = 60  # the color the player holds fewest of

# A gem offer's weight in the slot draw, against 1 for anything else: the three together count as
# one item. They still fill whatever slots the rest of the pool can't.
GEM_SLOT_WEIGHT = 1 / 3

# Refresh (unlocked by owning a key): 1 free per day (2 with Golden key), then 15g first paid, +15g per use.
REFRESH_COST_BASE = 15
REFRESH_COST_INCREMENT = 15

# Shop auto-refresh interval (seconds). DEFAULT applies with or without a key.
SHOP_REFRESH_INTERVAL_DEFAULT = 14400  # 4 hours (no key needed)
SHOP_REFRESH_INTERVAL_SILVER = 7200   # 2 hours (Silver key upgrade)

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

# Collectible: id, name, image, cost_gold (None = no gold price), unlock_with_gems, unlock_at_level,
# effect, effect_description. Bag, Star and Ticket are UI-only and not listed here.
COLLECTIBLES: list[dict[str, Any]] = [
    # ============ EARLY — unlocks at 1, 2, 3, 5, 8, 10, 12, 14–16 ============
    {"id": "stone", "name": "Stone", "image": "collectibles/equip_icon_stone.png", "cost_gold": 18, "unlock_with_gems": True, "unlock_at_level": 1, "effect": {"xp_bonus_percent": 1}, "effect_description": "+1% XP"},
    {"id": "cup", "name": "Cup", "image": "collectibles/Cup.png", "cost_gold": 25, "unlock_with_gems": True, "unlock_at_level": 1, "effect": {"gold_flat": 2}, "effect_description": "+2g earned"},
    {"id": "package", "name": "Package", "image": "collectibles/Package.png", "cost_gold": 28, "unlock_with_gems": True, "unlock_at_level": 1, "effect": {"luck_gem_chance_percent": 3}, "effect_description": "+3% gem luck"},
    # --- Level 2 ---
    {"id": "bracelet", "name": "Bracelet", "image": "collectibles/equip_icon_bracelet.png", "cost_gold": 40, "unlock_with_gems": True, "unlock_at_level": 2, "effect": {"gold_flat": 2, "xp_bonus_percent": 1}, "effect_description": "+2g earned, +1% XP"},
    {"id": "potion_red_0", "name": "Red potion", "image": "collectibles/equip_icon_potion_red_0.png", "cost_gold": 40, "unlock_with_gems": True, "unlock_at_level": 2, "effect": {"xp_bonus_percent": 2}, "effect_description": "+2% XP"},
    # --- Level 3 ---
    {"id": "fish", "name": "Fish", "image": "collectibles/equip_icon_fish.png", "cost_gold": 42, "unlock_with_gems": True, "unlock_at_level": 3, "effect": {"luck_gem_chance_percent": 5}, "effect_description": "+5% gem luck"},
    # --- Level 5 (gap 4) ---
    {"id": "hard_tooth", "name": "Hard tooth", "image": "collectibles/equip_icon_hard_tooth.png", "cost_gold": 45, "unlock_with_gems": True, "unlock_at_level": 5, "effect": {"gold_flat": 3}, "effect_description": "+3g earned"},
    {"id": "poison_tooth", "name": "Poison tooth", "image": "collectibles/equip_icon_posion_tooth.png", "cost_gold": 50, "unlock_with_gems": True, "unlock_at_level": 5, "effect": {"luck_gem_chance_percent": 5}, "effect_description": "+5% gem luck"},
    {"id": "tooth_red", "name": "Red teeth", "image": "collectibles/equip_icon_teeth_red.png", "cost_gold": 48, "unlock_with_gems": True, "unlock_at_level": 5, "effect": {"gold_flat": 2, "gold_bonus_percent": 2}, "effect_description": "+2g earned, +2% gold"},
    # --- Level 8 (gap 6–7) ---
    {"id": "crystal", "name": "Crystal", "image": "collectibles/equip_icon_cyristal.png", "cost_gold": 65, "unlock_with_gems": True, "unlock_at_level": 8, "effect": {"xp_bonus_percent": 3}, "effect_description": "+3% XP"},
    {"id": "axe", "name": "Axe", "image": "collectibles/equip_icon_axe_0.png", "cost_gold": 60, "unlock_with_gems": True, "unlock_at_level": 8, "effect": {"xp_bonus_percent": 2, "gold_bonus_percent": 1}, "effect_description": "+2% XP, +1% gold"},
    {"id": "leaf", "name": "Leaf", "image": "collectibles/equip_icon_leaf.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 8, "effect": {"luck_gem_chance_percent": 6}, "effect_description": "+6% gem luck"},
    {"id": "shield_wood", "name": "Wood shield", "image": "collectibles/equip_icon_shield_wood.png", "cost_gold": 70, "unlock_with_gems": True, "unlock_at_level": 8, "effect": {"luck_gem_chance_percent": 2, "gold_flat": 1}, "effect_description": "+2% gem luck, +1g earned"},
    # --- Level 10 ---
    {"id": "hammer", "name": "Hammer", "image": "collectibles/equip_icon_hammer_0.png", "cost_gold": 80, "unlock_with_gems": True, "unlock_at_level": 10, "effect": {"gold_flat": 4}, "effect_description": "+4g earned"},
    {"id": "potion_red_1", "name": "Red potion II", "image": "collectibles/equip_icon_potion_red_1.png", "cost_gold": 75, "unlock_with_gems": True, "unlock_at_level": 10, "effect": {"xp_bonus_percent": 3}, "effect_description": "+3% XP"},
    # --- Level 12 ---
    {"id": "key_bronze", "name": "Bronze key", "image": "collectibles/icon_key_bronze.png", "cost_gold": 120, "unlock_with_gems": True, "unlock_at_level": 12, "effect": {}, "effect_description": "Lets you restock the shop: 1 free/day, then 15g+"},
    {"id": "island", "name": "Island", "image": "collectibles/Island.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 12, "effect": {"streak_reward_bonus_percent": 30}, "effect_description": "+30% 7-day streak rewards"},
    # --- Level 14–16 ---
    {"id": "axe_1", "name": "Strong axe", "image": "collectibles/equip_icon_axe_1.png", "cost_gold": 95, "unlock_with_gems": True, "unlock_at_level": 14, "effect": {"xp_bonus_percent": 2, "gold_bonus_percent": 2}, "effect_description": "+2% XP, +2% gold"},
    {"id": "hammer_1", "name": "Strong hammer", "image": "collectibles/equip_icon_hammer_1.png", "cost_gold": 120, "unlock_with_gems": True, "unlock_at_level": 16, "effect": {"gold_flat": 4, "gold_bonus_percent": 5}, "effect_description": "+4g earned, +5% gold"},
    {"id": "potion_blue_0", "name": "Blue potion", "image": "collectibles/equip_icon_potion_blue_0.png", "cost_gold": 140, "unlock_with_gems": True, "unlock_at_level": 15, "effect": {"xp_flat": 1}, "effect_description": "+1 XP/review"},

    # ============ MID — 18, 22, 25, 26, 30, 35 ============
    {"id": "ring_blue", "name": "Blue ring", "image": "collectibles/equip_icon_ring_blue.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 18, "effect": {"xp_bonus_percent": 5}, "effect_description": "+5% XP"},
    {"id": "cloverleaf", "name": "Lucky clover", "image": "collectibles/Cloverleaf.png", "cost_gold": 333, "unlock_with_gems": True, "unlock_at_level": 18, "effect": {"luck_gem_chance_percent": 10}, "effect_description": "+10% gem luck"},
    {"id": "axe_2", "name": "Great axe", "image": "collectibles/equip_icon_axe_2.png", "cost_gold": 150, "unlock_with_gems": True, "unlock_at_level": 22, "effect": {"xp_bonus_percent": 4, "gold_bonus_percent": 3}, "effect_description": "+4% XP, +3% gold"},
    {"id": "hammer_2", "name": "Great hammer", "image": "collectibles/equip_icon_hammer_2.png", "cost_gold": 190, "unlock_with_gems": True, "unlock_at_level": 24, "effect": {"gold_bonus_percent": 8}, "effect_description": "+8% gold"},
    {"id": "potion_red_2", "name": "Red potion III", "image": "collectibles/equip_icon_potion_red_2.png", "cost_gold": 145, "unlock_with_gems": True, "unlock_at_level": 22, "effect": {"xp_bonus_percent": 5}, "effect_description": "+5% XP"},
    {"id": "key_silver", "name": "Silver key", "image": "collectibles/icon_key_silver.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 22, "effect": {}, "effect_description": "New stock every 2 hours instead of 4"},
    {"id": "gem_red", "name": "Red gem", "image": "collectibles/equip_icon_gem_red.png", "cost_gold": 200, "unlock_with_gems": True, "unlock_at_level": 25, "effect": {"streak_reward_bonus_percent": 45}, "effect_description": "+45% 7-day streak rewards"},
    {"id": "dragon_tooth", "name": "Dragon teeth", "image": "collectibles/equip_icon_dragon_teeth.png", "cost_gold": 200, "unlock_with_gems": True, "unlock_at_level": 26, "effect": {"luck_gem_chance_percent": 8}, "effect_description": "+8% gem luck"},
    {"id": "ring_gold", "name": "Gold ring", "image": "collectibles/equip_icon_ring_gold.png", "cost_gold": 250, "unlock_with_gems": True, "unlock_at_level": 30, "effect": {"gold_bonus_percent": 10}, "effect_description": "+10% gold"},
    {"id": "coins_chest", "name": "Coin chest", "image": "currency/Coins - Chest.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 30, "effect": {"gold_flat": 8, "gold_bonus_percent": 5}, "effect_description": "+8g earned, +5% gold"},
    {"id": "axe_3", "name": "Epic axe", "image": "collectibles/equip_icon_axe_3.png", "cost_gold": 290, "unlock_with_gems": True, "unlock_at_level": 35, "effect": {"xp_bonus_percent": 6, "gold_bonus_percent": 4}, "effect_description": "+6% XP, +4% gold"},
    {"id": "potion_red_3", "name": "Red potion IV", "image": "collectibles/equip_icon_potion_red_3.png", "cost_gold": 280, "unlock_with_gems": True, "unlock_at_level": 35, "effect": {"xp_bonus_percent": 8}, "effect_description": "+8% XP"},
    {"id": "oath_ring", "name": "Oath ring", "image": "collectibles/oath_ring.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 35, "effect": {"streak_reward_bonus_percent": 50}, "effect_description": "+50% 7-day streak rewards"},

    # ============ LATE — 40, 45, 50, 55 ============
    {"id": "hammer_3", "name": "Epic hammer", "image": "collectibles/equip_icon_hammer_3.png", "cost_gold": 300, "unlock_with_gems": True, "unlock_at_level": 40, "effect": {"gold_bonus_percent": 12}, "effect_description": "+12% gold"},
    {"id": "skull", "name": "Skull", "image": "collectibles/Skull (Border).png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 40, "effect": {"gold_bonus_percent": 10, "luck_gem_chance_percent": 10}, "effect_description": "+10% gold, +10% gem luck"},
    {"id": "prism", "name": "Prism", "image": "collectibles/prism.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 40, "effect": {}, "effect_description": "Lets you trade gems in the shop"},
    {"id": "flag_snow", "name": "Snow banner", "image": "collectibles/icon_flag_snow.png", "cost_gold": 350, "unlock_with_gems": False, "unlock_at_level": 40, "effect": {"streak_reward_bonus_percent": 60}, "effect_description": "+60% 7-day streak rewards"},
    {"id": "potion_blue_1", "name": "Blue potion II", "image": "collectibles/equip_icon_potion_blue_1.png", "cost_gold": 340, "unlock_with_gems": True, "unlock_at_level": 40, "effect": {"xp_flat": 2}, "effect_description": "+2 XP/review"},
    {"id": "sword", "name": "Sword", "image": "collectibles/Sword (Border).png", "cost_gold": 350, "unlock_with_gems": True, "unlock_at_level": 45, "effect": {"luck_gem_chance_percent": 16}, "effect_description": "+16% gem luck"},
    {"id": "key_gold", "name": "Golden key", "image": "collectibles/icon_key_gold.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 45, "effect": {}, "effect_description": "2 free restocks per day instead of 1"},
    {"id": "cup_border", "name": "Trophy cup", "image": "collectibles/Cup (Border).png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 50, "effect": {"gold_bonus_percent": 15}, "effect_description": "+15% gold"},
    {"id": "eye_blue", "name": "Void's eye", "image": "collectibles/equip_icon_eye_blue.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 50, "effect": {"xp_bonus_percent": 6, "gold_bonus_percent": 6, "luck_gem_chance_percent": 10}, "effect_description": "+6% XP, +6% gold, +10% gem luck"},
    {"id": "potion_red_4", "name": "Red potion V", "image": "collectibles/equip_icon_potion_red_4.png", "cost_gold": 420, "unlock_with_gems": True, "unlock_at_level": 55, "effect": {"xp_bonus_percent": 10}, "effect_description": "+10% XP"},
    {"id": "shield_blue", "name": "Blue shield", "image": "collectibles/equip_icon_shield_blue.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 55, "effect": {"luck_gem_chance_percent": 40}, "effect_description": "+40% gem luck"},

    # ============ END GAME — 60, 70, 80, 85 (moved UP, never down) ============
    {"id": "palm_tree", "name": "Palm tree", "image": "collectibles/Palm Tree.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 60, "effect": {"gold_flat": 8}, "effect_description": "+8g earned"},
    {"id": "crown", "name": "Crown", "image": "collectibles/Crown.png", "cost_gold": 500, "unlock_with_gems": True, "unlock_at_level": 60, "effect": {"xp_bonus_percent": 4, "gold_bonus_percent": 8}, "effect_description": "+4% XP, +8% gold"},
    {"id": "shield", "name": "Shield", "image": "collectibles/Shield.png", "cost_gold": 550, "unlock_with_gems": True, "unlock_at_level": 70, "effect": {"xp_bonus_percent": 8, "gold_bonus_percent": 4}, "effect_description": "+8% XP, +4% gold"},
    {"id": "potion_blue_2", "name": "Blue potion III", "image": "collectibles/equip_icon_potion_blue_2.png", "cost_gold": 645, "unlock_with_gems": True, "unlock_at_level": 70, "effect": {"xp_flat": 3}, "effect_description": "+3 XP/review"},
    {"id": "gemstone", "name": "Gemstone", "image": "collectibles/icon_gemstone.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 70, "effect": {"gold_bonus_percent": 12, "luck_gem_chance_percent": 13}, "effect_description": "+12% gold, +13% gem luck"},
    {"id": "hammer_4", "name": "Legendary hammer", "image": "collectibles/equip_icon_hammer_4.png", "cost_gold": 580, "unlock_with_gems": True, "unlock_at_level": 80, "effect": {"gold_bonus_percent": 18}, "effect_description": "+18% gold"},
    {"id": "gemstone_rune", "name": "Rune gemstone", "image": "collectibles/icon_gemstone_rune.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 80, "effect": {"xp_bonus_percent": 10, "gold_bonus_percent": 10}, "effect_description": "+10% XP, +10% gold"},
    {"id": "axe_4", "name": "Legendary axe", "image": "collectibles/equip_icon_axe_4.png", "cost_gold": 800, "unlock_with_gems": True, "unlock_at_level": 85, "effect": {"xp_bonus_percent": 15, "gold_bonus_percent": 5}, "effect_description": "+15% XP, +5% gold"},
    # ============ VERY LATE GAME — 65 to 130 (many gold-only) ============
    {"id": "meat_feast", "name": "Meat feast", "image": "collectibles/icon_food_meat.png", "cost_gold": 380, "unlock_with_gems": False, "unlock_at_level": 65, "effect": {"xp_bonus_percent": 3, "gold_flat": 3}, "effect_description": "+3% XP, +3g earned"},
    {"id": "shield_reinf", "name": "Reinforced shield", "image": "collectibles/icon_equip_shield.png", "cost_gold": 650, "unlock_with_gems": False, "unlock_at_level": 78, "effect": {"gold_bonus_percent": 8, "xp_bonus_percent": 4}, "effect_description": "+8% gold, +4% XP"},
    {"id": "arrow_sharp", "name": "Falcon bow", "image": "collectibles/icon_equip_arrow.png", "cost_gold": 520, "unlock_with_gems": True, "unlock_at_level": 72, "effect": {"luck_gem_chance_percent": 24}, "effect_description": "+24% gem luck"},
    {"id": "lucky_necklace", "name": "Lucky necklace", "image": "collectibles/icon_accessories_necklace.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 78, "effect": {"xp_bonus_percent": 2, "gold_bonus_percent": 2}, "effect_description": "+2% XP, +2% gold"},
    {"id": "tome_begin", "name": "Tome of Beginnings", "image": "collectibles/icon_book_0.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 90, "effect": {"prestige_bonus_points": 1}, "effect_description": "+1 prestige point per prestige"},
    {"id": "candle_focus", "name": "Candle of Focus", "image": "collectibles/icon_candle.png", "cost_gold": 750, "unlock_with_gems": False, "unlock_at_level": 90, "effect": {"luck_gem_chance_percent": 32}, "effect_description": "+32% gem luck"},
    {"id": "piggy_bank", "name": "Piggy bank", "image": "collectibles/icon_piggy.png", "cost_gold": 900, "unlock_with_gems": False, "unlock_at_level": 95, "effect": {"gold_flat": 5, "gold_bonus_percent": 10}, "effect_description": "+5g earned, +10% gold"},
    {"id": "tome_ascent", "name": "Chronicle of Ascension", "image": "collectibles/icon_book_1.png", "cost_gold": 1500, "unlock_with_gems": False, "unlock_at_level": 100, "effect": {"prestige_bonus_points": 1, "xp_bonus_percent": 5}, "effect_description": "+1 prestige point per prestige, +5% XP"},
    {"id": "potion_blue_3", "name": "Blue potion IV", "image": "collectibles/equip_icon_potion_blue_3.png", "cost_gold": 1100, "unlock_with_gems": True, "unlock_at_level": 100, "effect": {"xp_flat": 4}, "effect_description": "+4 XP/review"},
    {"id": "lamp_enchanted", "name": "Enchanted lamp", "image": "collectibles/icon_lamp.png", "cost_gold": 900, "unlock_with_gems": False, "unlock_at_level": 110, "effect": {"gold_bonus_percent": 10, "luck_gem_chance_percent": 16}, "effect_description": "+10% gold, +16% gem luck"},
    {"id": "hammer_utility", "name": "War hammer", "image": "collectibles/icon_equip_hammer.png", "cost_gold": 900, "unlock_with_gems": False, "unlock_at_level": 90, "effect": {"gold_bonus_percent": 20, "xp_bonus_percent": 2}, "effect_description": "+20% gold, +2% XP"},
    {"id": "axe_utility", "name": "Battle axe", "image": "collectibles/icon_equip_ax.png", "cost_gold": 900, "unlock_with_gems": False, "unlock_at_level": 95, "effect": {"xp_bonus_percent": 17, "gold_bonus_percent": 5}, "effect_description": "+17% XP, +5% gold"},
    {"id": "elixir_insight", "name": "Elixir of Insight", "image": "collectibles/elixir_of_insight.png", "cost_gold": 1100, "unlock_with_gems": False, "unlock_at_level": 100, "effect": {"xp_bonus_percent": 12, "luck_gem_chance_percent": 8}, "effect_description": "+12% XP, +8% gem luck"},
    {"id": "royal_banner", "name": "Royal banner", "image": "collectibles/royal_banner.png", "cost_gold": 1000, "unlock_with_gems": False, "unlock_at_level": 105, "effect": {"streak_reward_bonus_percent": 75}, "effect_description": "+75% 7-day streak rewards"},
    {"id": "ancient_coin", "name": "Ancient coin", "image": "collectibles/ancient_coin.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 110, "effect": {"gold_flat": 10}, "effect_description": "+10g earned"},
    {"id": "axe_dragonbone", "name": "Dragonbone axe", "image": "collectibles/dragonbone_axe.png", "cost_gold": 1200, "unlock_with_gems": True, "unlock_at_level": 115, "effect": {"xp_bonus_percent": 20, "gold_bonus_percent": 6}, "effect_description": "+20% XP, +6% gold"},
    {"id": "hammer_titan", "name": "Titan's hammer", "image": "collectibles/titans_hammer.png", "cost_gold": 1200, "unlock_with_gems": True, "unlock_at_level": 120, "effect": {"gold_bonus_percent": 24, "xp_bonus_percent": 3}, "effect_description": "+24% gold, +3% XP"},
    {"id": "potion_blue_4", "name": "Blue potion V", "image": "collectibles/equip_icon_potion_blue_4.png", "cost_gold": 1750, "unlock_with_gems": True, "unlock_at_level": 130, "effect": {"xp_flat": 5}, "effect_description": "+5 XP/review"},
    {"id": "dragon_heart", "name": "Dragon heart", "image": "collectibles/dragon_heart.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 130, "effect": {"xp_bonus_percent": 12, "gold_bonus_percent": 12, "luck_gem_chance_percent": 15}, "effect_description": "+12% XP, +12% gold, +15% gem luck"},

    # ============ DUNGEONS — what the shop sells alongside the feature ============ Dungeon stats
    # unlock at 15 or later, when dungeons do. Steel spaulders is the gem craft beside them.
    {"id": "smoke_pipe", "name": "Smoke pipe", "image": "collectibles/smoke_pipe.png", "cost_gold": 90, "unlock_with_gems": True, "unlock_at_level": 15, "effect": {"dungeon_discover_percent": 12}, "effect_description": "+12% chance to find a dungeon"},
    {"id": "compass", "name": "Compass", "image": "collectibles/compass.png", "cost_gold": 155, "unlock_with_gems": False, "unlock_at_level": 20, "effect": {"dungeon_discover_percent": 20}, "effect_description": "+20% chance to find a dungeon"},
    {"id": "treasure_map", "name": "Treasure map", "image": "collectibles/icon_scroll_map.png", "cost_gold": 250, "unlock_with_gems": False, "unlock_at_level": 30, "effect": {"dungeon_discover_percent": 30}, "effect_description": "+30% chance to find a dungeon"},
    {"id": "scouts_bracers", "name": "Scout's bracers", "image": "collectibles/scouts_bracers.png", "cost_gold": 450, "unlock_with_gems": True, "unlock_at_level": 50, "effect": {"dungeon_discover_percent": 25, "xp_bonus_percent": 6}, "effect_description": "+25% chance to find a dungeon, +6% XP"},
    # Gold-only, so the pace can be bought deliberately rather than left to a craft.
    {"id": "crystal_ball", "name": "Crystal ball", "image": "collectibles/crystal_ball.png", "cost_gold": 220, "unlock_with_gems": False, "unlock_at_level": 22, "effect": {"dungeon_explore_percent": 12}, "effect_description": "+12% faster dungeon exploration"},
    {"id": "delvers_ring", "name": "Delver's ring", "image": "collectibles/delvers_ring.png", "cost_gold": 360, "unlock_with_gems": False, "unlock_at_level": 40, "effect": {"dungeon_explore_percent": 15}, "effect_description": "+15% faster dungeon exploration"},
    {"id": "miners_torch", "name": "Miner's torch", "image": "collectibles/miners_torch.png", "cost_gold": 280, "unlock_with_gems": False, "unlock_at_level": 32, "effect": {"dungeon_explore_percent": 15}, "effect_description": "+15% faster dungeon exploration"},
    {"id": "spelunkers_rope", "name": "Spelunker's rope", "image": "collectibles/spelunkers_rope.png", "cost_gold": 480, "unlock_with_gems": False, "unlock_at_level": 55, "effect": {"dungeon_explore_percent": 20, "xp_bonus_percent": 3}, "effect_description": "+20% faster dungeon exploration, +3% XP"},
    {"id": "cartographers_kit", "name": "Cartographer's kit", "image": "collectibles/cartographers_kit.png", "cost_gold": 650, "unlock_with_gems": False, "unlock_at_level": 75, "effect": {"dungeon_explore_percent": 20, "dungeon_discover_percent": 20}, "effect_description": "+20% faster dungeon exploration, +20% chance to find a dungeon"},
    {"id": "prospectors_pick", "name": "Prospector's pick", "image": "collectibles/prospectors_pick.png", "cost_gold": 1300, "unlock_with_gems": False, "unlock_at_level": 125, "effect": {"dungeon_explore_percent": 25, "dungeon_discover_percent": 25}, "effect_description": "+25% faster dungeon exploration, +25% chance to find a dungeon"},
    {"id": "grappling_hook", "name": "Grappling hook", "image": "collectibles/grappling_hook.png", "cost_gold": 950, "unlock_with_gems": False, "unlock_at_level": 95, "effect": {"dungeon_explore_percent": 20, "gold_bonus_percent": 12}, "effect_description": "+20% faster dungeon exploration, +12% gold"},
    {"id": "witch_hat", "name": "Witch's hat", "image": "collectibles/witch_hat.png", "cost_gold": 1100, "unlock_with_gems": False, "unlock_at_level": 100, "effect": {"dungeon_discover_percent": 40, "luck_gem_chance_percent": 16}, "effect_description": "+40% chance to find a dungeon, +16% gem luck"},
    {"id": "obsidian_axe", "name": "Obsidian axe", "image": "collectibles/obsidian_axe.png", "cost_gold": 1200, "unlock_with_gems": False, "unlock_at_level": 110, "effect": {"dungeon_explore_percent": 25, "xp_bonus_percent": 10}, "effect_description": "+25% faster dungeon exploration, +10% XP"},
    {"id": "lantern", "name": "Lantern", "image": "collectibles/lantern.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 25, "effect": {"dungeon_explore_percent": 25}, "effect_description": "+25% faster dungeon exploration"},
    {"id": "hourglass", "name": "Hourglass", "image": "ui/Hourglass.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 60, "effect": {"dungeon_explore_percent": 30}, "effect_description": "+30% faster dungeon exploration"},
    {"id": "librarians_candle", "name": "Librarian's candle", "image": "collectibles/librarians_candle.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 65, "effect": {"dungeon_explore_percent": 15, "luck_gem_chance_percent": 12}, "effect_description": "+15% faster dungeon exploration, +12% gem luck"},
    {"id": "pilgrims_locket", "name": "Pilgrim's locket", "image": "collectibles/pilgrims_locket.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 120, "effect": {"dungeon_discover_percent": 45, "streak_reward_bonus_percent": 50}, "effect_description": "+45% chance to find a dungeon, +50% 7-day streak rewards"},
    {"id": "steel_shoulders", "name": "Steel spaulders", "image": "collectibles/steel_shoulders.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 35, "effect": {"xp_bonus_percent": 4, "gold_flat": 3}, "effect_description": "+4% XP, +3g earned"},

    # ============ REFINEMENT — hidden until refinement is unlocked (see catalog) ============
    {"id": "training_shield", "name": "Training shield", "image": "collectibles/training_shield.png", "cost_gold": 130, "unlock_with_gems": True, "unlock_at_level": 16, "effect": {"luck_shard_chance_percent": 12}, "effect_description": "+12% shard luck", "needs_refinement": True},
    {"id": "sickle", "name": "Sickle", "image": "collectibles/sickle.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 30, "effect": {"luck_shard_chance_percent": 15, "luck_gem_chance_percent": 8}, "effect_description": "+15% shard luck, +8% gem luck", "needs_refinement": True},
    {"id": "cudgel", "name": "Cudgel", "image": "collectibles/cudgel.png", "cost_gold": 380, "unlock_with_gems": True, "unlock_at_level": 42, "effect": {"luck_shard_chance_percent": 18, "xp_bonus_percent": 5}, "effect_description": "+18% shard luck, +5% XP", "needs_refinement": True},
    {"id": "flail", "name": "Flail", "image": "collectibles/flail.png", "cost_gold": 420, "unlock_with_gems": True, "unlock_at_level": 48, "effect": {"luck_shard_chance_percent": 20, "dungeon_explore_percent": 12}, "effect_description": "+20% shard luck, +12% faster dungeon exploration", "needs_refinement": True},
    {"id": "tankard", "name": "Tankard", "image": "collectibles/tankard.png", "cost_gold": 470, "unlock_with_gems": True, "unlock_at_level": 55, "effect": {"luck_shard_chance_percent": 25, "gold_bonus_percent": 6}, "effect_description": "+25% shard luck, +6% gold", "needs_refinement": True},
    {"id": "spear", "name": "Spear", "image": "collectibles/spear.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 70, "effect": {"luck_shard_chance_percent": 30, "dungeon_discover_percent": 15}, "effect_description": "+30% shard luck, +15% chance to find a dungeon", "needs_refinement": True},

    # ============ DUNGEON LOOT — cost_gold None and unlock_with_gems False ============ Found only
    # in dungeon treasure. `weight` is the draw weight, read only by dungeon.py.
    {"id": "bronze_helm", "name": "Bronze helm", "image": "collectibles/bronze_helm.png", "cost_gold": None, "unlock_with_gems": False, "unlock_at_level": 15, "weight": 6, "effect": {"xp_bonus_percent": 7}, "effect_description": "+7% XP"},
    {"id": "mushroom", "name": "Mushroom", "image": "collectibles/mushroom.png", "cost_gold": None, "unlock_with_gems": False, "unlock_at_level": 15, "weight": 6, "effect": {"xp_bonus_percent": 9}, "effect_description": "+9% XP"},
    {"id": "slingshot", "name": "Slingshot", "image": "collectibles/slingshot.png", "cost_gold": None, "unlock_with_gems": False, "unlock_at_level": 15, "weight": 5, "effect": {"gold_flat": 3, "gold_bonus_percent": 7}, "effect_description": "+3g earned, +7% gold"},
    {"id": "poison", "name": "Poison", "image": "collectibles/poison.png", "cost_gold": None, "unlock_with_gems": False, "unlock_at_level": 15, "weight": 4, "effect": {"dungeon_explore_percent": 11}, "effect_description": "+11% faster dungeon exploration"},
    {"id": "skull_scroll", "name": "Skull scroll", "image": "collectibles/skull_scroll.png", "cost_gold": None, "unlock_with_gems": False, "unlock_at_level": 15, "weight": 3, "effect": {"dungeon_explore_percent": 15}, "effect_description": "+15% faster dungeon exploration"},
    {"id": "winged_shoes", "name": "Winged shoes", "image": "collectibles/winged_shoes.png", "cost_gold": None, "unlock_with_gems": False, "unlock_at_level": 15, "weight": 4, "effect": {"dungeon_discover_percent": 38}, "effect_description": "+38% chance to find a dungeon"},
    {"id": "loot_bag", "name": "Loot bag", "image": "collectibles/loot_bag.png", "cost_gold": None, "unlock_with_gems": False, "unlock_at_level": 15, "weight": 3, "effect": {"gold_bonus_percent": 5, "luck_gem_chance_percent": 8}, "effect_description": "+5% gold, +8% gem luck"},
    {"id": "red_eyed_skull", "name": "Red-eyed skull", "image": "collectibles/red_eyed_skull.png", "cost_gold": None, "unlock_with_gems": False, "unlock_at_level": 15, "weight": 2, "effect": {"luck_gem_chance_percent": 20}, "effect_description": "+20% gem luck"},
]


def default_gems() -> dict[str, int]:
    return {color: 0 for color, _ in GEM_COLORS}


# --- Key helpers ---

# Keys are a tier chain, each needing the one below. Bronze has no prerequisite and unlocks lowest,
# so the chain is always completable.
TIER_PREREQUISITE = {
    KEY_SILVER_ID: KEY_BRONZE_ID,
    KEY_GOLD_ID: KEY_SILVER_ID,
}


def tier_unlocked(cid: str, owned_ids: list[str] | set[str]) -> bool:
    """True if the tier chain allows this collection to obtain `cid` yet. Applied to both crafting
    and the shop pool."""
    prereq = TIER_PREREQUISITE.get(cid)
    return prereq is None or prereq in owned_ids


def has_bronze_key(owned_ids: list[str]) -> bool:
    """True if player owns Bronze key (unlocks shop refresh)."""
    return KEY_BRONZE_ID in owned_ids


def has_silver_key(owned_ids: list[str]) -> bool:
    """True if player owns Silver key (faster refresh)."""
    return KEY_SILVER_ID in owned_ids


def has_gold_key(owned_ids: list[str]) -> bool:
    """True if player owns Golden key (free daily refresh)."""
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
    """The gem colors a craft charges: all, or all but the scarcest held while the discount buff
    runs. Ties break on GEM_COLORS order so the preview and spend agree."""
    colors = [c for c, _ in GEM_COLORS]
    if data is None:
        return colors
    from . import milestones

    if not milestones.buff_is_active(data, milestones.BUFF_CRAFT_CHEAPER):
        return colors
    scarcest = min(colors, key=lambda c: (gems.get(c, 0), colors.index(c)))
    return [c for c in colors if c != scarcest]


def can_craft(gems: dict[str, int], offer: tuple[dict[str, Any], int, tuple[str, ...]]) -> bool:
    """True if `gems` pay a craft_offer: its price in every color it charges."""
    _, each, colors = offer
    return all(gems.get(c, 0) >= each for c in colors)


# A craft costs one gem of each color per this many levels of the item's unlock level, rounded up.
CRAFT_LEVELS_PER_GEM = 30


def craft_price_each(c: dict[str, Any]) -> int:
    """Gems of each color crafting `c` costs."""
    return max(1, -(-_unlock_at_level(c) // CRAFT_LEVELS_PER_GEM))


def craft_band_label(c: dict[str, Any]) -> str:
    """The level range sharing `c`'s price, as the Craft button names it, e.g. "61–90"."""
    each = craft_price_each(c)
    return f"{CRAFT_LEVELS_PER_GEM * (each - 1) + 1}\u2013{CRAFT_LEVELS_PER_GEM * each}"


# Gem trade, unlocked by the Prism: the most-held color for the scarcest, 2 for 1 at the start of
# each day and one gem dearer per trade after that.
PRISM_ID = "prism"
GEM_TRADE_COST_BASE = 2


def has_gem_trade(data: dict[str, Any]) -> bool:
    return PRISM_ID in data.get("owned_collectibles", [])


def _gem_trades_today(data: dict[str, Any], today: str) -> int:
    return int(data.get("gem_trade_uses", 0) or 0) if data.get("gem_trade_date") == today else 0


def gem_trade_cost(data: dict[str, Any]) -> int:
    """Gems the next trade takes."""
    return GEM_TRADE_COST_BASE + _gem_trades_today(data, _today_str())


def gem_trade_offer(data: dict[str, Any]) -> tuple[str, int, str] | None:
    """(give, cost, get) for the next trade, or None if it wouldn't even the colors out. Ties are
    drawn at random and kept until the gems change, so the button names what it takes. Caller saves."""
    gems = data.get("gems") or default_gems()
    counts = {c: int(gems.get(c, 0) or 0) for c, _ in GEM_COLORS}
    pick = data.get("gem_trade_pick") or {}
    if pick.get("gems") != counts:
        most = max(counts.values())
        pick = {
            "gems": counts,
            "give": random.choice([c for c, n in counts.items() if n == most]),
            "get": most_needed_gem_color(counts),  # same tie-break as the shop's most-needed gem
        }
        data["gem_trade_pick"] = pick
    give, get, cost = pick["give"], pick["get"], gem_trade_cost(data)
    if give == get or counts[give] - cost < counts[get] + 1:
        return None
    return (give, cost, get)


def trade_gem_colors(data: dict[str, Any]) -> tuple[str, int, str] | None:
    """Make the offered trade and return it, or None if there is none. Caller saves."""
    offer = gem_trade_offer(data) if has_gem_trade(data) else None
    if offer is None:
        return None
    give, cost, get = offer
    gems = dict(data.get("gems") or default_gems())
    gems[give] = int(gems.get(give, 0) or 0) - cost
    gems[get] = int(gems.get(get, 0) or 0) + 1
    data["gems"] = gems
    today = _today_str()
    data["gem_trade_uses"] = _gem_trades_today(data, today) + 1
    data["gem_trade_date"] = today
    data.pop("gem_trade_pick", None)
    return offer


def _unlock_at_level(c: dict[str, Any]) -> int:
    """Level at which this collectible becomes visible in the shop (default 1)."""
    return c.get("unlock_at_level", 1)


def discounted_gold(data: dict[str, Any] | None, cost: int) -> int:
    """A shop price after the discount buff, rounded up and never below 1. Every shown or charged
    price goes through here."""
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
    """What a gem or Magnet slot charges now, discounted on read so the price tracks the buff."""
    return discounted_gold(data, int(slot.get("cost", default) or 0))


def catalog(data: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Every item the game admits to. Refinement items stay hidden until refinement is unlocked, so
    every count and pool that takes `data` acts as if they don't exist; no `data` means all."""
    if data is None or refinement_unlocked(data):
        return COLLECTIBLES
    return [c for c in COLLECTIBLES if not c.get("needs_refinement")]


def collectibles_for_gold(data: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Collectibles that can be bought with gold (have a gold price). Use collectibles_for_gold_at_level(level) to filter by level."""
    return [c for c in catalog(data) if c.get("cost_gold") is not None]


def collectibles_for_gold_at_level(level: int, data: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Collectibles buyable with gold that are unlocked at this level."""
    return [c for c in collectibles_for_gold(data) if level >= _unlock_at_level(c)]


def gem_only_collectibles(data: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Collectibles with no gold price that a gem craft can still produce."""
    return [
        c for c in catalog(data)
        if c.get("cost_gold") is None and c.get("unlock_with_gems", True)
    ]


def is_loot(c: dict[str, Any]) -> bool:
    """Dungeon loot: no gold price and no gem craft, so the shop can't supply it."""
    return c.get("cost_gold") is None and not c.get("unlock_with_gems", True)


def loot_collectibles() -> list[dict[str, Any]]:
    """Every dungeon loot item, for the dungeon's treasure pool and the loot counts; both shop pool
    builders exclude them already."""
    return [c for c in COLLECTIBLES if is_loot(c)]


def origin_note(c: dict[str, Any]) -> str:
    """An item's level as the Items window tags it, or "dungeon" for loot, which has no level."""
    return "dungeon" if is_loot(c) else f"lvl {_unlock_at_level(c)}"


def collectibles_for_gems(data: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Collectibles a gem craft can make. Use collectibles_for_gems_at_level(level) to filter by level."""
    return [c for c in catalog(data) if c.get("unlock_with_gems", True)]


def collectibles_for_gems_at_level(level: int, data: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Collectibles a gem craft can make that are unlocked at this level."""
    return [c for c in collectibles_for_gems(data) if level >= _unlock_at_level(c)]


_BY_ID: dict[str, dict[str, Any]] = {c["id"]: c for c in COLLECTIBLES}


def get_collectible(cid: str) -> dict[str, Any] | None:
    return _BY_ID.get(cid)


# --- Item quality and refinement ----------------------------------------------------------------
# Quality is kept beside the collection (id -> tier), never in it, so ownership checks such as the
# XP trades' are untouched. Design: drafts/item-quality.md.
QUALITY_KEY = "item_quality"
QUALITY_NORMAL, QUALITY_FINE, QUALITY_SUPERIOR = 0, 1, 2
QUALITY_NAMES = {QUALITY_FINE: "Fine", QUALITY_SUPERIOR: "Superior"}
QUALITY_MULTIPLIERS = {QUALITY_NORMAL: 1.0, QUALITY_FINE: 1.25, QUALITY_SUPERIOR: 1.6}
# Prestige points are whole with no fractional carry, so quality adds one per tier instead of
# multiplying, and refining an item that grants them costs this many times the usual price.
POINT_EFFECTS = ("prestige_bonus_points",)
POINT_STEP_COST_FACTOR = 5
# Chance a shop offer or a craft comes out Fine; dungeon items roll their own at the reveal.
SHOP_FINE_PERCENT = 5
LOOT_FINE_PERCENT = 25
LOOT_SUPERIOR_PERCENT = 12.5

SHARDS_KEY = "shards"
SHARD_COST_GOLD = 50
# Refinement opens one band per prestige level, the bands gem crafting prices by.
REFINEMENT_BANDS_MAX = 5

# How each stat reads in an item's effect text; quality versions are written from these.
EFFECT_PHRASES = {
    "xp_bonus_percent": "+{}% XP",
    "xp_flat": "+{} XP/review",
    "gold_bonus_percent": "+{}% gold",
    "gold_flat": "+{}g earned",
    "luck_gem_chance_percent": "+{}% gem luck",
    "luck_shard_chance_percent": "+{}% shard luck",
    "streak_reward_bonus_percent": "+{}% 7-day streak rewards",
    "dungeon_discover_percent": "+{}% chance to find a dungeon",
    "dungeon_explore_percent": "+{}% faster dungeon exploration",
    "prestige_bonus_points": "+{} prestige point",
}


def _phrase(key: str, value: float) -> str:
    """One stat as its effect text reads it, "points" plural from 2 on."""
    text = EFFECT_PHRASES[key].format(format_amount(value))
    return text + "s" if key in POINT_EFFECTS and value != 1 else text


def format_amount(value: float) -> str:
    """A stat as shown: up to 2 decimals, halves up, trailing zeros dropped (1.25, 2.5, 3)."""
    # Float noise is rounded off first, so a 56.975 held as 56.974999 can't fall to 56.97.
    shown = Decimal(repr(round(value, 6))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{shown:f}".rstrip("0").rstrip(".")


def refinement_bands(data: dict[str, Any]) -> int:
    """Level bands refinement is unlocked for (prestige), 0 before the first."""
    from . import prestige

    return prestige.refinement_bands(data)


def refinement_unlocked(data: dict[str, Any]) -> bool:
    """The one gate for everything Shard: drops, the pathway, the shop, the buff, the new items."""
    return refinement_bands(data) >= 1


def quality_map(data: dict[str, Any]) -> dict[str, int]:
    q = data.get(QUALITY_KEY)
    return q if isinstance(q, dict) else {}


def item_quality(data: dict[str, Any], cid: str) -> int:
    try:
        return max(QUALITY_NORMAL, min(QUALITY_SUPERIOR, int(quality_map(data).get(cid, 0) or 0)))
    except (TypeError, ValueError):
        return QUALITY_NORMAL


def set_item_quality(data: dict[str, Any], cid: str, quality: int) -> None:
    """Record an owned item's quality; Normal is stored as absence."""
    q = dict(quality_map(data))
    if quality > QUALITY_NORMAL:
        q[cid] = int(quality)
    else:
        q.pop(cid, None)
    data[QUALITY_KEY] = q


def has_quality(c: dict[str, Any]) -> bool:
    """Whether quality changes anything: the keys and the Prism have no stats for it to raise."""
    return bool(c.get("effect"))


def display_name(c: dict[str, Any], quality: int = QUALITY_NORMAL) -> str:
    """The name with its quality in front, the name's own capitals kept: "Fine Titan's hammer"."""
    name = c.get("name", c.get("id", ""))
    return f"{QUALITY_NAMES[quality]} {name}" if quality in QUALITY_NAMES else name


def effect_value(c: dict[str, Any], key: str, quality: int = QUALITY_NORMAL) -> float:
    base = (c.get("effect") or {}).get(key, 0)
    if key in POINT_EFFECTS:
        return base + quality if base else base
    return base * QUALITY_MULTIPLIERS.get(quality, 1.0)


def effect_text(c: dict[str, Any], quality: int = QUALITY_NORMAL) -> str:
    """The item's effect line at a quality: the hand-written one, its numbers scaled."""
    text = (c.get("effect_description") or "").strip()
    if quality == QUALITY_NORMAL:
        return text
    for key, value in (c.get("effect") or {}).items():
        if key in EFFECT_PHRASES:
            text = text.replace(_phrase(key, value), _phrase(key, effect_value(c, key, quality)), 1)
    return text


def roll_shop_quality(c: dict[str, Any]) -> int:
    """A shop offer's or a craft's quality: Fine at SHOP_FINE_PERCENT."""
    if has_quality(c) and random.random() * 100 < SHOP_FINE_PERCENT:
        return QUALITY_FINE
    return QUALITY_NORMAL


def roll_loot_quality(c: dict[str, Any]) -> int:
    """A dungeon item's quality, rolled when the treasure room reveals it."""
    if not has_quality(c):
        return QUALITY_NORMAL
    roll = random.random() * 100
    if roll < LOOT_SUPERIOR_PERCENT:
        return QUALITY_SUPERIOR
    if roll < LOOT_SUPERIOR_PERCENT + LOOT_FINE_PERCENT:
        return QUALITY_FINE
    return QUALITY_NORMAL


def shards(data: dict[str, Any]) -> int:
    return max(0, int(data.get(SHARDS_KEY, 0) or 0))


def add_shards(data: dict[str, Any], count: int) -> None:
    data[SHARDS_KEY] = shards(data) + max(0, int(count))


def shard_word(count: int) -> str:
    return f"{count} shard" + ("s" if count != 1 else "")


def is_refinable(c: dict[str, Any]) -> bool:
    """Has a level band and something to raise; dungeon loot (no gold price, no craft) has no band."""
    return has_quality(c) and not is_loot(c)


# The Superior step adds +35% to Fine's +25%, so it costs twice as much: less per shard, a sink.
SUPERIOR_STEP_COST_FACTOR = 2


def refine_cost(c: dict[str, Any], quality: int = QUALITY_NORMAL) -> int:
    """Shards the next step from `quality` costs: one per 30 levels of the item's level, like gem
    crafting, doubled for Fine to Superior, and POINT_STEP_COST_FACTOR times that for a tome."""
    factor = SUPERIOR_STEP_COST_FACTOR if quality == QUALITY_FINE else 1
    if any(k in POINT_EFFECTS for k in (c.get("effect") or {})):
        factor *= POINT_STEP_COST_FACTOR
    return craft_price_each(c) * factor


# What refine_status reports for an owned item, besides "ready" and "poor".
REFINE_READY = "ready"
REFINE_POOR = "poor"
REFINE_MAXED = "maxed"
REFINE_LOCKED = "locked"
REFINE_NEVER = "never"


def refine_status(data: dict[str, Any], cid: str) -> str:
    """Whether an owned item can be refined now, and if not why."""
    c = get_collectible(cid)
    if c is None or cid not in data.get("owned_collectibles", []) or not is_refinable(c):
        return REFINE_NEVER
    if item_quality(data, cid) >= QUALITY_SUPERIOR:
        return REFINE_MAXED
    if craft_price_each(c) > refinement_bands(data):
        return REFINE_LOCKED
    return REFINE_READY if shards(data) >= refine_cost(c, item_quality(data, cid)) else REFINE_POOR


def refine_item(data: dict[str, Any], cid: str) -> bool:
    """Spend the Shards and raise the item one tier. Always succeeds once paid. Caller saves."""
    if refine_status(data, cid) != REFINE_READY:
        return False
    c = get_collectible(cid)
    data[SHARDS_KEY] = shards(data) - refine_cost(c, item_quality(data, cid))
    set_item_quality(data, cid, item_quality(data, cid) + 1)
    return True


def _today_str() -> str:
    """Scheduler day (honors 'Next day starts at'), not civil midnight."""
    from . import streak
    return streak.today_str()


def _all_at_level(level: int) -> list[dict[str, Any]]:
    """All collectibles (gold + gem-only) available at this level."""
    return [c for c in COLLECTIBLES if level >= _unlock_at_level(c)]


# Three entries, not one, so each gem kind competes for a slot on its own and a restock can offer
# any mix of them. The kind is fixed when the pool is built, which is what lets them appear together.
_GEM_PLACEHOLDERS: tuple[dict[str, Any], ...] = (
    {"type": "gem_placeholder", "kind": "random"},
    {"type": "gem_placeholder", "kind": "most_needed"},
    {"type": "gem_placeholder", "kind": "specific"},
)


def most_needed_gem_color(gems: dict[str, int]) -> str:
    """The color the player holds fewest of, ties broken at random (not "rarest": ties are the
    common case)."""
    counts = [(gems.get(c, 0), c) for c, _ in GEM_COLORS]
    fewest = min(n for n, _ in counts)
    return random.choice([c for n, c in counts if n == fewest])


def _gem_slot_of_kind(kind: str, gems: dict[str, int] | None = None) -> dict[str, Any]:
    """Build the gem slot a placeholder resolves to. Most-needed resolves its color now, since the
    slot shows the gem's icon; later gains don't retarget it."""
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
    """The items a gem craft can produce: unowned, unlocked, tier prerequisite met. Targeted craft
    narrows to items with no gold price, falling back once they're owned."""
    # collectibles_for_gems_at_level, not _all_at_level: a craft used to be able to hand you an
    # item the shop only ever sells for gold, which is not a craft's to give.
    pool = [
        c for c in collectibles_for_gems_at_level(level, data)
        if c["id"] not in owned and tier_unlocked(c["id"], owned)
    ]
    if data is None:
        return pool
    from . import milestones

    if not milestones.has_targeted_craft(data):
        return pool
    gem_only = [c for c in pool if c.get("cost_gold") is None]
    return gem_only or pool


def _build_daily_slot_pool(
    level: int, owned: set[str] | None = None, data: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Pool for shop slots: collectibles (gold at level, not owned) plus one entry per gem kind, so
    a restock can offer several gems, and one for Shards once refinement is unlocked."""
    owned = owned or set()
    pool: list[dict[str, Any]] = []
    for c in collectibles_for_gold_at_level(level, data):
        if c["id"] not in owned and tier_unlocked(c["id"], owned):
            pool.append({"type": "collectible", "id": c["id"]})
    pool.extend(dict(g) for g in _GEM_PLACEHOLDERS)
    if data is not None and refinement_unlocked(data):
        pool.append({"type": "shards_placeholder"})
    return pool


def _draw_slots(pool: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    """Draw n distinct pool entries, gem offers at GEM_SLOT_WEIGHT. Shuffled, so the lighter gems
    don't settle in the last slots."""
    rest = list(pool)
    weights = [GEM_SLOT_WEIGHT if s.get("type") == "gem_placeholder" else 1.0 for s in rest]
    out: list[dict[str, Any]] = []
    for _ in range(min(n, len(rest))):
        # Nothing but weight-0 gems left: an even draw, where random.choices would raise.
        pick = random.choices(range(len(rest)), weights=weights if any(weights) else None)[0]
        out.append(rest.pop(pick))
        weights.pop(pick)
    random.shuffle(out)
    return out


def _restock(data: dict[str, Any], level: int) -> list[dict[str, Any]]:
    """Draw a fresh set of slots: placeholders resolved, each item's quality rolled now so the slot
    shows it, and maybe a Magnet."""
    owned = set(data.get("owned_collectibles", []))
    pool = _build_daily_slot_pool(level, owned, data)
    out: list[dict[str, Any]] = []
    for s in _draw_slots(pool, shop_slot_count(data)):
        kind = s.get("type")
        if kind == "gem_placeholder":
            # The player's own gems, so a most-needed slot targets the color actually short.
            out.append(_gem_slot_of_kind(s.get("kind", "specific"), data.get("gems", default_gems())))
        elif kind == "shards_placeholder":
            out.append({"type": "shards", "cost": SHARD_COST_GOLD})
        else:
            c = get_collectible(s.get("id", ""))
            quality = roll_shop_quality(c) if c else QUALITY_NORMAL
            out.append({**s, "quality": quality} if quality else s)
    _maybe_place_magnet_slot(data, out)
    return out


def _now_timestamp() -> int:
    """Current time as Unix timestamp (seconds)."""
    return int(datetime.now().timestamp())


def get_shop_refresh_remaining(data: dict[str, Any]) -> int:
    """Seconds until shop auto-refreshes. 0 if refresh is due."""
    last_refresh = data.get("shop_last_refresh_time", 0)
    elapsed = _now_timestamp() - last_refresh
    owned = data.get("owned_collectibles", [])
    interval = get_refresh_interval(owned)
    # Clamped to the interval as well as to zero: a timestamp in the future (clock moved back, save
    # from a machine running ahead) would otherwise hold the shop shut until real time caught up.
    remaining = interval - elapsed
    return max(0, min(interval, remaining))


def get_daily_slots(data: dict[str, Any], level: int) -> list[dict[str, Any]]:
    """The shop's slots, rerolled when there are none or the auto-refresh timer expired. Mutates
    data."""
    slots = data.get("shop_daily_slots", [])
    remaining = get_shop_refresh_remaining(data)
    if not slots or remaining == 0:
        data["shop_last_refresh_time"] = _now_timestamp()
        data["shop_daily_slots"] = _restock(data, level)
        slots = data["shop_daily_slots"]
    return slots


# Why a Magnet purchase failed. Returned instead of a bare False so the shop can say which it was -
# "Not enough gold" is wrong for three of the four.
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
    """Turn one slot of a fresh restock into a Magnet at MAGNET_DROP_PERCENT; rolled per restock
    (automatic and manual) so it isn't a permanent fixture."""
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
    """Buy the Magnet slot. Returns the stage it completed, True if it merely counted, or a
    MAGNET_BUY_* reason. Marked sold, not removed, so the grid doesn't reflow."""
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


def buy_shards(data: dict[str, Any], slot: dict[str, Any]) -> bool:
    """Buy the Shard slot's one Shard; shard luck and the buff don't touch purchases. Marks it sold."""
    if slot.get("sold") or slot.get("type") != "shards":
        return False
    cost = slot_cost(data, slot, SHARD_COST_GOLD)
    if cost <= 0 or data.get("money", 0) < cost:
        return False
    data["money"] = data["money"] - cost
    add_shards(data, 1)
    slot["sold"] = True
    return True


def buy_collectible(data: dict[str, Any], cid: str, level: int) -> bool:
    """Buy an item today's slots offer, at the quality its slot rolled. Mutates data."""
    c = get_collectible(cid)
    slot = next((s for s in data.get("shop_daily_slots", [])
                 if s.get("type") == "collectible" and s.get("id") == cid), None)
    if c is None or slot is None or cid in data.get("owned_collectibles", []):
        return False
    cost = effective_cost_gold(c, level, data)
    if cost <= 0 or data.get("money", 0) < cost:
        return False
    data["money"] = data["money"] - cost
    data.setdefault("owned_collectibles", []).append(cid)
    set_item_quality(data, cid, int(slot.get("quality", 0) or 0))
    return True


def buy_gem_option(data: dict[str, Any], slot: dict[str, Any]) -> bool:
    """Buy one gem from a slot ({"color", "cost"} or {"random", "cost"}; most-needed carries its
    color). Marks the slot sold. Mutates data and slot. Returns True if purchased."""
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


def kept_craft(data: dict[str, Any], level: int) -> dict[str, Any] | None:
    """The stored next craft while it can still be crafted. Judged at its own level too, so undoing
    the level-up that unlocked it doesn't drop it."""
    stored = get_collectible(data.get("next_craft_id") or "")
    if stored is None:
        return None
    owned = set(data.get("owned_collectibles", []))
    pool = craft_pool(max(level, _unlock_at_level(stored)), owned, data)
    return stored if any(c["id"] == stored["id"] for c in pool) else None


def next_craft(data: dict[str, Any], level: int) -> dict[str, Any] | None:
    """The item the next craft gives, rolled ahead so its price can be shown. Kept until crafted or
    gone from the pool, so waiting for a level-up can't swap it for a cheaper one. Mutates data;
    caller saves."""
    kept = kept_craft(data, level)
    if kept is not None:
        return kept
    pool = craft_pool(level, set(data.get("owned_collectibles", [])), data)
    if not pool:
        data["next_craft_id"] = None
        return None
    weights = [1.0 / (1 + min(max(0, level - _unlock_at_level(c)), GEM_CRAFT_MAX_DISTANCE)) for c in pool]
    c = random.choices(pool, weights=weights, k=1)[0]
    data["next_craft_id"] = c["id"]
    return c


def craft_offer(
    data: dict[str, Any], level: int
) -> tuple[dict[str, Any], int, tuple[str, ...]] | None:
    """The next craft as the Craft button shows it: (item, gems of each color, colors charged), or
    None with nothing to craft. Mutates data like next_craft; caller saves."""
    c = next_craft(data, level)
    if c is None:
        return None
    return (c, craft_price_each(c), tuple(craft_required_colors(data.get("gems", default_gems()), data)))


def craft_next(
    data: dict[str, Any], level: int, col: Any = None
) -> tuple[str | None, dict[str, Any] | None]:
    """Pay the next craft's price for its item, then roll the one after. Returns (cid, collectible),
    or (None, None). Mutates data."""
    offer = craft_offer(data, level)
    gems = data.get("gems", default_gems())
    if offer is None or not can_craft(gems, offer):
        return (None, None)
    c, each, colors = offer
    cid = c["id"]
    data["gems"] = {color: gems[color] - (each if color in colors else 0) for color, _ in GEM_COLORS}
    data.setdefault("owned_collectibles", []).append(cid)
    # Rolled now rather than with the next craft, so the hidden next craft stays a surprise.
    set_item_quality(data, cid, roll_shop_quality(c))
    next_craft(data, level)

    # Counted here rather than at the call site so every path that crafts an item is counted,
    # including any future one. Deferred import: shop is imported by most of the package.
    from . import milestones

    milestones.note_event(data, milestones.OBJ_CRAFT)
    # With the collection: a milestone completing here can raise the accumulator's cap, and that
    # restarts its ramp, which needs to know what day it is.
    milestones.advance_if_complete(data, col)
    return (cid, c)


def has_refresh_unlocked(data: dict[str, Any]) -> bool:
    """True if player owns any key (bronze, silver, gold) that unlocks the shop refresh button."""
    owned = data.get("owned_collectibles", [])
    return can_refresh_shop(owned)


def has_free_refresh_available(data: dict[str, Any]) -> bool:
    """True if player has free refresh(es) left today. Any key: 1 free/day; Golden key: 2 free/day."""
    if not has_refresh_unlocked(data):
        return False
    today = _today_str()
    last_date = data.get("shop_last_free_refresh_date", "")
    used_today = data.get("shop_free_refreshes_used_today", 0) if (last_date == today) else 0
    free_per_day = 2 if has_gold_key(data.get("owned_collectibles", [])) else 1
    return used_today < free_per_day


def get_refresh_cost(data: dict[str, Any]) -> int:
    """Gold cost of the next refresh: 0 if a free one is left today or refresh isn't unlocked, else
    15g rising by 15g per use."""
    if not has_refresh_unlocked(data):
        return 0
    if has_free_refresh_available(data):
        return 0
    # Falls through to the escalating price below, which the discount then applies to.
    uses = data.get("shop_refresh_uses", 0)
    return discounted_gold(data, REFRESH_COST_BASE + REFRESH_COST_INCREMENT * uses)


def refresh_shop(data: dict[str, Any], level: int) -> bool:
    """Reroll the shop's slots and reset the auto-refresh timer; needs a key. Uses a free refresh if
    left (1/day, 2 with the Golden key), else pays refresh_cost. Returns True if refreshed."""
    if not has_refresh_unlocked(data):
        return False
    is_free = has_free_refresh_available(data)
    cost = 0 if is_free else get_refresh_cost(data)
    money = data.get("money", 0)
    if not is_free and money < cost:
        return False
    out = _restock(data, level)
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


def _sum_effect(owned_ids: list[str], key: str, quality: dict[str, int] | None = None) -> float:
    """Sum a numeric effect across owned collectibles, each at its quality (quality_map)."""
    total = 0.0
    quality = quality or {}
    for cid in owned_ids:
        c = get_collectible(cid)
        if c and c.get("effect"):
            total += effect_value(c, key, int(quality.get(cid, 0) or 0))
    return total


def xp_bonus_percent(owned_ids: list[str], quality: dict[str, int] | None = None) -> float:
    """Total XP bonus from owned collectibles (e.g. 3 for +3%)."""
    return _sum_effect(owned_ids, "xp_bonus_percent", quality)


def gold_bonus_percent(owned_ids: list[str], quality: dict[str, int] | None = None) -> float:
    """Total gold bonus from owned collectibles (e.g. 2 for +2%)."""
    return _sum_effect(owned_ids, "gold_bonus_percent", quality)


def gold_flat(owned_ids: list[str], quality: dict[str, int] | None = None) -> float:
    """Total flat gold bonus from owned collectibles (added to level-up and streak gold, half to
    quest gold). A fraction with quality; the carry pays it out."""
    return _sum_effect(owned_ids, "gold_flat", quality)


def xp_flat(owned_ids: list[str], quality: dict[str, int] | None = None) -> float:
    """Total flat XP bonus from owned collectibles (added to review XP, except Again/Hard-in-hard-mode)."""
    return _sum_effect(owned_ids, "xp_flat", quality)


def streak_reward_bonus_percent(owned_ids: list[str], quality: dict[str, int] | None = None) -> float:
    """Total 7-day streak reward bonus % from owned collectibles (see streak.grant_streak_reward)."""
    return _sum_effect(owned_ids, "streak_reward_bonus_percent", quality)


def luck_gem_chance_percent(owned_ids: list[str], quality: dict[str, int] | None = None) -> float:
    """Total luck chance (e.g. 5 = 5% chance +1 extra gem on quest/level-up)."""
    return _sum_effect(owned_ids, "luck_gem_chance_percent", quality)


def dungeon_discover_percent(owned_ids: list[str], quality: dict[str, int] | None = None) -> float:
    """Total bonus to the dungeon entrance chance, as a percent (e.g. 15 for +15%)."""
    return _sum_effect(owned_ids, "dungeon_discover_percent", quality)


def dungeon_explore_percent(owned_ids: list[str], quality: dict[str, int] | None = None) -> float:
    """Total bonus to the branching-pathway chance: "faster dungeon exploration"."""
    return _sum_effect(owned_ids, "dungeon_explore_percent", quality)


def luck_shard_chance_percent(owned_ids: list[str], quality: dict[str, int] | None = None) -> float:
    """Total shard luck, which multiplies every Shard chance as gem luck does gem chances."""
    return _sum_effect(owned_ids, "luck_shard_chance_percent", quality)


def prestige_bonus_points(owned_ids: list[str], quality: dict[str, int] | None = None) -> int:
    """Extra prestige points granted per prestige by owned collectibles (the two tomes), +1 for
    each quality tier."""
    return int(_sum_effect(owned_ids, "prestige_bonus_points", quality))


def shop_supplied_collectibles(data: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Everything the shop or a craft can eventually hand over: the collection minus dungeon loot."""
    loot = {c["id"] for c in loot_collectibles()}
    return [c for c in catalog(data) if c["id"] not in loot]


def _owns_all(data: dict[str, Any], pool: list[dict[str, Any]]) -> bool:
    """Whether every item in `pool` is owned. Neither caller's pool holds dungeon loot, which no save
    realistically collects all of."""
    owned = set(data.get("owned_collectibles", []))
    return all(c["id"] in owned for c in pool)


def owns_all_gold_items(data: dict[str, Any]) -> bool:
    """True once every item with a gold price is owned, at any level. Opens the gold-for-XP trade."""
    return _owns_all(data, collectibles_for_gold(data))


def owns_all_craftable(data: dict[str, Any]) -> bool:
    """True once every item a craft can make is owned, at any level. Opens the gems-for-XP trade."""
    return _owns_all(data, collectibles_for_gems(data))


# A Magnet on sale. Flat, like what it buys: later stages ask for more Magnets, not dearer ones.
MAGNET_COST_GOLD = 50

# Late-game trade rates; each trade opens once its currency has nothing left to buy.
TRADE_GOLD_TO_XP_RATE = 3   # 1 gold -> 3 XP
# A gem is worth what the cheapest gem slot charges for one, so buying gems to trade them gains
# nothing over the gold trade (the shop discount buff aside).
TRADE_GEM_TO_XP_RATE = GEM_COST_RANDOM * TRADE_GOLD_TO_XP_RATE  # 1 gem -> 90 XP


def _pay_level_up(data: dict[str, Any]) -> None:
    """Update the stored level for XP a trade just paid, and grant its level-ups. Imported inside,
    since review_rewards imports this module."""
    from . import review_rewards

    review_rewards.grant_level_up(
        data, data.get("level", 1), data.get("owned_collectibles", [])
    )


def trade_gold_for_xp(data: dict[str, Any]) -> int:
    """Convert all gold to XP at 1g = 3 XP; the shop offers it once every gold item is owned.
    Returns XP added. Levels crossed pay normally, so gold may come back."""
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
    """Convert all gems to XP at TRADE_GEM_TO_XP_RATE; the shop offers it once every craftable item
    is owned. Returns XP added. Levels crossed pay normally, returning some gold and gems."""
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
