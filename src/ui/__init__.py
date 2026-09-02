"""
CollectQuest UI package.

ui.py grew past 3000 lines and was split by concern; this module re-exports the names the rest
of the add-on reaches for, so callers keep using `ui.<name>` exactly as before.
"""
from __future__ import annotations

from .constants import (
    _COLLECTQUEST_PANEL_MIN_WIDTH,
    _FLOAT_HEIGHT_SAVE_OFFSET,
)
from .docks import (
    _collectquest_dock_area,
    _shop_dock_area,
    get_collectquest_statusbar_center_content_width,
    get_collectquest_statusbar_right_panel_block_width,
    refresh_progress_panel,
    show_progress_dialog,
    toggle_progress_panel,
    toggle_shop_panel,
)
from .notifications import (
    maybe_show_onboarding,
    maybe_show_update_popup,
    show_review_summary_tooltip,
    show_streak_reward_notification,
    show_sync_summary_panel,
)
from .options import (
    show_options_dialog,
)
from .prestige import (
    maybe_show_game_finished_prompt,
    maybe_show_prestige_prompt,
)
from .milestones import (
    show_milestones_dialog,
)
from .stacked_tooltip import (
    stacked_tooltip,
)
from .shop import (
    show_shop_dialog,
)
from .statusbar import (
    build_bottom_ui_block,
    build_simple_centered_xp_bar_widget,
    build_streak_widget,
    update_simple_bar_centering,
)

__all__ = [
    "_COLLECTQUEST_PANEL_MIN_WIDTH",
    "_FLOAT_HEIGHT_SAVE_OFFSET",
    "_collectquest_dock_area",
    "_shop_dock_area",
    "build_bottom_ui_block",
    "build_simple_centered_xp_bar_widget",
    "build_streak_widget",
    "get_collectquest_statusbar_center_content_width",
    "get_collectquest_statusbar_right_panel_block_width",
    "maybe_show_game_finished_prompt",
    "maybe_show_onboarding",
    "maybe_show_prestige_prompt",
    "maybe_show_update_popup",
    "refresh_progress_panel",
    "show_options_dialog",
    "show_progress_dialog",
    "show_review_summary_tooltip",
    "show_milestones_dialog",
    "stacked_tooltip",
    "show_shop_dialog",
    "show_streak_reward_notification",
    "show_sync_summary_panel",
    "toggle_progress_panel",
    "toggle_shop_panel",
    "update_simple_bar_centering",
]
