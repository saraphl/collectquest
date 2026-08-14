"""Level-based unlocks: map level -> image and name. Uses images from add-on images/ folder."""
from __future__ import annotations

# Order of unlocks by level. (level, image_path_under_images/, display_name)
UNLOCKS_BY_LEVEL: list[tuple[int, str, str]] = [
    (1, "gems/Gem - Blue.png", "Blue Gem"),
    (2, "gems/Gem - Green.png", "Green Gem"),
    (3, "currency/Coin x1.png", "Coin"),
    (4, "collectibles/Cup.png", "Cup"),
    (5, "collectibles/Crown.png", "Crown"),
    (6, "rewards/Gift - Blue (Border).png", "Blue Gift"),
    (7, "gems/Gem - Pink.png", "Pink Gem"),
    (8, "currency/Coins - Chest.png", "Coin Chest"),
    (9, "collectibles/Shield.png", "Shield"),
    (10, "collectibles/Sword (Border).png", "Sword"),
    (11, "gems/Gem - Purple.png", "Purple Gem"),
    (12, "gems/Gem - Yellow.png", "Yellow Gem"),
    (13, "rewards/Gift - Pink (Border).png", "Pink Gift"),
    (14, "rewards/Gift - Yellow (Border).png", "Yellow Gift"),
    (15, "collectibles/Skull (Border).png", "Skull"),
    (16, "collectibles/Bag.png", "Bag"),
    (17, "collectibles/Package.png", "Package"),
    (18, "collectibles/Cup (Border).png", "Cup (Border)"),
    (19, "ui/Calendar.png", "Calendar"),
    (20, "ui/Clock - Indigo.png", "Clock"),
]


def newly_unlocked(level: int, already_unlocked: list[str]) -> list[tuple[str, str]]:
    """Returns list of (image_filename, display_name) for unlocks newly reached at this level."""
    result = []
    for req_lev, img, name in UNLOCKS_BY_LEVEL:
        if req_lev <= level and img not in already_unlocked:
            result.append((img, name))
    return result


def all_unlocks_for_level(level: int) -> list[tuple[int, str, str]]:
    """All unlock entries up to and including level."""
    return [(lev, img, name) for lev, img, name in UNLOCKS_BY_LEVEL if lev <= level]
