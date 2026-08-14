# CollectQuest (fork)

A personal fork of [CollectQuest](https://ankiweb.net/shared/info/627746544) by Florent Baris — an RPG-style progression layer for Anki (XP, levels, daily quests, gold, gems, collectibles, streaks, prestige).

All credit for the original add-on goes to the upstream author. This fork exists only to carry a few local changes.

## Changes in this fork

### Daily resets follow the scheduler's day, not civil midnight

Daily quests previously reset at midnight local time, ignoring Anki's **Preferences → Scheduler → Next day starts at** setting. With the default 4 a.m. rollover, a review at 00:30 belonged to *yesterday* as far as Anki was concerned, but already started a *new* day of daily quests.

The day boundary is now taken from that setting, which is what the streak code already did. The same boundary applies to the shop's daily unlock and free refresh, and to which synced phone reviews count as today's — without that last one, reviews done between midnight and rollover were dropped rather than credited.

### Reward bonuses that silently did nothing

Several items promised bonuses the game never applied — a better chance of gems from daily quests, and bigger 7-day streak payouts — as did the prestige *Quest reward* upgrade, which cost points and did nothing. They now work.

Separately, the count of claimed 7-day rewards carried over when a streak broke, so after three payouts a fresh streak needed 28 consecutive days rather than 7 to pay out again. It now resets when a streak ends or restarts — but not when a sync backfills a missing day, which extends the same streak.
