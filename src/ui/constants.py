"""Shared sizing, color and asset constants for the CollectQuest UI."""
from __future__ import annotations


_STREAK_FILLED_COLOR = "#2563eb"

_STREAK_EMPTY_COLOR = "#5c5c5c"

_STREAK_GAP = 8  # space between the streak squares and the centered group

_QUEST_BONUS_SEPARATOR_WIDTH = 180

_QUEST_BONUS_SEPARATOR_TOP_PAD = 2

_COLLECTQUEST_PANEL_WIDTH = 280

_COLLECTQUEST_PANEL_MIN_WIDTH = 200  # minimum dock width; content uses setMinimumWidth(1) so dock can shrink to this

_POPUP_PROGRESS_DIALOG_WIDTH = 260

_POPUP_SHOP_DIALOG_WIDTH = 280
# Width the shop dialog opens at. Set explicitly because it would otherwise follow sizeHint,
# which is driven by the longest item effect line — lengthening one item's text then widens
# the whole dialog. Between the min above and _POPUP_MAX_WIDTH, so it stays resizable.
_POPUP_SHOP_DIALOG_OPEN_WIDTH = 320

_POPUP_MAX_WIDTH = 420

# Floor for a dialog's bottom button row. "Options" and "Close" hint at ~80px, which looks thin in
# the CollectQuest window; this matches the width the shop's own row lands on.
_DIALOG_BUTTON_MIN_WIDTH = 110

# Opening width for the prestige window. Wider than its content strictly needs, so the gray
# effect text on each upgrade row keeps clear of the title beside it.
_PRESTIGE_DIALOG_WIDTH = 520

# Chrome for the windows a panel section's [▸] opens - the milestones track and the items
# collection. Shared so the two cannot drift into different grays or header sizes.
_DETAIL_HEADER_ICON_PX = 96
_DETAIL_TITLE_STYLE = "font-weight: bold; font-size: 16px;"
_DETAIL_MUTED = "color: #888;"
_DETAIL_BUTTON_ROW_GAP = 8

_SHOP_PANEL_WIDTH = 220

_COLLECTQUEST_PANEL_EXPAND_WIDTH = (_COLLECTQUEST_PANEL_WIDTH * 2) // 3  # 2/3 expansion, 1/3 from center

_FLOAT_HEIGHT_SAVE_OFFSET = 30

_STATUSBAR_STREAK_AREA_WIDTH = 120

_STATUSBAR_BLOCK_PREFERRED = 380

_STATUSBAR_BLOCK_MIN = 260  # fallback when sizeHint not available

_TOOLTIP_PERIOD_MS = 5000

# Secondary figures inside a rich-text label - the items count, the quest rewards. Smaller and
# gray, so a row's objective stays the part that is read first.
_MUTED_STAT_STYLE = "color: #888; font-size: 10px;"

_STREAK_GIFT_IMAGES = {
    "xp": "rewards/Gift - Blue (Border).png",
    "gem": "rewards/Gift - Pink (Border).png",
    "gold": "rewards/Gift - Yellow (Border).png",
}

_CHANGELOG_URL = "https://github.com/saraphl/collectquest/blob/main/CHANGELOG.md"

_UPDATE_POPUP_TEXT_SPACING = 2  # title -> body block; also the layout's base spacing

_UPDATE_POPUP_ICON_GAP = 5  # icon -> title

_UPDATE_POPUP_BUTTON_GAP = 12  # body -> OK button
