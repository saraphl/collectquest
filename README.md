# CollectQuest (fork)

A personal fork of [CollectQuest](https://ankiweb.net/shared/info/627746544) by Florent Baris — an RPG-style progression layer for Anki (XP, levels, daily quests, gold, gems, collectibles, streaks, prestige).

All credit for the original add-on goes to the upstream author. This fork exists only to carry a few local changes.

## Changes in this fork

### Daily resets follow the scheduler's day, not civil midnight

Upstream decided "what day is it?" with a plain `datetime.now().strftime("%Y-%m-%d")`, i.e. midnight local time, ignoring Anki's **Preferences → Scheduler → Next day starts at** setting. With the default 4 a.m. rollover, a review at 00:30 belonged to *yesterday* as far as Anki was concerned, but already started a *new* day of CollectQuest quests — so a late-night session would roll fresh quests and burn progress into them before you went to bed.

The day boundary is now taken from the collection's `rollover` config, which is what the streak code already did.
