"""Shop, gems and collectibles: the restocking shop slots (collectibles, gem kinds, a Magnet), gem
crafting, key-unlocked refreshes, and the endgame XP trades. Rules for players are in the wiki."""
from __future__ import annotations

import random
from datetime import datetime
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

# Refresh (unlocked by owning a key): 1 free per day (2 with Golden Key), then 15g first paid, +15g per use.
REFRESH_COST_BASE = 15
REFRESH_COST_INCREMENT = 15

# Shop auto-refresh interval (seconds). DEFAULT applies with or without a key.
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

# Collectible: id, name, image, cost_gold (None = no gold price), unlock_with_gems, unlock_at_level,
# effect, effect_description, rarity. Bag, Star and Ticket are UI-only and not listed here.
COLLECTIBLES: list[dict[str, Any]] = [
    # ============ EARLY — unlocks at 1, 2, 3, 5, 8, 10, 14 ============
    {"id": "stone", "name": "Stone", "image": "collectibles/equip_icon_stone.png", "cost_gold": 18, "unlock_with_gems": True, "unlock_at_level": 1, "effect": {"xp_bonus_percent": 1}, "effect_description": "+1% XP", "rarity": "common"},
    {"id": "cup", "name": "Cup", "image": "collectibles/Cup.png", "cost_gold": 25, "unlock_with_gems": True, "unlock_at_level": 1, "effect": {"gold_flat": 2}, "effect_description": "+2g earned", "rarity": "common"},
    {"id": "package", "name": "Package", "image": "collectibles/Package.png", "cost_gold": 28, "unlock_with_gems": True, "unlock_at_level": 1, "effect": {"luck_gem_chance_percent": 3}, "effect_description": "+3% gem luck", "rarity": "common"},
    # --- Level 2 ---
    {"id": "bracelet", "name": "Bracelet", "image": "collectibles/equip_icon_bracelet.png", "cost_gold": 40, "unlock_with_gems": True, "unlock_at_level": 2, "effect": {"gold_flat": 2, "xp_bonus_percent": 1}, "effect_description": "+2g earned, +1% XP", "rarity": "common"},
    {"id": "potion_red_0", "name": "Red Potion", "image": "collectibles/equip_icon_potion_red_0.png", "cost_gold": 40, "unlock_with_gems": True, "unlock_at_level": 2, "effect": {"xp_bonus_percent": 2}, "effect_description": "+2% XP", "rarity": "common"},
    # --- Level 3 ---
    {"id": "fish", "name": "Fish", "image": "collectibles/equip_icon_fish.png", "cost_gold": 42, "unlock_with_gems": True, "unlock_at_level": 3, "effect": {"luck_gem_chance_percent": 5}, "effect_description": "+5% gem luck", "rarity": "common"},
    # --- Level 5 (gap 4) ---
    {"id": "hard_tooth", "name": "Hard Tooth", "image": "collectibles/equip_icon_hard_tooth.png", "cost_gold": 45, "unlock_with_gems": True, "unlock_at_level": 5, "effect": {"gold_flat": 3}, "effect_description": "+3g earned", "rarity": "common"},
    {"id": "poison_tooth", "name": "Poison Tooth", "image": "collectibles/equip_icon_posion_tooth.png", "cost_gold": 50, "unlock_with_gems": True, "unlock_at_level": 5, "effect": {"luck_gem_chance_percent": 5}, "effect_description": "+5% gem luck", "rarity": "common"},
    {"id": "tooth_red", "name": "Red Teeth", "image": "collectibles/equip_icon_teeth_red.png", "cost_gold": 48, "unlock_with_gems": True, "unlock_at_level": 5, "effect": {"gold_flat": 2, "gold_bonus_percent": 2}, "effect_description": "+2g earned, +2% gold", "rarity": "common"},
    {"id": "potion_blue_0", "name": "Blue Potion", "image": "collectibles/equip_icon_potion_blue_0.png", "cost_gold": 95, "unlock_with_gems": True, "unlock_at_level": 5, "effect": {"xp_flat": 1}, "effect_description": "+1 XP/review", "rarity": "common"},
    # --- Level 8 (gap 6–7) ---
    {"id": "crystal", "name": "Crystal", "image": "collectibles/equip_icon_cyristal.png", "cost_gold": 65, "unlock_with_gems": True, "unlock_at_level": 8, "effect": {"xp_bonus_percent": 3}, "effect_description": "+3% XP", "rarity": "common"},
    {"id": "axe", "name": "Axe", "image": "collectibles/equip_icon_axe_0.png", "cost_gold": 60, "unlock_with_gems": True, "unlock_at_level": 8, "effect": {"xp_bonus_percent": 2, "gold_bonus_percent": 1}, "effect_description": "+2% XP, +1% gold", "rarity": "common"},
    {"id": "leaf", "name": "Leaf", "image": "collectibles/equip_icon_leaf.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 8, "effect": {"luck_gem_chance_percent": 6}, "effect_description": "+6% gem luck", "rarity": "rare"},
    {"id": "shield_wood", "name": "Wood Shield", "image": "collectibles/equip_icon_shield_wood.png", "cost_gold": 70, "unlock_with_gems": True, "unlock_at_level": 8, "effect": {"luck_gem_chance_percent": 2, "gold_flat": 1}, "effect_description": "+2% gem luck, +1g earned", "rarity": "common"},
    # --- Level 10 ---
    {"id": "hammer", "name": "Hammer", "image": "collectibles/equip_icon_hammer_0.png", "cost_gold": 80, "unlock_with_gems": True, "unlock_at_level": 10, "effect": {"gold_flat": 4}, "effect_description": "+4g earned", "rarity": "common"},
    {"id": "potion_red_1", "name": "Red Potion II", "image": "collectibles/equip_icon_potion_red_1.png", "cost_gold": 75, "unlock_with_gems": True, "unlock_at_level": 10, "effect": {"xp_bonus_percent": 3}, "effect_description": "+3% XP", "rarity": "common"},
    # --- Level 12 ---
    {"id": "key_bronze", "name": "Bronze Key", "image": "collectibles/icon_key_bronze.png", "cost_gold": 120, "unlock_with_gems": True, "unlock_at_level": 12, "effect": {}, "effect_description": "Lets you restock the shop: 1 free/day, then 15g+", "rarity": "common"},
    {"id": "island", "name": "Island", "image": "collectibles/Island.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 12, "effect": {"streak_reward_bonus_percent": 30}, "effect_description": "+30% 7-day streak rewards", "rarity": "rare"},
    {"id": "axe_1", "name": "Strong Axe", "image": "collectibles/equip_icon_axe_1.png", "cost_gold": 95, "unlock_with_gems": True, "unlock_at_level": 14, "effect": {"xp_bonus_percent": 2, "gold_bonus_percent": 2}, "effect_description": "+2% XP, +2% gold", "rarity": "common"},
    {"id": "hammer_1", "name": "Strong Hammer", "image": "collectibles/equip_icon_hammer_1.png", "cost_gold": 120, "unlock_with_gems": True, "unlock_at_level": 16, "effect": {"gold_flat": 4, "gold_bonus_percent": 5}, "effect_description": "+4g earned, +5% gold", "rarity": "common"},
    {"id": "potion_blue_1", "name": "Blue Potion II", "image": "collectibles/equip_icon_potion_blue_1.png", "cost_gold": 185, "unlock_with_gems": True, "unlock_at_level": 14, "effect": {"xp_flat": 2}, "effect_description": "+2 XP/review", "rarity": "common"},

    # ============ MID — 18, 22, 25, 26, 30, 35 ============
    {"id": "ring_blue", "name": "Blue Ring", "image": "collectibles/equip_icon_ring_blue.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 18, "effect": {"xp_bonus_percent": 5}, "effect_description": "+5% XP", "rarity": "rare"},
    {"id": "cloverleaf", "name": "Lucky Clover", "image": "collectibles/Cloverleaf.png", "cost_gold": 333, "unlock_with_gems": True, "unlock_at_level": 18, "effect": {"luck_gem_chance_percent": 10}, "effect_description": "+10% gem luck", "rarity": "rare"},
    {"id": "axe_2", "name": "Great Axe", "image": "collectibles/equip_icon_axe_2.png", "cost_gold": 150, "unlock_with_gems": True, "unlock_at_level": 22, "effect": {"xp_bonus_percent": 4, "gold_bonus_percent": 3}, "effect_description": "+4% XP, +3% gold", "rarity": "rare"},
    {"id": "hammer_2", "name": "Great Hammer", "image": "collectibles/equip_icon_hammer_2.png", "cost_gold": 190, "unlock_with_gems": True, "unlock_at_level": 24, "effect": {"gold_bonus_percent": 8}, "effect_description": "+8% gold", "rarity": "rare"},
    {"id": "potion_red_2", "name": "Red Potion III", "image": "collectibles/equip_icon_potion_red_2.png", "cost_gold": 145, "unlock_with_gems": True, "unlock_at_level": 22, "effect": {"xp_bonus_percent": 5}, "effect_description": "+5% XP", "rarity": "rare"},
    {"id": "key_silver", "name": "Silver Key", "image": "collectibles/icon_key_silver.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 22, "effect": {}, "effect_description": "New stock every 2 hours instead of 4", "rarity": "rare"},
    {"id": "gem_red", "name": "Red Gem", "image": "collectibles/equip_icon_gem_red.png", "cost_gold": 200, "unlock_with_gems": True, "unlock_at_level": 25, "effect": {"streak_reward_bonus_percent": 45}, "effect_description": "+45% 7-day streak rewards", "rarity": "rare"},
    {"id": "dragon_tooth", "name": "Dragon Teeth", "image": "collectibles/equip_icon_dragon_teeth.png", "cost_gold": 200, "unlock_with_gems": True, "unlock_at_level": 26, "effect": {"luck_gem_chance_percent": 8}, "effect_description": "+8% gem luck", "rarity": "rare"},
    {"id": "potion_blue_2", "name": "Blue Potion III", "image": "collectibles/equip_icon_potion_blue_2.png", "cost_gold": 350, "unlock_with_gems": True, "unlock_at_level": 26, "effect": {"xp_flat": 3}, "effect_description": "+3 XP/review", "rarity": "rare"},
    {"id": "ring_gold", "name": "Gold Ring", "image": "collectibles/equip_icon_ring_gold.png", "cost_gold": 250, "unlock_with_gems": True, "unlock_at_level": 30, "effect": {"gold_bonus_percent": 10}, "effect_description": "+10% gold", "rarity": "rare"},
    {"id": "coins_chest", "name": "Coin Chest", "image": "currency/Coins - Chest.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 30, "effect": {"gold_flat": 8, "gold_bonus_percent": 5}, "effect_description": "+8g earned, +5% gold", "rarity": "rare"},
    {"id": "axe_3", "name": "Epic Axe", "image": "collectibles/equip_icon_axe_3.png", "cost_gold": 290, "unlock_with_gems": True, "unlock_at_level": 35, "effect": {"xp_bonus_percent": 6, "gold_bonus_percent": 4}, "effect_description": "+6% XP, +4% gold", "rarity": "epic"},
    {"id": "potion_red_3", "name": "Red Potion IV", "image": "collectibles/equip_icon_potion_red_3.png", "cost_gold": 280, "unlock_with_gems": True, "unlock_at_level": 35, "effect": {"xp_bonus_percent": 8}, "effect_description": "+8% XP", "rarity": "epic"},

    # ============ LATE — 40, 45, 50, 55 ============
    {"id": "hammer_3", "name": "Epic Hammer", "image": "collectibles/equip_icon_hammer_3.png", "cost_gold": 300, "unlock_with_gems": True, "unlock_at_level": 40, "effect": {"gold_bonus_percent": 12}, "effect_description": "+12% gold", "rarity": "epic"},
    {"id": "skull", "name": "Skull", "image": "collectibles/Skull (Border).png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 40, "effect": {"gold_bonus_percent": 10, "luck_gem_chance_percent": 10}, "effect_description": "+10% gold, +10% gem luck", "rarity": "rare"},
    {"id": "flag_snow", "name": "Snow Banner", "image": "collectibles/icon_flag_snow.png", "cost_gold": 350, "unlock_with_gems": False, "unlock_at_level": 40, "effect": {"streak_reward_bonus_percent": 60}, "effect_description": "+60% 7-day streak rewards", "rarity": "epic"},
    {"id": "sword", "name": "Sword", "image": "collectibles/Sword (Border).png", "cost_gold": 350, "unlock_with_gems": True, "unlock_at_level": 45, "effect": {"luck_gem_chance_percent": 16}, "effect_description": "+16% gem luck", "rarity": "epic"},
    {"id": "key_gold", "name": "Golden Key", "image": "collectibles/icon_key_gold.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 45, "effect": {}, "effect_description": "2 free restocks per day instead of 1", "rarity": "epic"},
    {"id": "potion_blue_3", "name": "Blue Potion IV", "image": "collectibles/equip_icon_potion_blue_3.png", "cost_gold": 480, "unlock_with_gems": True, "unlock_at_level": 50, "effect": {"xp_flat": 4}, "effect_description": "+4 XP/review", "rarity": "epic"},
    {"id": "cup_border", "name": "Trophy Cup", "image": "collectibles/Cup (Border).png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 50, "effect": {"gold_bonus_percent": 15}, "effect_description": "+15% gold", "rarity": "epic"},
    {"id": "eye_blue", "name": "Void's Eye", "image": "collectibles/equip_icon_eye_blue.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 50, "effect": {"xp_bonus_percent": 6, "gold_bonus_percent": 6, "luck_gem_chance_percent": 10}, "effect_description": "+6% XP, +6% gold, +10% gem luck", "rarity": "epic"},
    {"id": "potion_red_4", "name": "Red Potion V", "image": "collectibles/equip_icon_potion_red_4.png", "cost_gold": 420, "unlock_with_gems": True, "unlock_at_level": 55, "effect": {"xp_bonus_percent": 10}, "effect_description": "+10% XP", "rarity": "epic"},
    {"id": "shield_blue", "name": "Blue Shield", "image": "collectibles/equip_icon_shield_blue.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 55, "effect": {"luck_gem_chance_percent": 40}, "effect_description": "+40% gem luck", "rarity": "epic"},

    # ============ END GAME — 60, 70, 80, 85 (moved UP, never down) ============
    {"id": "palm_tree", "name": "Palm Tree", "image": "collectibles/Palm Tree.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 60, "effect": {"gold_flat": 8}, "effect_description": "+8g earned", "rarity": "rare"},
    {"id": "potion_blue_4", "name": "Blue Potion V", "image": "collectibles/equip_icon_potion_blue_4.png", "cost_gold": 580, "unlock_with_gems": True, "unlock_at_level": 60, "effect": {"xp_flat": 5}, "effect_description": "+5 XP/review", "rarity": "epic"},
    {"id": "crown", "name": "Crown", "image": "collectibles/Crown.png", "cost_gold": 500, "unlock_with_gems": True, "unlock_at_level": 60, "effect": {"xp_bonus_percent": 4, "gold_bonus_percent": 8}, "effect_description": "+4% XP, +8% gold", "rarity": "rare"},
    {"id": "shield", "name": "Shield", "image": "collectibles/Shield.png", "cost_gold": 550, "unlock_with_gems": True, "unlock_at_level": 70, "effect": {"xp_bonus_percent": 8, "gold_bonus_percent": 4}, "effect_description": "+8% XP, +4% gold", "rarity": "rare"},
    {"id": "gemstone", "name": "Gemstone", "image": "collectibles/icon_gemstone.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 70, "effect": {"gold_bonus_percent": 12, "luck_gem_chance_percent": 13}, "effect_description": "+12% gold, +13% gem luck", "rarity": "epic"},
    {"id": "hammer_4", "name": "Legendary Hammer", "image": "collectibles/equip_icon_hammer_4.png", "cost_gold": 580, "unlock_with_gems": True, "unlock_at_level": 80, "effect": {"gold_bonus_percent": 18}, "effect_description": "+18% gold", "rarity": "epic"},
    {"id": "gemstone_rune", "name": "Rune Gemstone", "image": "collectibles/icon_gemstone_rune.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 80, "effect": {"xp_bonus_percent": 10, "gold_bonus_percent": 10}, "effect_description": "+10% XP, +10% gold", "rarity": "epic"},
    {"id": "axe_4", "name": "Legendary Axe", "image": "collectibles/equip_icon_axe_4.png", "cost_gold": 800, "unlock_with_gems": True, "unlock_at_level": 85, "effect": {"xp_bonus_percent": 15, "gold_bonus_percent": 5}, "effect_description": "+15% XP, +5% gold", "rarity": "epic"},
    # ============ VERY LATE GAME — 65+ (many gold-only, no gem craft) ============
    {"id": "meat_feast", "name": "Meat Feast", "image": "collectibles/icon_food_meat.png", "cost_gold": 380, "unlock_with_gems": False, "unlock_at_level": 65, "effect": {"xp_bonus_percent": 3, "gold_flat": 3}, "effect_description": "+3% XP, +3g earned", "rarity": "rare"},
    {"id": "shield_reinf", "name": "Reinforced Shield", "image": "collectibles/icon_equip_shield.png", "cost_gold": 650, "unlock_with_gems": False, "unlock_at_level": 78, "effect": {"gold_bonus_percent": 8, "xp_bonus_percent": 4}, "effect_description": "+8% gold, +4% XP", "rarity": "epic"},
    {"id": "arrow_sharp", "name": "Falcon Bow", "image": "collectibles/icon_equip_arrow.png", "cost_gold": 520, "unlock_with_gems": True, "unlock_at_level": 72, "effect": {"luck_gem_chance_percent": 24}, "effect_description": "+24% gem luck", "rarity": "epic"},
    {"id": "lucky_necklace", "name": "Lucky Necklace", "image": "collectibles/icon_accessories_necklace.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 78, "effect": {"xp_bonus_percent": 2, "gold_bonus_percent": 2}, "effect_description": "+2% XP, +2% gold", "rarity": "epic"},
    {"id": "tome_begin", "name": "Tome of Beginnings", "image": "collectibles/icon_book_0.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 90, "effect": {"prestige_bonus_points": 1}, "effect_description": "+1 prestige point per prestige", "rarity": "legendary"},
    {"id": "candle_focus", "name": "Candle of Focus", "image": "collectibles/icon_candle.png", "cost_gold": 750, "unlock_with_gems": False, "unlock_at_level": 90, "effect": {"luck_gem_chance_percent": 32}, "effect_description": "+32% gem luck", "rarity": "legendary"},
    {"id": "piggy_bank", "name": "Piggy Bank", "image": "collectibles/icon_piggy.png", "cost_gold": 900, "unlock_with_gems": False, "unlock_at_level": 95, "effect": {"gold_flat": 5, "gold_bonus_percent": 10}, "effect_description": "+5g earned, +10% gold", "rarity": "legendary"},
    {"id": "tome_ascent", "name": "Chronicle of Ascension", "image": "collectibles/icon_book_1.png", "cost_gold": 1500, "unlock_with_gems": False, "unlock_at_level": 100, "effect": {"prestige_bonus_points": 1, "xp_bonus_percent": 5}, "effect_description": "+1 prestige point per prestige, +5% XP", "rarity": "legendary"},
    {"id": "lamp_enchanted", "name": "Enchanted Lamp", "image": "collectibles/icon_lamp.png", "cost_gold": 900, "unlock_with_gems": False, "unlock_at_level": 110, "effect": {"gold_bonus_percent": 10, "luck_gem_chance_percent": 16}, "effect_description": "+10% gold, +16% gem luck", "rarity": "legendary"},
    {"id": "hammer_utility", "name": "War Hammer", "image": "collectibles/icon_equip_hammer.png", "cost_gold": 900, "unlock_with_gems": False, "unlock_at_level": 90, "effect": {"gold_bonus_percent": 20, "xp_bonus_percent": 2}, "effect_description": "+20% gold, +2% XP", "rarity": "legendary"},
    {"id": "axe_utility", "name": "Battle Axe", "image": "collectibles/icon_equip_ax.png", "cost_gold": 900, "unlock_with_gems": False, "unlock_at_level": 95, "effect": {"xp_bonus_percent": 17, "gold_bonus_percent": 5}, "effect_description": "+17% XP, +5% gold", "rarity": "legendary"},

    # ============ DUNGEONS — what the shop sells alongside the feature ============ Dungeon stats
    # unlock at 15 or later, when dungeons do. Steel Shoulders is the gem craft beside them.
    {"id": "smoke_pipe", "name": "Smoke Pipe", "image": "collectibles/smoke_pipe.png", "cost_gold": 90, "unlock_with_gems": True, "unlock_at_level": 15, "effect": {"dungeon_discover_percent": 12}, "effect_description": "+12% chance to find a dungeon", "rarity": "common"},
    {"id": "compass", "name": "Compass", "image": "collectibles/compass.png", "cost_gold": 155, "unlock_with_gems": False, "unlock_at_level": 20, "effect": {"dungeon_discover_percent": 20}, "effect_description": "+20% chance to find a dungeon", "rarity": "rare"},
    {"id": "treasure_map", "name": "Treasure Map", "image": "collectibles/icon_scroll_map.png", "cost_gold": 250, "unlock_with_gems": False, "unlock_at_level": 30, "effect": {"dungeon_discover_percent": 30}, "effect_description": "+30% chance to find a dungeon", "rarity": "rare"},
    # Gold-only, so the pace can be bought deliberately rather than left to a craft.
    {"id": "crystal_ball", "name": "Crystal Ball", "image": "collectibles/crystal_ball.png", "cost_gold": 220, "unlock_with_gems": False, "unlock_at_level": 22, "effect": {"dungeon_explore_percent": 7}, "effect_description": "+7% faster dungeon exploration", "rarity": "rare"},
    {"id": "delvers_ring", "name": "Delver's Ring", "image": "collectibles/delvers_ring.png", "cost_gold": 360, "unlock_with_gems": False, "unlock_at_level": 40, "effect": {"dungeon_explore_percent": 10}, "effect_description": "+10% faster dungeon exploration", "rarity": "epic"},
    {"id": "lantern", "name": "Lantern", "image": "collectibles/lantern.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 25, "effect": {"dungeon_explore_percent": 18}, "effect_description": "+18% faster dungeon exploration", "rarity": "rare"},
    {"id": "steel_shoulders", "name": "Steel Shoulders", "image": "collectibles/steel_shoulders.png", "cost_gold": None, "unlock_with_gems": True, "unlock_at_level": 35, "effect": {"xp_bonus_percent": 4, "gold_flat": 3}, "effect_description": "+4% XP, +3g earned", "rarity": "epic"},

    # ============ DUNGEON LOOT — cost_gold None and unlock_with_gems False ============ Found only
    # in dungeon treasure. `weight` is the draw weight, read only by dungeon.py.
    {"id": "bronze_helm", "name": "Bronze Helm", "image": "collectibles/bronze_helm.png", "cost_gold": None, "unlock_with_gems": False, "unlock_at_level": 15, "weight": 6, "effect": {"xp_bonus_percent": 7}, "effect_description": "+7% XP", "rarity": "rare"},
    {"id": "mushroom", "name": "Mushroom", "image": "collectibles/mushroom.png", "cost_gold": None, "unlock_with_gems": False, "unlock_at_level": 15, "weight": 6, "effect": {"xp_bonus_percent": 9}, "effect_description": "+9% XP", "rarity": "rare"},
    {"id": "slingshot", "name": "Slingshot", "image": "collectibles/slingshot.png", "cost_gold": None, "unlock_with_gems": False, "unlock_at_level": 15, "weight": 5, "effect": {"gold_flat": 3, "gold_bonus_percent": 7}, "effect_description": "+3g earned, +7% gold", "rarity": "rare"},
    {"id": "poison", "name": "Poison", "image": "collectibles/poison.png", "cost_gold": None, "unlock_with_gems": False, "unlock_at_level": 15, "weight": 4, "effect": {"dungeon_explore_percent": 11}, "effect_description": "+11% faster dungeon exploration", "rarity": "rare"},
    {"id": "skull_scroll", "name": "Skull Scroll", "image": "collectibles/skull_scroll.png", "cost_gold": None, "unlock_with_gems": False, "unlock_at_level": 15, "weight": 3, "effect": {"dungeon_explore_percent": 15}, "effect_description": "+15% faster dungeon exploration", "rarity": "epic"},
    {"id": "winged_shoes", "name": "Winged Shoes", "image": "collectibles/winged_shoes.png", "cost_gold": None, "unlock_with_gems": False, "unlock_at_level": 15, "weight": 4, "effect": {"dungeon_discover_percent": 38}, "effect_description": "+38% chance to find a dungeon", "rarity": "epic"},
    {"id": "loot_bag", "name": "Loot Bag", "image": "collectibles/loot_bag.png", "cost_gold": None, "unlock_with_gems": False, "unlock_at_level": 15, "weight": 3, "effect": {"gold_bonus_percent": 5, "luck_gem_chance_percent": 8}, "effect_description": "+5% gold, +8% gem luck", "rarity": "epic"},
    {"id": "red_eyed_skull", "name": "Red-eyed Skull", "image": "collectibles/red_eyed_skull.png", "cost_gold": None, "unlock_with_gems": False, "unlock_at_level": 15, "weight": 2, "effect": {"luck_gem_chance_percent": 20}, "effect_description": "+20% gem luck", "rarity": "legendary"},
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


def can_craft(gems: dict[str, int], data: dict[str, Any] | None = None) -> bool:
    """True if the player has at least 1 of every color the craft charges for."""
    return all(gems.get(c, 0) >= 1 for c in craft_required_colors(gems, data))


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


def collectibles_for_gold() -> list[dict[str, Any]]:
    """Collectibles that can be bought with gold (have a gold price). Use collectibles_for_gold_at_level(level) to filter by level."""
    return [c for c in COLLECTIBLES if c.get("cost_gold") is not None]


def collectibles_for_gold_at_level(level: int) -> list[dict[str, Any]]:
    """Collectibles buyable with gold that are unlocked at this level."""
    return [c for c in collectibles_for_gold() if level >= _unlock_at_level(c)]


def gem_only_collectibles() -> list[dict[str, Any]]:
    """Collectibles with no gold price that a gem craft can still produce."""
    return [
        c for c in COLLECTIBLES
        if c.get("cost_gold") is None and c.get("unlock_with_gems", True)
    ]


def loot_collectibles() -> list[dict[str, Any]]:
    """Dungeon loot: no gold price and no gem craft, so the shop can't supply it. Both pool builders
    exclude it already; only the counting helpers need this."""
    return [
        c for c in COLLECTIBLES
        if c.get("cost_gold") is None and not c.get("unlock_with_gems", True)
    ]


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
    """Whether the craft is narrowed to gem-only items right now (false again once they're all
    owned)."""
    from . import milestones

    if not milestones.has_targeted_craft(data):
        return False
    owned = set(data.get("owned_collectibles", []))
    return any(c.get("cost_gold") is None for c in craft_pool(level, owned, data))


def _build_daily_slot_pool(level: int, owned: set[str] | None = None) -> list[dict[str, Any]]:
    """Pool for shop slots: collectibles (gold at level, not owned) plus one entry per gem kind, so
    a restock can offer several gems."""
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


def spend_gems_get_random(
    data: dict[str, Any], level: int, col: Any = None
) -> tuple[str | None, dict[str, Any] | None]:
    """Spend one gem of each color for a random collectible from the craft pool, weighted toward the
    player's level. Returns (cid, collectible), or (None, None). Mutates data."""
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
    # With the collection: a milestone completing here can raise the accumulator's cap, and that
    # restarts its ramp, which needs to know what day it is.
    milestones.advance_if_complete(data, col)
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
    left (1/day, 2 with the Golden Key), else pays refresh_cost. Returns True if refreshed."""
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
            # The player's own gems, so a most-needed slot targets the color actually short.
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
    """Total flat gold bonus from owned collectibles (added to level-up and streak gold, half to
    quest gold)."""
    return int(_sum_effect(owned_ids, "gold_flat"))


def xp_flat(owned_ids: list[str]) -> int:
    """Total flat XP bonus from owned collectibles (added to review XP, except Again/Hard-in-hard-mode)."""
    return int(_sum_effect(owned_ids, "xp_flat"))


def streak_reward_bonus_percent(owned_ids: list[str]) -> float:
    """Total 7-day streak reward bonus % from owned collectibles (see streak.grant_streak_reward)."""
    return _sum_effect(owned_ids, "streak_reward_bonus_percent")


def luck_gem_chance_percent(owned_ids: list[str]) -> float:
    """Total luck chance (e.g. 5 = 5% chance +1 extra gem on quest/level-up)."""
    return _sum_effect(owned_ids, "luck_gem_chance_percent")


def dungeon_discover_percent(owned_ids: list[str]) -> float:
    """Total bonus to the dungeon entrance chance, as a percent (e.g. 15 for +15%)."""
    return _sum_effect(owned_ids, "dungeon_discover_percent")


def dungeon_explore_percent(owned_ids: list[str]) -> float:
    """Total bonus to the branching-pathway chance: "faster dungeon exploration"."""
    return _sum_effect(owned_ids, "dungeon_explore_percent")


def prestige_bonus_points(owned_ids: list[str]) -> int:
    """Extra prestige points granted per prestige by owned collectibles (the two tomes)."""
    return int(_sum_effect(owned_ids, "prestige_bonus_points"))


def shop_supplied_collectibles() -> list[dict[str, Any]]:
    """Everything the shop or a craft can eventually hand over: the collection minus dungeon loot."""
    loot = {c["id"] for c in loot_collectibles()}
    return [c for c in COLLECTIBLES if c["id"] not in loot]


def all_collectibles_owned(data: dict[str, Any]) -> bool:
    """True once the player owns everything the shop and crafting can supply. Dungeon loot is
    excluded, since no save realistically collects all of it."""
    owned = set(data.get("owned_collectibles", []))
    all_ids = {c["id"] for c in shop_supplied_collectibles()}
    return all_ids.issubset(owned)


# A Magnet on sale. Flat, like what it buys: later stages ask for more Magnets, not dearer ones.
MAGNET_COST_GOLD = 50

# Endgame trade rates (when all collectibles owned)
TRADE_GOLD_TO_XP_RATE = 3   # 1 gold -> 3 XP
# A gem is worth what the cheapest gem slot charges for one, so the slots a completed collection
# hides cost the player nothing.
TRADE_GEM_TO_XP_RATE = GEM_COST_RANDOM * TRADE_GOLD_TO_XP_RATE  # 1 gem -> 90 XP


def _pay_level_up(data: dict[str, Any]) -> None:
    """Update the stored level for XP a trade just paid, and grant its level-ups. Imported inside,
    since review_rewards imports this module."""
    from . import review_rewards

    review_rewards.grant_level_up(
        data, data.get("level", 1), data.get("owned_collectibles", [])
    )


def trade_gold_for_xp(data: dict[str, Any]) -> int:
    """Convert all gold to XP at 1g = 3 XP; only once all collectibles are owned. Returns XP added.
    Levels crossed pay normally, so gold may come back."""
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
    """Convert all gems to XP at TRADE_GEM_TO_XP_RATE; only once all collectibles are owned. Returns
    XP added. Levels crossed pay normally, returning some gold and gems."""
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
