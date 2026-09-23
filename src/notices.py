"""The notification queue: what one answer, refresh or sync announces, and in what order and spacing."""
from __future__ import annotations

from aqt import mw
from aqt.qt import QTimer
from . import dungeon, milestones, ui, xp

# Milestones finished but not yet shown. The bar refresh drains the save's queue into this and
# announces straight away, except during an answer - the summary tooltip has to land first.
milestone_queue: list[dict] = []
# Free-text lines (sync dungeon finds) joining the next box, so one moment's output is one box.
pending_lines: list[str] = []
# Feature unlocks, one box each: two opening on the same answer in one box read as a single event.
pending_unlocks: list[str] = []
# A granted streak reward waiting for its slot, announced alongside the queue above.
pending_streak_reward: dict | None = None
# True between profile_will_close and the next profile_did_open. Anki syncs during teardown, where a
# deferred message would target a collection about to close and be dropped unseen.
profile_closing = False
_scheduled = False

# Between any two notifications one answer produces, so they don't read as one wall of text or
# measure the screen before the previous one lands.
STAGGER_MS = 500
# A buff drop waits this long behind the bonus quest's notification, so it reads as its own grant.
BUFF_DELAY_MS = 2000
# Before announcing a refresh's queue, so Anki's "Collection sync complete." is already on screen.
TRACK_DELAY_MS = 2000

# Each feature unlock is announced once; the flags' reset rules live in storage.
_UNLOCKS = (
    ("milestones_unlock_notice_shown", "Milestones unlocked!\nSee the CollectQuest window."),
    ("dungeon_unlock_notice_shown", "Dungeons unlocked!\nSee the CollectQuest window."),
)


def clear() -> None:
    """Drop everything queued, so nothing from a closing profile fires against the next one."""
    global pending_streak_reward, _scheduled
    milestone_queue.clear()
    pending_lines.clear()
    pending_unlocks.clear()
    pending_streak_reward = None
    _scheduled = False


def schedule() -> None:
    """Announce anything queued shortly, once the noisier startup messages have landed."""
    global _scheduled
    if _scheduled or not (
        milestone_queue or pending_streak_reward or pending_lines or pending_unlocks
    ):
        return
    _scheduled = True

    def _fire() -> None:
        global _scheduled
        _scheduled = False
        # An answer may have drained the queue meanwhile, making this a no-op rather than an empty box.
        show_queued()

    QTimer.singleShot(TRACK_DELAY_MS, _fire)


def queue_unlocks(data: dict) -> None:
    """Queue a line for any feature that has just become available. Mutates data; caller saves.
    Checked on refresh, not at level-up, so saves from older builds still get their notice."""
    level = xp.level_from_total_xp(int(data.get("total_xp", 0) or 0))
    available = {
        "milestones_unlock_notice_shown": milestones.is_unlocked(data),
        "dungeon_unlock_notice_shown": level >= dungeon.UNLOCK_LEVEL,
    }
    for key, line in _UNLOCKS:
        if available[key] and not data.get(key):
            data[key] = True
            pending_unlocks.append(line)


def _post_streak_reward(reward: dict) -> None:
    """Caught on its own: a failure here must not take the box queued behind it down too."""
    try:
        ui.show_streak_reward_notification(mw, reward)
    except Exception as e:
        print(f"CollectQuest: streak reward notification failed: {e!r}")


def _post_one(message: str) -> None:
    """Show one queued box, unless the profile closed while it waited."""
    if profile_closing or mw is None:
        return
    ui.stacked_tooltip(message, parent=mw)


def post(messages: list[str], start_delay: int = 0) -> int:
    """Show each message in its own stacked box, STAGGER_MS apart. Returns the next free delay, so
    every caller queues behind whatever already spoke."""
    delay = start_delay
    for message in messages:
        QTimer.singleShot(delay, lambda m=message: _post_one(m))
        delay += STAGGER_MS
    return delay


def _post_unlocks(start_delay: int = 0) -> int:
    """Drained as it schedules, so a refresh inside the stagger cannot post one twice."""
    pending, pending_unlocks[:] = list(pending_unlocks), []
    return post(pending, start_delay)


def dungeon_lines(earned: dict) -> list[str]:
    """What a dungeon found on one answer, as notification lines. Shared by the answer and post-sync
    paths; auto-pick names what it took, since the player otherwise has no reason to look."""
    lines: list[str] = []
    xp_suffix = f" (+{earned['dungeon_xp']} XP)" if earned.get("dungeon_xp") else ""
    if earned.get("dungeon_entrance"):
        lines.append("Dungeon entrance discovered!")
    if earned.get("dungeon_branching"):
        took = earned.get("dungeon_auto_took")
        if took:
            # The button's own words, so an auto-taken Unique path reads "Unknown item".
            lines.append(
                f"Dungeon: branching pathways discovered — took {dungeon.offer_summary(took)}."
            )
        else:
            lines.append("Dungeon: branching pathways discovered!")
    if earned.get("dungeon_treasure"):
        lines.append("Dungeon: treasure room discovered!")
    if lines and xp_suffix:
        lines[-1] += xp_suffix
    return lines


def show_queued(earned: dict | None = None, start_delay: int = 0) -> None:
    """Announce what the milestone track did: one stacked box, plus a separate one for a buff drop.
    Never raises (it runs from the answer hook) but prints, so wiring mistakes aren't silent."""
    global pending_streak_reward
    try:
        # Queued first so the milestone box stacks above it.
        delay = start_delay
        if pending_streak_reward is not None:
            reward, pending_streak_reward = pending_streak_reward, None
            QTimer.singleShot(delay, lambda r=reward: _post_streak_reward(r))
            delay += STAGGER_MS
        lines: list[str] = []
        lines.extend(pending_lines)
        pending_lines.clear()
        while milestone_queue:
            entry = milestone_queue.pop(0)
            lines.append(f"Milestone complete: {milestones.objective_label(entry)}")
            lines.append(f"Reward: {entry.get('reward', '')}")

        if earned:
            lines.extend(dungeon_lines(earned))
            if earned.get("magnet_found"):
                lines.append("Magnet found!")
            stage = earned.get("magnet_stage_completed")
            if stage:
                lines.append(milestones.stage_completed_message(stage))
        delay = post(["\n".join(lines)] if lines else [], delay)
        # A buff gets its own box, measured from now; max() keeps it last behind a longer queue.
        buff = earned.get("buff_started") if earned else None
        if buff:
            delay = post(
                [f"Buff for {milestones.BUFF_DAYS} days: {buff['label']}"],
                max(delay, BUFF_DELAY_MS),
            )
        _post_unlocks(delay)
    except Exception as e:
        print(f"CollectQuest: milestone notification failed: {e!r}")
