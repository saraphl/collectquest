# Changelog

## 2.4.0

### Gem scrambler

Dungeons can now hold a gem scrambler. Each branching you find has a 15% chance to put one on the path ahead, at most one per dungeon, so about every other dungeon has one. It shows up just before the next branching could be found, and only if you hold at least 6 gems.

The scrambler takes every gem you hold and gives them back in random colors, but one gem per 10 is destroyed in the process (1 for 1–10 gems, 2 for 11–20, and so on). It's meant for piles that lean heavily on one or two colors, which hold crafting and prestige point purchases back.

It works like a branching: the `Dungeon` button lights up, reviews answered while it waits are queued up, and the count toward the next branching carries on.

The Auto-pick window has a separate setting for it, which works whether or not pathways are picked automatically: **Decide manually** (the default), **Always scramble** or **Always ignore**.

### Dungeon prestige upgrades

Two new prestige upgrades: **Dungeon discovery** (+20% chance to find a dungeon per level) and **Dungeon exploration** (+20% faster dungeon exploration per level).

### Temporary buffs

A new temporary buff, "All dungeon progression is 30% faster", can now be awarded by the bonus quest. It multiplies the chance to find a dungeon and to reach the next branching by 1.3 after all your other bonuses

The base chance to get a temporary buff from the bonus quest was raised by 5%. The first raise was also swapped with the "Bonus quest gold +20%" milestone reward, so it's awarded sooner:

| Milestone | Before | Now |
| - | - | - |
| #4 | Buff chance 15% | Buff chance 20% |
| #10 | Bonus quest gold +20% | Buff chance 25% |
| #11 | Buff chance 20% | Bonus quest gold +20% |
| #13 | Buff chance 25% | Buff chance 30% |

### Streak reward upgrade nerf

The prestige Streak reward upgrade now gives +40% 7-day streak rewards per level instead of +100%. To make up for it, the XP week pays more to everyone: 1,200 XP at level 50 instead of 975, and 744 at level 20 instead of 600. Gem and gold weeks are unchanged.

### Other changes
- New notification toggle in **Options → Notifications**: "Auto-picked dungeon choices" covers the pathways auto-pick takes and the scramblers it answers, so they can be silenced without hiding entrances and treasure rooms.
- The "Reviews pay 20% more XP" buff now multiplies your review XP after all other bonuses, instead of adding 20% to your XP bonus. For example, with +100% XP from items, a review worth 5 XP before bonuses now pays 12 instead of 11.
- The 7-day streak reward notification now stays on screen for 7 seconds instead of 5.

## 2.3.0

### Deck blacklist

Decks you aren't studying can now be crossed out in **Options → Deck blacklist**. They no longer get deck quests, and their due cards no longer inflate the "Review cards" and "Get answers correct" targets or the bonus quest objective. Crossing out a parent deck covers its subdecks. Changes apply from the next day.

### Difficulty rework

Difficulty is now a multiplier on everything a review earns: Casual earns 30% more XP than Steady, and Heavy User 30% less. Previously it only set the base XP per review, so items adding XP per review slowly erased the difference.

The multiplier is applied after every item bonus, so the gap now stays the same at every level. These are the starting figures before any modifiers:

| | Before | Now |
|---|---|---|
| Casual | 9 XP per Good | 9.1 XP per Good |
| Steady | 7.2 XP per Good | 7 XP per Good |
| Heavy User | 4.5 XP per Good | 4.9 XP per Good |

Difficulty now also affects dungeons, by half as much: Casual has a 15% higher chance to find and explore dungeons, and Heavy User 15% lower. Quests, streak rewards and level-ups are not affected.

### Crafting is priced by the item's level

Crafting used to cost 1 gem of each color at every level, so late in a run it was nearly free. It now costs one of each for every 30 levels of the item you'll get, rounded up:

| Item unlocks at | Price |
|---|---|
| Level 1–30 | 1 of each color |
| Level 31–60 | 2 of each color |
| Level 61–90 | 3 of each color |
| Level 91–120 | 4 of each color |
| Level 121–150 | 5 of each color |

Your next craft is now picked in advance and stays the same until you craft it. The item is still a surprise, but the button names its level range and price, e.g. `Craft a level 61–90 item (3 of each)`. While the discount buff runs, the button shows the four gem colors it charges instead. That buff now reads "Crafting skips your scarcest gem color" instead of "Crafting costs 4 gems instead of 5".

Trading gems for prestige points also gets dearer: the first trade in a run still costs 3 of each, but every further one costs one more, back to 3 after you prestige. The trade row no longer says "one-time only", which was never true.

### Trading for XP opens earlier

Trading gold or gems for XP used to open only once you owned everything the shop sells. Now each opens as soon as that currency has nothing left to buy: gold once you own every item sold for gold, and gems once you own every item crafting can make. Until now, a player who had crafted everything could only hoard gems until the last gold item was bought.

Gems also stay on sale for gold once you own everything, along with the **Restock** button, so gold can still become gems for the prestige trade. The Prism's color trade no longer disappears at that point either, and the shop drops the level and XP line it showed there.

### Faster dungeon exploration buffed

Faster dungeon exploration now also shortens the 50 reviews you wait after each branching before the next one can be found, instead of only raising the chance once that wait is over. At +25% the wait is now 40 reviews instead of 50, and it never drops below 20.

The existing exploration items you can buy or craft were also buffed:

| Item | Before | Now |
|---|---|---|
| Crystal Ball | +7% | +12% |
| Delver's Ring | +10% | +15% |
| Lantern | +18% | +25% |

### New items

13 new items, and the highest unlock level goes from 110 to 130:

| Item | Level | How to get it | Effect |
|---|---|---|---|
| Miner's Torch | 32 | 280 gold | +15% faster dungeon exploration |
| Oath Ring | 35 | Crafting only | +50% 7-day streak rewards |
| Prism | 40 | Crafting only | Lets you trade gems in the shop |
| Spelunker's Rope | 55 | 480 gold | +20% faster dungeon exploration, +3% XP |
| Hourglass | 60 | Crafting only | +30% faster dungeon exploration |
| Cartographer's Kit | 75 | 650 gold | +20% faster dungeon exploration, +20% chance to find a dungeon |
| Elixir of Insight | 100 | 1100 gold | +12% XP, +8% gem luck |
| Royal Banner | 105 | 1000 gold | +75% 7-day streak rewards |
| Ancient Coin | 110 | Crafting only | +10g earned |
| Dragonbone Axe | 115 | 1200 gold, or crafting | +20% XP, +6% gold |
| Titan's Hammer | 120 | 1200 gold, or crafting | +24% gold, +3% XP |
| Prospector's Pick | 125 | 1300 gold | +25% faster dungeon exploration, +25% chance to find a dungeon |
| Dragon Heart | 130 | Crafting only | +12% XP, +12% gold, +15% gem luck |

With the Prism, a new **Trade** button under **Craft** swaps the color you have most of for the one you have fewest of. The first trade each day costs 2 gems for 1, and each one after that costs one gem more. It can only be used when a trade would even out your colors.

### New milestone

Milestone #16 was added. The objective is a new 16-day streak, and completing it makes temporary buffs last 4 days instead of 3. Buffs already running when you complete it gain the extra day too.

### Fixes

- A shop panel left open while prestiging could still sell items from the run before, including ones above your new level.
- After prestiging, the Prestige window kept its old height, leaving stray gaps between its lines until the next purchase closed them. It now shrinks right away.

## 2.2.4

### Options window

The most common notifications are now configurable, to keep the game in line with one of the original philosophy pillars, which is that the game shouldn't be too distracting to the Anki user. This held true at the start, but with more added features it is possible that some users may find the current notifications to be too much.

The Options window is now split into categories: **Gameplay** (difficulty, save, reset progress), **Interface** (bottom bar settings, previously "Bottom UI") and a new **Notifications** category. All of the notifications are still enabled by default.

#### Other changes in Options window
- Changing the difficulty no longer closes and reopens the window.
- The "Run sync now" button was removed. Reviews from other devices are credited automatically after each sync anyway.
- The "Longest previous streak" line was removed as well.

## 2.2.3

### 7-day streak rewards rebalancing

The "7-day streak reward" stat was by far the least rewarding one, especially if you have a decent review load. In its original state it paid next to nothing, so some rebalancing had to be done.

Base rewards were drastically increased, most notably XP (2-3 times of what it was). When gold reward is rolled, it now also includes "gold earned" stat, which it didn't before.

Items boosting streak rewards were also boosted across the board. They also unlock sooner and cost less. Since items are lost on prestige, it doesn't make much sense to have them unlocked too far into a run.

| | Before | Now |
|---|---|---|
| Island | level 26, +15% | level 12, +30% |
| Red Gem | level 50, 400g, +20% | level 25, 200g, +45% |
| Snow Banner | level 105, 850g, +30% | level 40, 350g, +60% |

### Milestone #15

A new milestone added: **loot 3 items from dungeons**. Its reward makes every dungeon found afterwards bigger by one branching, 4-7 instead of 3-6.

### Quest reroll conditions

The quest reroll now only swaps to a quest you can still finish today, and never asks for more than what's left (with the reward lowered to match). When nothing finishable is left, the button is disabled and its tooltip says why.

The daily "Study new cards" quest now needs at least 3 new cards in your collection instead of 1, because that's the minimal target it can roll. It will also never ask for more new cards than what remains in your Anki collection.

### Consistent streak counting

On the two days a year when the clocks change, a review done around the "Next day starts at" hour could count toward a different day for the streak than for Anki and the quests. All of them now split days the same way Anki does.

### Shop's 10 reviews requirement

After undoing reviews until less than 10 are done for the day, the shop button now stays unlocked.

If Anki stayed open past the start of a new day, the shop counted the previous day's reviews and could be opened before any review was done. It now waits for 10 reviews on the new day.

### UI changes

- Items window now has a fixed width of 10 item icons and only grows taller with more items. Its icons get smaller from 33 and from 48 items owned.
- Shop window resizes due to "Restock now" button becoming "Restock now (15g)". Close button is now the same width as in the CollectQuest window, and "Sold" labels keep their place when every item is bought.
- Hover tooltips now stay up for as long as the cursor is on them, instead of flashing briefly. Many useless tooltips were removed.
- Summary of item bonuses now shows the total 7-day streak reward bonus on its own line, above the dungeon bonuses.

## 2.2.2

### Long streaks are counted in full

Streaks were previously hard-capped at 400 days and this also influenced the repeating 7-day streak counter. It should now be unlimited.

### UI change

Temporary buff awarded by completing the bonus quest now has a separate notification.

## 2.2.1

### Bonus quest's objective reacts to changes

Once the number of reviews for the bonus quest was decided, reducing the real number using Anki's features made the quest unreachable for the day. It is now very forgiving, so the user isn't discouraged from using Anki's core features.

Taking cards off today's schedule — suspending, burying, deleting, setting a due date, or limiting reviews in Custom Study or in deck options — lowers the objective by that many cards, but at most 70% of the day can be taken off this way. Past that the bonus quest is out of reach for the day. Bringing enough cards back or reviewing ahead using Custom Study makes the bonus quest completable again.

### XP reward rebalancing

The "XP/review" stat made the individual reviews give way too much XP in comparison with quests and dungeons. This was very apparent in my own playthrough on level 84, where each review gave me about 50 XP, while quests only about double that.

Only the Blue Potions carry "XP per review" now. Stone, Crystal, Blue Ring, Steel Shoulders, Meat
Feast and Bronze Helm trade it for an XP percentage instead, which lifts everything you earn rather
than reviews alone.

At the same time every other source gives a lot more:

| | Before | Now |
|---|---|---|
| Review cards quest | 20–140 XP | 60–220 XP |
| Get answers correct quest | 30–85 XP | 70–160 XP |
| Study new cards quest | 25–50 XP | 50–100 XP |
| Bonus quest | 40 XP | 120 XP |
| Branching pathway found | 40 XP | 110 XP |
| Treasure room reached | 70 XP | 220 XP |

### Purchasable items rebalancing

With the Blue Potions now the only source of "XP per review", they were the cheapest source of XP in the shop. Prices rise across the line, and the two highest level ones are unlocked even later in the run.

| Potion | Level | Gold |
|---|---|---|
| Blue Potion | 5 | 55 → 95 |
| Blue Potion II | 14 | 105 → 185 |
| Blue Potion III | 26 | 231 → 350 |
| Blue Potion IV | 45 → 50 | 374 → 480 |
| Blue Potion V | 55 → 60 | 473 → 580 |

Some of the cheapest items in the shop were also adjusted.

| Item | Level | Gold | Bonus |
|---|---|---|---|
| Stone | 1 | 32 → 18 | +1 XP per review → +1% XP |
| Bracelet | 1 → 2 | 40 | +2g earned, +1% XP |
| Red Potion | 1 → 2 | 40 | +2% XP |
| Fish | 1 → 3 | 42 | +5% gem luck |

### UI change

In Dungeon window, dungeon-related bonus stats are now one formatted block and it only appears when the player reached 110+ reviews without finding an entrance or progressing inside a dungeon.

## 2.2.0

### Dungeons

New feature available from level 15 - Dungeons. Refer to its [chapter on wiki](https://github.com/saraphl/collectquest/wiki/Player-guide#dungeons) for more info.

### 15 new items

7 are sold in the shop or made by crafting: Smoke Pipe, Compass, Treasure Map, Crystal Ball, Delver's Ring, Lantern and Steel Shoulders.

8 more are found only in dungeon treasure: Bronze Helm, Mushroom, Slingshot, Poison, Skull Scroll, Winged Shoes, Loot Bag and Red-eyed Skull.

You can see their bonuses in the [items chapter on wiki](https://github.com/saraphl/collectquest/wiki/Player-guide#items).

### Items window

The Items window now breaks your collection down by where each item comes from: purchasable items, gem-only items, and dungeon loot.

The shop's completion message reads "You own everything the shop sells" instead of "You own all collectibles", because dungeon loot is found rather than sold. The gold and gem trades still open as soon as you own everything the shop can offer you.

### Prestige

The confirmation now mentions dungeons among the things a prestige resets, and warns you separately when you are part way through one or have a treasure waiting to be claimed. It does not stop you — you can close it, claim, and come back.

## 2.1.5

### UI changes

- The 7-day streak reward is a regular notification instead of a separate window you have to close.
- Milestone #3's reward reads "Craft gem-only items first" instead of "Targeted craft".
- The two daily quests always appear in the same order now, whichever way they were rolled.
- Quest rewards are written in smaller gray text.
- Active temporary buffs have their own section below your items, instead of sitting under the milestone row.
- Items are listed in their own window now, opened with the [▸] button beside the Items heading.
- The streak accumulator's charge, and the magnets counted toward its next upgrade, moved from the Milestones window to CollectQuest window.
- The Prestige window shows one star beside "Prestiged N times" instead of a growing grid of them.
- Prestige upgrade rows are no longer bold, and the window opens wider so each upgrade's effect is easier to read.

## 2.1.4

### Streak accumulator charging

- A milestone that raises the accumulator's cap no longer fills it straight away if you had a long enough streak going. It will charge progressively now, just like when the accumulator first unlocked.
- Formatting changed for its charging progress in Milestones window.

### Quests

- The "Study new cards" quest now asks for 3 to 5 new cards instead of 3 to 6, and smaller targets come up more often: 3 cards is three times as likely as 5.

### Prestige UI

- Prestiging no longer closes the Prestige window. The window updates itself and points can be spent immediately.
- CollectQuest window (where the Prestige window is opened from) also updates itself now (doesn't require to be reopened).
- Hidden one irrelevant label when prestiging is unavailable yet.

## 2.1.3

### Prestige button moved back

The Prestige button returns to the CollectQuest window, to the left of Options. On the bottom bar it spent most of a run just sitting there being purely informative until level 50 comes round again.

### Windows stack properly

Opening Prestige or Options from the CollectQuest window and then minimizing Anki could bring the CollectQuest window back on top of them. Since those windows are modal, nothing on the CollectQuest window would respond to clicks. They now behave like the Milestones window, which never had the problem, and any window added to that panel later will too.

### One-time pop-ups

- The "Prestige unlocked" pop-up was rewritten: it now names level 50, says where the button is, and lists all five upgrades your points buy instead of just XP and gold.
- It and the "house fully expanded" congratulations now appear only once per profile. Both used to come back after a prestige, once you climbed to their level again.

## 2.1.2

### Changes to Prestige feature

- Gem luck raised from 20 to 30% and moved up to third place among the upgrades.
- Fixed a bug where gem counts in Prestige window didn't update immediately after trading them in.
- Redesigned and rewritten various elements in the Prestige window, mostly to make them consistent with the rest of the game.
- The Prestige button now sits on the bottom bar between Shop and CollectQuest, instead of inside the CollectQuest windowm if prestige is unlocked. "Invert button order" still swaps just Shop and CollectQuest, leaving Prestige in the middle.
- Your difficulty setting now carries over instead of resetting to Steady.
- No more pop-ups when you prestige. The welcome screen no longer reappears, and the 7-day streak reward you'd already claimed isn't handed out a second time.
- The confirmation no longer claims your streak will be reset, because it never was.
- The shop stays open after you prestige. It used to lock again and ask for 10 fresh reviews, even though you'd already done them - and it let you back in as soon as you restarted Anki.

### CollectQuest window

- Past level 170 the house picture used to disappear from the window entirely, along with the "Best House obtained!" line under it. The final house now stays for good.
- With no items owned, the empty box under Items is replaced by a "No items owned yet." line.

### Other

- Various buttons now have fixed width and align to the right instead of center.

## 2.1.1

### More UI changes

- Both collectible items and gems in shop now display unified "Sold" label when purchased and the "Buy" button gets hidden afterwards.
- The shop's countdown now reads "New stock arrives in" instead of "Auto-refresh" and the button below it is "Restock now" instead of "Refresh".

### Fixes

- A milestone asking you to complete both daily quests no longer counts the day it opened if one of that day's quests was already finished.
- The message about reviews credited from a sync no longer lands on top of Anki's default sync notification.

## 2.1.0

### Milestones

New feature available from level 10 - Milestones. Refer to its [chapter on wiki](https://github.com/saraphl/collectquest/wiki/Player-guide#milestones) for more info.

### Gem economy rework

Squashed 2 gem modifier stats into one that's multiplicative rather than additive. Items and prestige rewards were rebalanced around this. Second gem roll on level up removed due to needless added complexity. Instead gem chance over 100% guarantees 1 gem and rolls for the extra one. For example 120% gem chance awards 1.2 gems on average.

### Streak counting and cleaner start for new players

There's less pop-up spam for new users. A notice about a new version makes no sense for a fresh install, and there's no "Streak awarded" pop-up immediately after starting, because now streak can only be as long as the number of days since you launched CollectQuest for the first time.

A brand new profile now shows only the level/XP bar at the bottom of Anki's window. The streak, gold and gems, and quests can all be switched back on in Options -> Bottom UI. Existing profiles keep whatever they had before. 

### Clearer labels

- The shop's "Today's items" heading is now "Purchasable items", with a count of how many of them you already own - the same style as the count beside Items in the CollectQuest window. "Gem crafting" got the same count, covering the items only crafting can give you.
- The CollectQuest window now says "Next house expansion at level N" instead of "Next unlock at level N".

### Smoother icons

The original images used throughout the game were rendering noticeably jagged, even though the source images are of pretty high quality. They now look nicer throughout all windows.

### Fixes

- Items documented on wiki as "gold-only" were still craftable with gems.
- Removed empty space that would sometimes appear above the "Gem crafting" heading in the shop window after Craft button was pressed.
- The original icons for Red Tooth and Dragon Tooth were actually full jaws of teeth, so these were renamed accordingly.

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
