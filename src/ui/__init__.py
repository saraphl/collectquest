"""CollectQuest UI package. Re-exports the names the rest of the add-on uses as `ui.<name>`."""
from __future__ import annotations

from .dungeon import (
    show_catch_up_prompt,
    show_dungeon_dialog,
)
from .docks import (
    close_panels,
    refresh_progress_panel,
    restore_saved_panels,
    show_progress_dialog,
    toggle_progress_panel,
    toggle_shop_panel,
)
from .notifications import (
    maybe_show_onboarding,
    maybe_show_update_popup,
    level_up_message,
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
from .items import (
    show_items_dialog,
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
    mount_status_bar,
)

__all__ = [
    "close_panels",
    "show_catch_up_prompt",
    "show_dungeon_dialog",
    "maybe_show_game_finished_prompt",
    "maybe_show_onboarding",
    "maybe_show_prestige_prompt",
    "maybe_show_update_popup",
    "mount_status_bar",
    "refresh_progress_panel",
    "restore_saved_panels",
    "show_options_dialog",
    "show_progress_dialog",
    "level_up_message",
    "show_review_summary_tooltip",
    "show_items_dialog",
    "show_milestones_dialog",
    "stacked_tooltip",
    "show_shop_dialog",
    "show_streak_reward_notification",
    "show_sync_summary_panel",
    "toggle_progress_panel",
    "toggle_shop_panel",
]
