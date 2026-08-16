# Changelog

## 2.0.1

Revlog lookups optimized, such as streak counting logic only querying it on the first review of the day rather than each one.

Fixed a bug where `Again` was the only review result that advanced "Study N new cards" quest type.

## 2.0.0

### Daily resets follow the scheduler's day, not civil midnight

Daily quests previously reset at midnight local time, ignoring Anki's **Preferences → Scheduler → Next day starts at** setting. With the default 4 a.m. rollover, a review at 00:30 belonged to *yesterday* as far as Anki was concerned, but already started a *new* day of daily quests.

The day boundary is now taken from that setting, which is what the streak code already did. The same boundary applies to the shop's daily unlock and free refresh, and to which synced phone reviews count as today's — without that last one, reviews done between midnight and rollover were dropped rather than credited.

### Reward bonuses that silently did nothing

1. Several items promised bonuses the game never applied — a better chance of gems from daily quests, and bigger 7-day streak payouts — as did the prestige *Quest reward* upgrade, which cost points and did nothing. They now work.

2. The count of claimed 7-day rewards carried over when a streak broke, so after three payouts a fresh streak needed 28 consecutive days rather than 7 to pay out again. It now resets when a streak ends or restarts — but not when a sync backfills a missing day, which extends the same streak.

3. Awarded XP and gold used to be trimmed at integer level, so for example if one review awarded 5 XP, then with a bonus of 3% this would still be the same 5 XP. Such bonus would only be meaningful for quests where the reward can be high enough for this bonus to come into play. Both XP and gold are now awarded with a decimal carry, meaning if you were to get 5.2 XP five times in a row, it would go like: 5, 5, 5, 5, 6. The decimal part is never lost.

### Daily quests scale to your workload

Quest targets used to be fixed numbers — complete 25 reviews, get 12 correct — regardless of how much you actually had due. Targets are now a share of the reviews Anki has genuinely scheduled for you today, counted before you start and capped by your deck limits, so a quest can never ask for more than Anki will hand you. The reward scales with how much the quest asks for.

There are four kinds: all decks, a single deck, correct answers, and new cards. "Session" quests are gone — they were the ordinary review quest under a different name, with nothing session-like about them. New-card quests now appear whenever your collection holds new cards at all, rather than only when new cards are scheduled, so they still turn up if you introduce new cards through **Custom Study**. Reviews done on your phone count towards every kind once you sync, deck-specific quests included.

Two smaller changes came along with it. Every answer now counts towards review quests, including *Again* — correct-answer quests still need *Good* or *Easy*. Difficulty no longer changes quest targets, since those already follow your real workload; it only sets how much XP a review is worth.

### XP reward balancing

Pressing Again didn't award any XP, even though it's an important part of SRS process. It now awards 20% of what Good does, based on the difficulty. Heavy User difficulty no longer punished pressing Hard, which awards 50% XP of Good. With these changes, XP received for pressing Good was scaled down to 90% of its former design, to balance things out a little.

### Fixed various cosmetic issues with the UI

Quest text didn't fit the CollectQuest window, extremely wide buttons on top of each other instead of side by side, white text on bright background in dark mode, uncentered elements on the bottom bar, replaced custom blue notifications with Anki's standard singleShots, and likely more.

## 1.1.2

This is the last version of the original add-on. See its [AnkiWeb page](https://ankiweb.net/shared/info/627746544) for version history.
