# Changelog

## 2.1.0

### Milestones

New feature available from level 10 - Milestones. Refer to its [chapter on wiki](https://github.com/saraphl/collectquest/wiki/Player-guide#milestones) for more info.

### Gem economy rework

Squashed 2 gem modifier stats into one that's multiplicative rather than additive. Items and prestige rewards were rebalanced around this. Second gem roll on level up removed due to needless added complexity. Instead gem chance over 100% guarantees 1 gem and rolls for the extra one. For example 120% gem chance awards 1.2 gems on average.

### Quieter start for new players

A brand new profile now shows only the level/XP bar at the bottom of Anki's window. The streak, gold and gems, and quests can all be switched back on in Options -> Bottom UI. Existing profiles keep whatever they had before. 

There's also less pop-up spam for new users (a notice about a new version makes no sense for a fresh install). The pop-ups now appear in expected order: first the welcome, then streak reward.

### Clearer labels

- The shop's "Today's items" heading is now "Purchasable items", with a count of how many of them you already own - the same style as the count beside Items in the CollectQuest window. "Gem crafting" got the same count, covering the items only crafting can give you.
- The CollectQuest window now says "Next house expansion at level N" instead of "Next unlock at level N".

### Two fixes

- Items documented on wiki as "gold-only" were still craftable with gems.
- Removed empty space that would sometimes appear above the "Gem crafting" heading in the shop window after Craft button was pressed.

## 2.0.3

### Mostly more UI cleanup

- CollectQuest doesn't fight for Anki's native singleton tooltip on sync action anymore, but it'll display its own clone of it in same style. It has an offset on Y axis and will show in the first "slot" on top of the default tooltip that's available.
- Nicer UI in the shop for gem crafting: Last crafted item will always be visible in the shop instead of just seeing its name once in a basic notification.
- Quest label of the deck-specific quest in will wrap to the new line if the deck's name is too long.
- Reworked how the shop UI looks when the player owns all items and can only spend gold and gems on XP. It should feel much cleaner now.
- Unified formatting of items' effect labels — same effects should now be written the same way consistently.

### Changes to gems in the shop

Gems purchasable from the shop previously came in two versions — a random one for 30 gold, or a predetermined one (color rolled randomly) with cost between 20 and 50 gold (also rolled randomly). That seemed a bit chaotic. The cost is now always constant. The random one remains unchanged, the one with predetermined random color now always costs 45 gold and there's also a new variant for 60 gold — the color you currently own the fewest of. That color remains unchanged until the next shop reset.

## 2.0.2

### Player guide

There is now a [player guide](https://github.com/saraphl/collectquest/wiki/Player-guide), covering hopefully everything the player would need to know, including complete list of items to collect and explanations to the mechanics of this game.

### The shop makes you wait longer

The shop restocked itself every 2 hours even without a key, which made restocking feel too frequent already. It now restocks every 4 hours by default, and the Silver Key halves that to 2 hours instead of 1. Manual refreshes are unchanged.

The shop's countdown now reads `4h 0m` rather than `120m 0s`.

### Keys have to be collected in order

Previously crafting could've handed you the Golden Key first, which would make the subsequent acquisition of Bronze Key completely useless. It now offers the Silver Key only once you own the Bronze, and the Golden only once you own the Silver.

### The bonus quest is a proper daily quest

Finishing every due card paid a flat 20 XP and 10 gold no matter what you owned, so it shrank into irrelevance next to the two quests above it while every other reward grew with your collection. Your XP and gold bonuses now apply to it, the same items improve its gem chance, and its line shows what it will actually pay you.

Like the other quests it now pays **either** its gold **or** a gem, rather than gold with a gem on the side. Roughly one day in twenty is a gem day.

### Two fixes

Tome of Beginnings and Chronicle of Ascension promised an extra prestige point every time you prestige and never delivered one. They now work, and the prestige window shows where each point comes from.

Items granting a flat amount of XP per answer were also adding that amount to every quest reward, which was never advertised. It now applies to answers only. Percentage bonuses are unaffected.

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

Pressing Again didn't award any XP, even though it's an important part of SRS process. It now awards 20% of what Good does, based on the difficulty. Heavy User difficulty no longer punishes pressing Hard, which awards 50% XP of Good. With these changes, XP received for pressing Good was scaled down to 90% of its former design, to balance things out a little.

### Fixed various cosmetic issues with the UI

Quest text didn't fit the CollectQuest window, extremely wide buttons on top of each other instead of side by side, white text on bright background in dark mode, uncentered elements on the bottom bar, replaced custom blue notifications with Anki's standard singleShots, and likely more.

## 1.1.2

This is the last version of the original add-on. See its [AnkiWeb page](https://ankiweb.net/shared/info/627746544) for version history.
