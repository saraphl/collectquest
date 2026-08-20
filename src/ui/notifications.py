"""Transient UI: review tooltip, streak reward, onboarding and update popups."""
from __future__ import annotations

from typing import Callable
from aqt.qt import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    Qt,
)
from aqt.utils import tooltip
from .. import storage, xp
from .stacked_tooltip import stacked_tooltip
from .options import show_options_dialog
from .assets import _pixmap, _pixmap_ui, _review_dialog_icon
from .constants import _CHANGELOG_URL, _STREAK_GIFT_IMAGES, _TOOLTIP_PERIOD_MS, _UPDATE_POPUP_BUTTON_GAP, _UPDATE_POPUP_ICON_GAP, _UPDATE_POPUP_TEXT_SPACING

def show_review_summary_tooltip(
    completed_quests: list[tuple[str, int]],
    gold_earned: int,
    gem_earned: int,
    leveled_up: bool = False,
) -> None:
    """
    One tooltip for everything a single answer earned:

        Quest complete: Review 82 cards (+61 XP, +12g)
        Quests complete: Review 82 cards, Get 45 correct (+118 XP, +25g, +1 gem)
        Level up (+24g, +2 gems)

    Anki's tooltip is a singleton — every call closes the previous one — so firing "quest complete"
    and "+gold" as two calls meant the second silently ate the first and the quest message was never
    readable. Composing one line is the only way both survive.
    """
    rewards: list[str] = []
    quest_xp = sum(x for _, x in completed_quests) if completed_quests else 0
    if quest_xp > 0:
        rewards.append(f"+{quest_xp} XP")
    if gold_earned > 0:
        rewards.append(f"+{gold_earned}g")
    if gem_earned > 0:
        rewards.append(f"+{gem_earned} gem" + ("s" if gem_earned > 1 else ""))

    if completed_quests:
        labels = ", ".join(label for label, _ in completed_quests)
        head = ("Quest complete: " if len(completed_quests) == 1 else "Quests complete: ") + labels
    elif leveled_up:
        head = "Level up"
    else:
        # Rewards with no quest and no level-up shouldn't happen, but report the amounts plainly
        # rather than captioning them with a cause that didn't occur.
        head = ""

    if head:
        tooltip(head + (f" ({', '.join(rewards)})" if rewards else ""), period=_TOOLTIP_PERIOD_MS)
    elif rewards:
        tooltip(", ".join(rewards), period=_TOOLTIP_PERIOD_MS)

def _streak_reward_message(reward: dict) -> str:
    """Build reward text for toast or dialog."""
    kind = reward.get("type", "xp")
    amount = reward.get("amount", 0)
    if kind == "xp":
        return f"+{amount} XP"
    if kind == "gem":
        msg = f"+{amount} gem" + ("s" if amount != 1 else "")
        if reward.get("gold"):
            msg += f"  and  +{reward['gold']}g"
        return msg
    msg = f"+{amount}g"
    if reward.get("xp"):
        msg += f"  and  +{reward['xp']} XP"
    return msg

def show_streak_reward_dialog(parent: QWidget | None, reward: dict) -> None:
    """Show a modal dialog for 7-day streak reward with title, correct gift icon, current streak, and reward icons."""
    kind = reward.get("type", "xp")
    gift_img = _STREAK_GIFT_IMAGES.get(kind, _STREAK_GIFT_IMAGES["xp"])
    msg = _streak_reward_message(reward)

    d = QDialog(parent)
    d.setWindowTitle("Streak reward!")
    layout = QVBoxLayout(d)
    layout.setSpacing(12)

    # Title (always visible)
    title_lbl = QLabel("Streak reward!")
    title_lbl.setStyleSheet("font-weight: bold; font-size: 16px;")
    layout.addWidget(title_lbl, 0, Qt.AlignmentFlag.AlignCenter)

    # Current total streak
    current_streak_days = 0
    try:
        from aqt import mw as _mw
        if getattr(_mw, "col", None):
            from .. import streak as _streak_mod
            data = storage.load()
            today_ep = _streak_mod.today_epoch(_mw.col)
            current_streak_days, _ = _streak_mod.get_display_streak_days(data, today_ep)
    except Exception:
        pass
    if current_streak_days > 0:
        streak_txt = f"Current total streak: {current_streak_days} day{'s' if current_streak_days != 1 else ''}"
        streak_lbl = QLabel(streak_txt)
        streak_lbl.setStyleSheet("color: #555; font-size: 12px;")
        layout.addWidget(streak_lbl, 0, Qt.AlignmentFlag.AlignCenter)

    # Reward row: gift icon + small gem/coin icon (before message) + message
    row = QHBoxLayout()
    row.setSpacing(10)
    gift_pm = _pixmap(gift_img, 56)
    if not gift_pm or gift_pm.isNull():
        gift_pm = _pixmap("ui/icon_message.png", 56)
    if gift_pm and not gift_pm.isNull():
        icon_lbl = QLabel()
        icon_lbl.setPixmap(gift_pm)
        row.addWidget(icon_lbl)
    # Small icon for gem or gold before the amount (fallback to ui icon if asset missing)
    if kind == "gem":
        small_pm = _pixmap("gems/Gem - Pink.png", 24) or _pixmap("ui/icon_message.png", 24)
        if small_pm and not small_pm.isNull():
            gem_lbl = QLabel()
            gem_lbl.setPixmap(small_pm)
            row.addWidget(gem_lbl)
    elif kind == "gold":
        small_pm = _pixmap("currency/Coin x1.png", 24) or _pixmap("ui/icon_message.png", 24)
        if small_pm and not small_pm.isNull():
            coin_lbl = QLabel()
            coin_lbl.setPixmap(small_pm)
            row.addWidget(coin_lbl)
    msg_lbl = QLabel(msg)
    msg_lbl.setStyleSheet("font-size: 13px;")
    row.addWidget(msg_lbl)
    row.addStretch()
    layout.addLayout(row)

    ok_btn = QPushButton("OK")
    ok_btn.setDefault(True)
    ok_btn.setFocus(Qt.FocusReason.PopupFocusReason)
    ok_btn.clicked.connect(d.accept)
    layout.addWidget(ok_btn, 0, Qt.AlignmentFlag.AlignCenter)
    d.exec()

def _estimate_reviews_per_day_last_30(col) -> float:
    """Rough average reviews/day over the last 30 days, from revlog."""
    try:
        days = 30
        rows = col.db.scalar(
            "SELECT COUNT() FROM revlog WHERE id/1000 >= strftime('%s','now') - ?",
            days * 86400,
        )
        count = rows or 0
        return float(count) / float(days)
    except Exception:
        return 0.0

def _recommend_difficulty(avg_reviews_per_day: float) -> str:
    """Map average reviews/day to difficulty id. Heavy user = 200+ reviews/day."""
    if avg_reviews_per_day < 60:
        return "easy"
    if avg_reviews_per_day >= 200:
        return "hard"
    return "normal"

def _show_onboarding_dialog(
    parent: QWidget | None,
    avg_per_day: float,
    diff_id: str,
    on_refresh: Callable[[], None] | None,
) -> None:
    """Welcome popup explaining basics and chosen difficulty."""
    d = QDialog(parent)
    d.setWindowTitle("CollectQuest — Welcome")
    layout = QVBoxLayout(d)
    layout.setSpacing(10)

    icon = _review_dialog_icon()
    if icon:
        layout.addWidget(icon)

    title = QLabel("Welcome to CollectQuest!")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title.setStyleSheet("font-size: 16px; font-weight: bold;")
    layout.addWidget(title)

    intro = QLabel(
        "CollectQuest adds a light progression layer on top of your reviews:\n"
        "- Earn XP and gold from your daily studying and quests.\n"
        "- Buy collectibles in the shop and upgrade your house over time."
    )
    intro.setWordWrap(True)
    intro.setStyleSheet("font-size: 12px;")
    layout.addWidget(intro)

    avg_txt = f"~{avg_per_day:.0f}" if avg_per_day > 0 else "unknown"
    diff_label = {
        "easy": "Casual",
        "normal": "Steady",
        "hard": "Heavy User",
    }.get(diff_id, "Steady")

    diff_msg = QLabel(
        f"Based on your last 30 days (~{avg_txt} reviews/day),\n"
        f"we started you in **{diff_label}** difficulty.\n\n"
        "You can always change this later in the Options."
    )
    diff_msg.setWordWrap(True)
    diff_msg.setStyleSheet("font-size: 12px;")
    layout.addWidget(diff_msg)

    btn_row = QHBoxLayout()
    btn_row.addStretch()

    def _open_options() -> None:
        d.accept()
        show_options_dialog(parent, on_refresh or (lambda: None))

    options_btn = QPushButton("Open Options")
    options_btn.clicked.connect(_open_options)
    ok_btn = QPushButton("OK")
    ok_btn.clicked.connect(d.accept)
    btn_row.addWidget(options_btn)
    btn_row.addWidget(ok_btn)
    layout.addLayout(btn_row)

    # Highlight the OK button by default (not Open Options)
    ok_btn.setDefault(True)
    ok_btn.setAutoDefault(True)
    ok_btn.setFocus()

    d.setMinimumWidth(380)
    d.exec()

def show_update_popup(
    parent: QWidget | None = None,
    version: str | None = None,
) -> None:
    """Show the 'Updated to X' dialog. version defaults to current add-on version. Does nothing when no version can be resolved."""
    ver = (version or storage.get_version() or "").strip()
    if not ver:
        return
    d = QDialog(parent)
    d.setWindowTitle("CollectQuest — Update")
    layout = QVBoxLayout(d)
    # Tight enough that the three text rows read as one block rather than as separate paragraphs.
    # The icon and the OK button get their own spacing below, so only the text is affected.
    layout.setSpacing(_UPDATE_POPUP_TEXT_SPACING)
    scroll_pm = _pixmap_ui("icon_scroll_letter_1.png", height=56)
    if scroll_pm and not scroll_pm.isNull():
        scroll_lbl = QLabel()
        scroll_lbl.setPixmap(scroll_pm)
        scroll_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(scroll_lbl)
        layout.addSpacing(_UPDATE_POPUP_ICON_GAP - _UPDATE_POPUP_TEXT_SPACING)
    title = QLabel(f"Updated to {ver} !")
    title.setStyleSheet("font-weight: bold; font-size: 14px;")
    layout.addWidget(title)
    # One label with an explicit <br> rather than two labels. Two labels each carried their own
    # padding and an inter-widget gap, and setWordWrap made matters worse: its sizeHint is computed
    # against a narrow width where this text wraps to three lines, which inflated the dialog and
    # left the surplus redistributed across every row. Breaking the line ourselves means no wrapping
    # guess, and the two rows sit at the font's natural line height.
    body_lbl = QLabel(
        "Thank you for playing CollectQuest!<br>"
        f'Refer to the <a href="{_CHANGELOG_URL}">changelog</a> for more information.'
    )
    body_lbl.setTextFormat(Qt.TextFormat.RichText)
    body_lbl.setOpenExternalLinks(True)  # hand the URL to the system browser
    # No font-size here: a hardcoded pixel size happens to match the default at 9pt, but stops
    # matching as soon as the UI font is larger, leaving this line visibly smaller than the rest.
    layout.addWidget(body_lbl)
    layout.addSpacing(_UPDATE_POPUP_BUTTON_GAP - _UPDATE_POPUP_TEXT_SPACING)
    ok_btn = QPushButton("OK")
    ok_btn.clicked.connect(d.accept)
    layout.addWidget(ok_btn)
    ok_btn.setFocus()
    d.setMinimumWidth(340)
    d.exec()

def maybe_show_update_popup(
    parent: QWidget | None,
    force: bool = False,
) -> None:
    """Show update popup once per version: if shown_update_popup_for != current, show it. The flag is set *after* the user closes the popup (so we don't mark as shown while it's open). force=True (admin) just shows the dialog."""
    data = storage.load()
    current = (storage.get_version() or "").strip()
    if not current:
        # manifest.json carries no version, so there is no update to announce. Substituting a
        # placeholder would show a number that was never released, and would then be written to
        # shown_update_popup_for — pinning the flag to a version that can never change again.
        if force:
            tooltip("No version in manifest.json, so there is nothing to announce.")
        return
    shown_for = (data.get("shown_update_popup_for") or "0").strip()
    if not force and shown_for == current:
        return
    show_update_popup(parent, version=current)
    # Set flag only after popup was closed (user clicked OK)
    if not force:
        data = storage.load()
        data["shown_update_popup_for"] = current
        storage.save(data)

def maybe_show_onboarding(
    parent: QWidget | None,
    on_refresh: Callable[[], None] | None = None,
    force: bool = False,
) -> None:
    """Show onboarding popup once, and auto-set difficulty from last 30 days. force=True (admin) skips guards and shows dialog."""
    from aqt import mw as _mw

    data = storage.load()
    if not force:
        if data.get("onboarding_shown") or (data.get("total_xp", 0) or 0) > 0:
            return
    col = getattr(_mw, "col", None)
    avg = _estimate_reviews_per_day_last_30(col) if col else 0.0
    diff_id = _recommend_difficulty(avg) if col else "normal"
    if not force:
        data["difficulty"] = diff_id
        data["onboarding_shown"] = True
        storage.save(data)
    xp.set_difficulty(diff_id)
    _show_onboarding_dialog(parent, avg, diff_id, on_refresh)

def show_sync_summary_panel(parent: QWidget | None, summary: dict) -> None:
    """
    Report what a sync credited (CollectQuest: synced N reviews, +X XP, …).

    Uses the stacking notification rather than Anki's tooltip: a sync also produces Anki's own
    "Collection complete.", and other add-ons report on the same hook, so the shared singleton means
    whoever speaks last is the only one heard. This one sits above whatever is already showing.

    parent must be the main window. The notification is placed at the bottom-left of whichever
    window it is given, and right after a sync the active window can still be the small, screen-
    centered progress dialog, which would put the message in the middle of the screen.
    """
    reviews = summary.get("reviews", 0)
    if reviews <= 0:
        return
    xp_val = summary.get("xp", 0)
    gold_val = summary.get("gold", 0)
    gems_val = summary.get("gems", 0)
    parts = [f"CollectQuest: Synced {reviews} review" + ("s" if reviews != 1 else "")]
    if xp_val > 0:
        parts.append(f"+{xp_val} XP")
    if gold_val > 0:
        parts.append(f"+{gold_val}g")
    if gems_val > 0:
        parts.append(f"+{gems_val} gem" + ("s" if gems_val != 1 else ""))
    stacked_tooltip(", ".join(parts), period=_TOOLTIP_PERIOD_MS, parent=parent)
