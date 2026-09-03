# Player guide

## The basics

By far the biggest driver of your progress is you simply doing your Anki reviews. You'll start gaining XP and levels. Along the way you earn gold and gems, spend them in a shop on collectible items, and those in turn make you earn more in the future.

The first thing you'll notice is a bar that appeared at the bottom of your Anki window. What you see there is customizable from `CollectQuest` → `Options` button.

The game's "day" starts at whatever Anki's `Preferences → Scheduler → Next day starts at` setting considers a new day. Reviews you do on your phone count too, as soon as you sync.

## XP per review

Every button earns something. How much depends on the difficulty you picked in Options:

| Difficulty | Again | Hard | Good | Easy |
|---|---|---|---|---|
| Casual | 1.8 | 4.5 | 9 | 10.8 |
| Steady | 1.44 | 3.6 | 7.2 | 8.64 |
| Heavy User | 0.9 | 2.25 | 4.5 | 5.4 |

`Again` is worth 20% of `Good` and `Hard` 50%, on every difficulty. Pressing the honest button
always pays — you never lose XP by admitting you forgot a card.

Fractions are never thrown away. If an answer is worth 7.2 XP you'll be paid 7, 7, 7, 7, 8
and so on; the leftovers are saved up and paid out as whole points.

Using Anki's undo feature (`Ctrl+Z`) takes back what it paid — XP, gold, gems, and any quest progress it made. This add-on intentionally ignores Anki's redo feature, so if you want the card to count again, answer it again rather than redoing it.

## Levels

Level 2 takes 100 XP, and each level after that 20 more than the last. Leveling up pays 20 gold and has a 15% chance of a gem. There is no level cap, but after level 50 you might consider the [prestige](#prestige) feature. In the `CollectQuest` window there's a picture of your house that changes as you level up. It stops changing at **level 153**.

## Daily quests

Two quests are rolled each day, sized from the reviews Anki has actually scheduled for you,
so a quest can never ask for more than Anki will hand you. You'll never get two of the same
kind on one day. A third, bonus quest, tasking you with completing all your due reviews, will be there every day.

| Quest | What it asks for | XP | Gold | Gem |
|---|---|---|---|---|
| Review cards (all decks) | 30–70% of due, at least 30 | 20–140 | 8–24 | 14–30% |
| Review cards (one deck) | 30–70% of deck's due, at least 30 | scaled by deck size | scaled likewise | scaled likewise |
| Get answers correct | 15–30% of due, at least 15 | 30–85 | 8–18 | 14–22% |
| Study new cards | 3–5 new cards, smaller targets more likely | 25–50 | 6–12 | 14% |
| Bonus quest | every card Anki had due | 40 | 10 | 10% |

Every answer counts towards "Review cards" quests, including `Again` — but only on reviewed cards, not new. 
"Get answers correct" quest is advanced with `Good` or `Easy` answers, on both reviews and new cards.

### Deck-specific quest requirement

A deck qualifies only if all three hold:

- Its share of the day's due is **between 15% and 90%** — any smaller and the quest would be
  trivial, any larger and it would just repeat the all-decks quest.
- It has **at least 30 cards due**, so the quest can never ask for more than the deck holds.
- It isn't a filtered deck.

Deck counts include subdecks, exactly as the deck list shows them, so a quest for a parent
deck also counts reviews done in its children. You can freely rename your deck (quest label will update), but deleting a deck will cancel the quest for that deck.

### Bonus quest

Any day you have reviews due, there will be a third, bonus quest. It tasks you with completing all your due reviews for the day. This is decided when Anki is opened for the first time of the day, and the objective doesn't change. Be aware that if you delete cards that are due for today or limit your review load (in deck options or with Custom Study) after the objective was already decided, you won't be able to finish this quest until you raise the limit back or "review ahead" using Custom Study. Learning new cards won't contribute to this objective.

## Gems

Gems are the game's second currency. Their main use is crafting. Later on they can also be
traded for XP once your collection is complete, or for prestige points once you can
[prestige](#prestige). They come in five colors: blue, green, pink, purple and yellow.

Crafting spends one gem of every color and gives you a random item you don't own yet, drawn from
everything unlocked at your level. Recent unlocks are strongly favored: an item that unlocks at
your current level is 16 times as likely as one from 15 or more levels back, though past that
point the bias stops growing and all the older items share the floor. Crafting is the only way to
get the 15 items that have no gold price.

| Where gems come from | What you get |
|---|---|
| Shop | 30 gold for a random color, 45 for the color on offer, 60 for the one you have fewest of |
| Leveling up | One guaranteed gem every 5th level, plus a 15% chance on any level-up |
| Daily quest reward | Some quests pay a gem alongside their gold, decided when the quest is rolled |
| 7-day streak | 2 gems (1 below level 20), plus a gem luck roll on top |

Every one of those except the shop is improved by **gem luck** from your items, so gems compound:
more gems means more crafted items, which means more luck. When the 15% level-up roll succeeds
there is a further 3% chance of a second gem from the same level-up, and on every 5th level the
guaranteed gem stacks on top of both — so a single level can pay out three.

## Streak

Your streak is read from Anki's own review history, but it can only be as long as the number of days
since you launched CollectQuest for the first time.

Every 7 days in a row pays one reward, and you can see which type is coming:

| Type | Payout at level 20 | at level 50 |
|---|---|---|
| XP | 252 XP | 450 XP |
| Gems | 2 gems + 18 gold | 2 gems + 45 gold |
| Gold | 60 gold + 42 XP | 120 gold + 97 XP |

Those are the figures before any items — your XP and gold bonuses apply on top. Payouts grow
every 10 levels. Breaking a streak resets the count, but a sync that fills in a missed day
repairs it rather than punishing you.

## Shop

The shop opens once you've passed **10 reviews** for the day, and offers **3 slots**. Slots
can hold a collectible or a gem.

- **Gems** come in three offers: 30 gold for a random color, 45 for whichever color the shop
  names that day, or 60 for the one you have fewest of. You never pick the color yourself.
- **Crafting**: one gem of each of the 5 colors makes a random item you don't own yet.
  Some items can *only* be obtained this way — they have no gold price. See [Gems](#gems).
- **Automatic restock** happens every 4 hours for everyone, with no key needed. A Silver Key
  halves that to every 2 hours.
- **Manual restock** needs at least a Bronze Key. That gives you one free restock a day (two with the
  Golden Key), after which each costs 15 gold, rising by 15 every time.
- **Trading**, once you own every item, you can trade all your gold for XP at 3 XP per gold piece, and each
  gem becomes 90 XP.

## Stats

Every item's effect is built from the stats below. There is nothing to equip and there are no
slots — owning an item is the same as using it, and everything you own counts at once.

| Stat | What it does |
|---|---|
| **XP %** | Raises XP from reviews, daily quests and streak rewards. |
| **XP per review** | Added to a card's value before the button share is taken, so `Good` gains the full amount and `Again` a fifth of it. Answers only — it does not touch quest rewards. |
| **Gold %** | Raises gold from daily quests, level-ups and streak rewards. |
| **Gold earned** | Added in full to level-up and streak gold, and at half strength to daily quest gold. |
| **Gem luck %** | Multiplies every gem chance in the game — each quest's, the level-up gem, and the streak gem. |
| **7&#8209;day&nbsp;streak&nbsp;reward&nbsp;%** | Scales the whole 7-day streak payout, and improves its gem roll. |
| **Prestige points** | Grants an extra point each time you prestige, on top of the level payout. |

Once gem luck % is applied to the base gem chance, the final chance pushed past 100% pays one gem outright and rolls what's left over for another, so 120% is a guaranteed gem plus a 20% shot at a second — no luck is ever wasted.

## Items

63 items in total. An item can only be owned once, and everything you own counts together.

The CollectQuest panel shows how many you have and what they add up to. The `▸` button beside the heading opens a separate window with full list of owned items.

### Bought with gold (48)

Available in the shop once you reach the listed level. Most can also turn up from gem crafting (**Craftable** column).

| Item | Level | Gold | Craftable | Effect |
|---|---|---|---|---|
| Bracelet | 1 | 40g | yes | +2g earned, +1% XP |
| Cup | 1 | 25g | yes | +2g earned |
| Fish | 1 | 42g | yes | +5% gem luck |
| Package | 1 | 28g | yes | +3% gem luck |
| Red Potion | 1 | 40g | yes | +2% XP |
| Stone | 1 | 32g | yes | +1 XP per review |
| Blue Potion | 5 | 55g | yes | +1 XP per review |
| Hard Tooth | 5 | 45g | yes | +3g earned |
| Poison Tooth | 5 | 50g | yes | +5% gem luck |
| Red Teeth | 5 | 48g | yes | +2g earned, +2% gold |
| Axe | 8 | 60g | yes | +2% XP, +1% gold |
| Crystal | 8 | 65g | yes | +2 XP per review |
| Wood Shield | 8 | 70g | yes | +2% gem luck, +1g earned |
| Hammer | 10 | 80g | yes | +4g earned |
| Red Potion II | 10 | 75g | yes | +3% XP |
| Bronze Key | 12 | 120g | yes | Lets you restock the shop: 1 free/day, then 15g+ |
| Blue Potion II | 14 | 105g | yes | +2 XP per review |
| Strong Axe | 14 | 95g | yes | +2% XP, +2% gold |
| Strong Hammer | 16 | 120g | yes | +4g earned, +5% gold |
| Lucky Clover | 18 | 333g | yes | +10% gem luck |
| Great Axe | 22 | 150g | yes | +4% XP, +3% gold |
| Red Potion III | 22 | 145g | yes | +5% XP |
| Great Hammer | 24 | 190g | yes | +8% gold |
| Blue Potion III | 26 | 231g | yes | +3 XP per review |
| Dragon Teeth | 26 | 200g | yes | +8% gem luck |
| Gold Ring | 30 | 250g | yes | +10% gold |
| Epic Axe | 35 | 290g | yes | +6% XP, +4% gold |
| Red Potion IV | 35 | 280g | yes | +8% XP |
| Epic Hammer | 40 | 300g | yes | +12% gold |
| Blue Potion IV | 45 | 374g | yes | +4 XP per review |
| Sword | 45 | 350g | yes | +16% gem luck |
| Red Gem | 50 | 400g | yes | +20% 7-day streak reward |
| Blue Potion V | 55 | 473g | yes | +5 XP per review |
| Red Potion V | 55 | 420g | yes | +10% XP |
| Crown | 60 | 500g | yes | +4% XP, +8% gold |
| Meat Feast | 65 | 380g | no | +2 XP per review, +3g earned |
| Shield | 70 | 550g | yes | +8% XP, +4% gold |
| Falcon Bow | 72 | 520g | yes | +24% gem luck |
| Reinforced Shield | 78 | 650g | no | +8% gold, +4% XP |
| Legendary Hammer | 80 | 580g | yes | +18% gold |
| Legendary Axe | 85 | 800g | yes | +15% XP, +5% gold |
| Candle of Focus | 90 | 750g | no | +32% gem luck |
| War Hammer | 90 | 900g | no | +20% gold, +2% XP |
| Battle Axe | 95 | 900g | no | +17% XP, +5% gold |
| Piggy Bank | 95 | 900g | no | +5g earned, +10% gold |
| Chronicle of Ascension | 100 | 1500g | no | +1 prestige point per prestige, +5% XP |
| Snow Banner | 105 | 850g | no | +30% 7-day streak reward |
| Enchanted Lamp | 110 | 900g | no | +10% gold, +16% gem luck |

### Obtainable with gems only (15)

These have no price and never appear for sale. The only way to get one is crafting — one gem
of each of the five colors, which rolls a random item you don't own yet.

| Item | Level | Effect |
|---|---|---|
| Leaf | 8 | +6% gem luck |
| Blue Ring | 18 | +4% XP, +1 XP per review |
| Silver Key | 22 | New stock every 2 hours instead of 4 |
| Island | 26 | +15% 7-day streak reward |
| Coin Chest | 30 | +8g earned, +5% gold |
| Skull | 40 | +10% gold, +10% gem luck |
| Golden Key | 45 | 2 free restocks per day instead of 1 |
| Trophy Cup | 50 | +15% gold |
| Void's Eye | 50 | +6% XP, +6% gold, +10% gem luck |
| Blue Shield | 55 | +40% gem luck |
| Palm Tree | 60 | +8g earned |
| Gemstone | 70 | +12% gold, +13% gem luck |
| Lucky Necklace | 78 | +2% XP, +2% gold |
| Rune Gemstone | 80 | +10% XP, +10% gold |
| Tome of Beginnings | 90 | +1 prestige point per prestige |

### Keys are a special case

The three keys are the only items that grant no stats at all. Instead of making your rewards
bigger, they change how the shop behaves — and unlike everything else, they have to be collected
in order.

| Key | Level | How to get it | What it does |
|---|---|---|---|
| Bronze | 12 | 120 gold, or crafting | Unlocks manual restocking: 1 free a day, then 15 gold, rising by 15 each time |
| Silver | 22 | Crafting, requiring Bronze | Shop restocks by itself every 2 hours instead of 4 |
| Golden | 45 | Crafting, requiring Silver | 2 free manual restocks a day instead of 1 |

Owning a higher tier key doesn't interfere with the effects of the previous tiers.


## Milestones

**Unlocks at level 10.** Once you've [prestiged](#prestige) it stays unlocked no matter what level you drop back to.

Fourteen goals worked through one at a time, in a fixed order. Each pays a reward, and the next
one only opens when the current one is done. **Counters start from zero the moment a milestone
opens** — nothing you did before it counts.

The `CollectQuest` panel shows the one you're on. The `▸` button beside it opens the full track.

| # | Goal | Reward |
|---|---|---|
| 1 | Reach a new 4-day streak | Streak accumulator, +5% cap |
| 2 | Complete the bonus quest 3 times | Bonus quest XP +15% |
| 3 | Complete both daily quests 5 times | Craft gem-only items first |
| 4 | Reach a new 8-day streak | Bonus quest can award buffs (15%) |
| 5 | Craft 3 items | Accumulator to +10% cap |
| 6 | Complete the bonus quest 5 times | Quest reroll, once a week |
| 7 | Complete both daily quests 10 times | Shop offers 4 items |
| 8 | Prestige 2 times | Magnets appear in the shop |
| 9 | Reach a new 12-day streak | Accumulator to +15% cap |
| 10 | Craft 6 items | Bonus quest gold +20% |
| 11 | Complete the bonus quest 7 times | Buff drop chance to 20% |
| 12 | Complete both daily quests 15 times | Accumulator to +20% cap |
| 13 | Complete the bonus quest 10 times | Buff drop chance to 25% |
| 14 | Prestige 4 times | Accumulator also boosts gold |

**Quest reroll** puts a `⟳` button on each unfinished daily quest once #6 is done. It swaps that
quest for a different kind, keeping the other one and its progress, and can be used once every
seven days.

**Craft milestones state their position** rather than shrinking or quietly completing. If fewer
items remain craftable than the milestone still needs, the row reads `(will require prestiging)` —
prestiging empties your collection and so refills the pool. A level-up can take the note back off
by unlocking new items.

**Craft gem-only items first** narrows crafting to the 15 items that have no gold price — the ones
crafting is the only route to — at the usual cost. Once you own all of those that have unlocked at
your level, crafting goes back to drawing from everything.

Milestones survive a prestige. Everything else resets; the track doesn't.

### Streak accumulator

Unlocked by the first milestone and charges **1% per day**, up to a cap, and is lost when the streak breaks. 
It adds to your XP bonus, so it's worth most early on, when you own few items.

Streak accumulator has to be progressively charged, so **it starts from 1 charge on the day you unlock it**, 
even if you already have a long streak going — the same rule every milestone objective follows.
The same applies when a cap raise is unlocked — it won't jump up in charges by more than 1 a day.

Once milestone #14 is done and its 15 magnets are found,
the same charge that gives you XP bonus is added to your **gold** bonus as well. 
You can see the current charge under **Streak accumulator** in the panel, below your items.
While an upgrade is in progress, the magnets you have toward it are counted on the line beneath it.

### Temporary buffs

From milestone #4 on, completing the bonus quest can drop a buff. It lasts **3 days** and starts
itself — there's nothing to activate and nothing to save for later. The drop chance is 15%, rising
to 20% and then 25% further along the track. Running buffs are listed under **Temporary buffs** in
the panel, below your items, with the days each has left.

| Buff | Group | What it does |
|---|---|---|
| Reviews pay 20% more XP | Reviews | Reviews only — quest and streak rewards are unaffected |
| Double quest rewards, bonus quest included | Quests | Doubles their XP, gold and gems |
| Everything in the shop costs 20% less gold | Shop | Items, gems, magnets and paid restocks |
| Crafting costs 4 gems instead of 5 | Crafting | The color you have fewest of is free |
| Every gem reward is the most-needed color | Crafting | Changes which gem arrives, never how many |
| Double gem rewards | Crafting | Every gem you're *awarded* — shop purchases are unaffected |

**Only one buff per group runs at a time**, so the three crafting buffs never stack. Buffs from
different groups can run together.

A doubler doubles whatever the reward actually pays, so a quest whose gem luck pushed it to 2 gems
pays 4. The two doublers don't compound, though — with both running, a quest gem is still only
doubled once. The extra gems roll their own colors rather than copying the ones they double, so a
doubled reward isn't twice as lopsided as a normal one.

### Magnets

Magnets upgrade the accumulator. Each of the first three caps the track grants opens a faster
charge rate; the fourth upgrade is the closing one and changes what the charge does instead:

| Unlocked by | Magnets needed | What it does |
|---|---|---|
| Accumulator to +10% cap | 3 | charges 1.5% per day |
| Accumulator to +15% cap | 5 | charges 2% per day |
| Accumulator to +20% cap | 10 | charges 2.5% per day |
| Milestone #14 | 15 | the charge also counts as **gold** bonus |

**Magnets only turn up while an upgrade is in progress.** With nothing to collect for, they stop
appearing — including in the gaps between filling one upgrade and the track unlocking the next.

Completing the bonus quest has a 10% chance of dropping one, rolled separately from the buff, so a
single completion can give both. This starts as soon as the first upgrade opens.

The shop only stocks them once milestone #8 is done. From then on a restock has the same 10%
chance of offering one in place of an item, at a flat 50 gold, never more than one at a time —
and since a restock only happens while you have the shop open, you never miss one. Once you own
every item the shop drops its item list, so magnets stop appearing there until you prestige.

The upgrade completes itself the moment you find the last magnet.

## Prestige

From **level 50** you can prestige: your XP, level, gold, gems, items, house and quests all
reset, in exchange for permanent prestige points. Your points, the upgrades you've bought, your
[milestones](#milestones) and your interface settings survive.

A `Prestige` button appears in the `CollectQuest` window, left of `Options`, once prestige is
within reach, and stays there afterwards.

**You lose the items themselves, not just access to them.** Your collection is emptied, and
reaching an item's level again doesn't give it back — you have to buy or craft it a second
time, at full price. That's the real cost of prestiging early, since items unlock as high as
level 110.

**Your streak is not affected.** It's read from Anki's review history, so both the current run
and your all-time best reappear as soon as the game next checks, and a reward you've already
claimed isn't paid a second time.

You gain **2 points at level 50, plus 1 more for every full 10 levels above it**. So level 60
pays 3, level 100 pays 7. The two tomes each add 1 more to every prestige you do while you hold
them, and the prestige window breaks down where your points are coming from.

**Trading gems for points.** The prestige window has a row that turns 3 of each color into
1 extra point, using a button that only lights up once you hold 3 blue, 3 green, 3 pink,
3 purple and 3 yellow. The point isn't paid at once — it's banked as "pending" and added to
your next prestige, and you can repeat the trade as often as your gems allow. Since prestiging
destroys your gems but keeps the pending points, it's worth spending every spare set this way
just before you reset. Note the whole window is out of reach until you can prestige, so gems
can't be banked during your first climb to level 50.

| Upgrade | Each level gives |
|---|---|
| XP bonus | +30% XP |
| Gold bonus | +30% gold |
| Gem luck | +30% gem luck |
| Starting gold | +100 gold at the start of each run |
| Streak reward | Doubles a 7-day streak payout (then triples, and so on) |

Upgrades get dearer as you deepen them: the first level of an upgrade costs 1 point, the
second 2, the third 3, and so on. Spreading points across several upgrades is much cheaper
than pushing one to the top.

Because each extra point costs another 10 levels, and levels keep getting more expensive,
prestiging soon after level 50 earns points faster than grinding far past it. The reason to
wait is the collection, which you have to rebuild from nothing each time.
