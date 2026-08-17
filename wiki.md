# Player guide

## The basics

By far the biggest driver of your progress is you simply doing your Anki reviews. Answer cards, earn XP, gain levels. Along the way you earn gold and gems, spend them in
a shop on collectible items, and those items make everything you earn a little bigger.

The game's "day" is Anki's day, not midnight — it follows **Preferences → Scheduler →
Next day starts at**. Reviews you do on your phone count too, as soon as you sync.

The first thing you'll notice is a bar that appeared at the bottom of your Anki window. What you see there is customizable from `CollectQuest` → `Options` button.

## XP per answer

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

## Levels

Level 2 takes 100 XP, and each level after that 20 more than the last. Leveling up pays 20 gold and has a 15% chance of a gem. There is no level cap, but after level 50 you might consider the [prestige](#prestige) feature. In the `CollectQuest` window there's a picture of your house that changes as you level up. It stops changing at **level 153**. 

## Daily quests

Two quests are rolled each day, sized from the reviews Anki has actually scheduled for you,
so a quest can never ask for more than Anki will hand you. You'll never get two of the same
kind on one day. A third — clearing the day — is always there.

| Quest | What it asks for | XP | Gold | Gem instead of gold |
|---|---|---|---|---|
| Review cards (all decks) | 30–70% of due, at least 30 | 20–140 | 8–24 | 14–30% |
| Review cards (one deck) | 30–70% of deck's due, at least 30 | scaled by deck size | scaled likewise | scaled likewise |
| Get answers correct | 15–30% of due, at least 15 | 30–85 | 8–18 | 14–22% |
| Study new cards | 3–6 new cards | 25–50 | 6–12 | 14% |
| Bonus quest | every card Anki had due | 20 | 10 | 5% |

Every quest pays its XP, plus **either** the gold or a gem — never both. Which one is decided
when the quest is created, and within each band the bigger the target rolled, the more it pays
and the likelier the gem. On top of that, finishing any quest rolls separately for a further
bonus gem, so a quest whose reward was already a gem can hand you two.

Every answer counts towards review quests, including `Again`; correct-answer quests need
`Good` or `Easy`.

### Deck-specific quest requirement

A deck qualifies only if all three hold:

- Its share of the day's due is **between 15% and 90%** — any smaller and the quest would be
  trivial, any larger and it would just repeat the all-decks quest.
- It has **at least 30 cards due**, so the quest can never ask for more than the deck holds.
- It isn't a filtered deck.

Deck counts include subdecks, exactly as the deck list shows them, so a quest for a parent
deck also counts reviews done in its children. You can freely rename your deck (quest label will update), but deleting a deck will cancel the quest for that deck.

## Gems

Gems are the game's second currency. Their main use is **crafting**; later on they can also be
traded for XP once your collection is complete, or for prestige points once you can
[prestige](#prestige). They come in five colours: blue, green, pink, purple and yellow.

Crafting spends one gem of every colour and gives you a random item you don't own yet, drawn from
everything unlocked at your level. Recent unlocks are strongly favoured: an item that unlocks at
your current level is 16 times as likely as one from 15 or more levels back, though past that
point the bias stops growing and all the older items share the floor. Crafting is the only way to
get the 15 items that have no gold price.

| Where gems come from | What you get |
|---|---|
| Shop | 20–50 gold for a colour you pick, 30 gold for a random one |
| Levelling up | One guaranteed gem every 5th level, plus a 15% chance on any level-up |
| Daily quest reward | Some quests pay a gem instead of gold, decided when the quest is rolled |
| Daily quest gem roll | Every finished quest rolls for a bonus gem; the clear-the-day one starts at 5% |
| 7-day streak | The gem reward pays 2 gems (1 below level 20), plus gold |

Every one of those except the shop is improved by **gem luck** from your items, so gems compound:
more gems means more crafted items, which means more luck. When the 15% level-up roll succeeds
there is a further 3% chance of a second gem from the same level-up, and on every 5th level the
guaranteed gem stacks on top of both — so a single level can pay out three.

## Streak

Your streak is read from Anki's own review history, so it survives reinstalls and counts days
you studied on any device. Every 7 days in a row pays one reward, and you can see which type
is coming:

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

- **Gems** cost 20–50 gold for a chosen colour, or 30 gold for a random one.
- **Crafting**: one gem of each of the 5 colours makes a random item you don't own yet.
  Some items can *only* be obtained this way — they have no gold price. See [Gems](#gems).
- **Auto-refresh** happens every 2 hours for everyone, with no key needed. A Silver Key
  shortens that to every hour.
- **Manual refresh** needs at least a Bronze Key. That gives you one free refresh a day (two with the
  Golden Key), after which each costs 15 gold, rising by 15 every time.
- **Trading**, once you own every item: all your gold becomes XP at 3 XP per gold, and each
  gem becomes 100 XP.

## Stats

Every item's effect is built from the stats below. There is nothing to equip and there are no
slots — owning an item is the same as using it, and everything you own counts at once.

| Stat | What it does |
|---|---|
| **XP %** | Raises XP from reviews, daily quests and streak rewards. |
| **XP per answer** | Added to a card's value before the button share is taken, so `Good` gains the full amount and `Again` a fifth of it. Answers only — it does not touch quest rewards. |
| **Gold %** | Raises gold from daily quests, level-ups and streak rewards. |
| **Gold per payout** | Added in full to level-up and streak gold, and at half strength to daily quest gold. |
| **Gem luck %** | Improves the gem chance on level-up and on the streak gem reward at full strength, and on every daily quest's gem roll at half strength. |
| **Quest&nbsp;gem&nbsp;chance&nbsp;%** | Improves every daily quest's gem roll. Works even if you own no luck items. |
| **Streak&nbsp;reward&nbsp;%** | Scales the whole 7-day streak payout, and improves its gem roll. |
| **Prestige points** | Grants an extra point each time you prestige, on top of the level payout. |

Percentages are added up, never multiplied together: +10% XP from items and +30% XP from a
prestige upgrade give +40%, not +43%.

## Items

63 items in total. An item can only be owned once, and everything you own counts together.

### Bought with gold (48)

Available in the shop once you reach the listed level. Most can also turn up from gem crafting (**Craftable** column).

| Item | Level | Gold | Craftable | Effect |
|---|---|---|---|---|
| Bracelet | 1 | 40g | yes | +2g per payout, +1% XP |
| Cup | 1 | 25g | yes | +2g per payout |
| Fish | 1 | 42g | yes | +3% gem luck |
| Package | 1 | 28g | yes | +2% gem luck |
| Red Potion | 1 | 40g | yes | +2% XP |
| Stone | 1 | 32g | yes | +1 XP per answer |
| Blue Potion | 5 | 55g | yes | +1 XP per answer |
| Hard Tooth | 5 | 45g | yes | +3g per payout |
| Poison Tooth | 5 | 50g | yes | +3% gem luck |
| Red Tooth | 5 | 48g | yes | +2g per payout, +2% gold |
| Axe | 8 | 60g | yes | +2% XP, +1% gold |
| Crystal | 8 | 65g | yes | +2 XP per answer |
| Wood Shield | 8 | 70g | yes | +1% gem luck, +1g per payout |
| Hammer | 10 | 80g | yes | +4g per payout |
| Red Potion II | 10 | 75g | yes | +3% XP |
| Bronze Key | 12 | 120g | yes | Unlocks manual shop refresh: 1 free/day, then 15g+ |
| Blue Potion II | 14 | 105g | yes | +2 XP per answer |
| Strong Axe | 14 | 95g | yes | +2% XP, +2% gold |
| Strong Hammer | 16 | 120g | yes | +4g per payout, +5% gold |
| Lucky Clover | 18 | 333g | yes | +6% gem luck |
| Great Axe | 22 | 150g | yes | +4% XP, +3% gold |
| Red Potion III | 22 | 145g | yes | +5% XP |
| Great Hammer | 24 | 190g | yes | +8% gold |
| Blue Potion III | 26 | 231g | yes | +3 XP per answer |
| Dragon Tooth | 26 | 200g | yes | +5% quest gem chance |
| Gold Ring | 30 | 250g | yes | +10% gold |
| Epic Axe | 35 | 290g | yes | +6% XP, +4% gold |
| Red Potion IV | 35 | 280g | yes | +8% XP |
| Epic Hammer | 40 | 300g | yes | +12% gold |
| Blue Potion IV | 45 | 374g | yes | +4 XP per answer |
| Sword | 45 | 350g | yes | +10% quest gem chance |
| Red Gem | 50 | 400g | yes | +20% streak reward |
| Blue Potion V | 55 | 473g | yes | +5 XP per answer |
| Red Potion V | 55 | 420g | yes | +10% XP |
| Crown | 60 | 500g | yes | +4% XP, +8% gold |
| Meat Feast | 65 | 380g | no | +2 XP per answer, +3g per payout |
| Shield | 70 | 550g | yes | +8% XP, +4% gold |
| Falcon Bow | 72 | 520g | yes | +15% quest gem chance |
| Reinforced Shield | 78 | 650g | no | +8% gold, +4% XP |
| Legendary Hammer | 80 | 580g | yes | +18% gold |
| Legendary Axe | 85 | 800g | yes | +15% XP, +5% gold |
| Candle of Focus | 90 | 750g | no | +20% quest gem chance |
| War Hammer | 90 | 900g | no | +20% gold, +2% XP |
| Battle Axe | 95 | 900g | no | +17% XP, +5% gold |
| Piggy Bank | 95 | 900g | no | +5g per payout, +10% gold |
| Chronicle of Ascension | 100 | 1500g | no | +1 prestige point per prestige, +5% XP |
| Snow Banner | 105 | 850g | no | +30% streak reward |
| Enchanted Lamp | 110 | 900g | no | +10% gold, +10% quest gem chance |

### Obtainable with gems only (15)

These have no price and never appear for sale. The only way to get one is crafting — one gem
of each of the five colours, which rolls a random item you don't own yet.

| Item | Level | Effect |
|---|---|---|
| Leaf | 8 | +4% gem luck |
| Blue Ring | 18 | +4% XP, +1 XP per answer |
| Silver Key | 22 | Shop auto-refresh hourly instead of every 2 hours |
| Island | 26 | +15% streak reward |
| Coin Chest | 30 | +8g per payout, +5% gold |
| Skull | 40 | +10% gold, +6% gem luck |
| Golden Key | 45 | 2 free manual shop refreshes per day instead of 1 |
| Trophy Cup | 50 | +15% gold |
| Void's Eye | 50 | +6% XP, +6% gold, +6% gem luck |
| Blue Shield | 55 | +25% quest gem chance |
| Palm Tree | 60 | +8g per payout |
| Gemstone | 70 | +12% gold, +8% gem luck |
| Lucky Necklace | 78 | +2% XP, +2% gold |
| Rune Gemstone | 80 | +10% XP, +10% gold |
| Tome of Beginnings | 90 | +1 prestige point per prestige |

### Keys are a special case

The three keys are the only items that grant no stats at all. Instead of making your rewards
bigger, they change how the shop behaves — and unlike everything else, they have to be collected
in order.

| Key | Level | How to get it | What it does |
|---|---|---|---|
| Bronze | 12 | 120 gold, or crafting | Unlocks manual refresh: 1 free a day, then 15 gold, rising by 15 each time |
| Silver | 22 | Crafting, requiring Bronze | Shop refreshes by itself hourly instead of every 2 hours |
| Golden | 45 | Crafting, requiring Silver | 2 free manual refreshes a day instead of 1 |

Owning a higher tier key doesn't interfere with the effects of the previous tiers.

## Prestige

From **level 50** you can prestige: your XP, level, gold, gems, items, house and quests all
reset, in exchange for permanent prestige points. Your points, the upgrades you've bought and
your interface settings survive. Difficulty goes back to Steady and you're asked to pick again.

**You lose the items themselves, not just access to them.** Your collection is emptied, and
reaching an item's level again doesn't give it back — you have to buy or craft it a second
time, at full price. That's the real cost of prestiging early, since items unlock as high as
level 110.

**Your streak is not affected.** It's read from Anki's review history, so both the current run
and your all-time best reappear as soon as the game next checks. One quirk: the count of 7-day
rewards you've already claimed *does* reset, so prestiging in the middle of a long streak pays
out one reward straight away.

You gain **2 points at level 50, plus 1 more for every full 10 levels above it**. So level 60
pays 3, level 100 pays 7. The two tomes each add 1 more to every prestige you do while you hold
them, and the prestige window breaks down where your points are coming from.

**Trading gems for points.** The prestige window has a row that turns 3 of each colour into
1 extra point, using a button that only lights up once you hold 3 blue, 3 green, 3 pink,
3 purple and 3 yellow. The point isn't paid at once — it's banked as "pending" and added to
your next prestige, and you can repeat the trade as often as your gems allow. Since prestiging
destroys your gems but keeps the pending points, it's worth spending every spare set this way
just before you reset. Note the whole window is out of reach until you can prestige, so gems
can't be banked during your first climb to level 50.

| Upgrade | Each level gives |
|---|---|
| Global XP | +30% XP |
| Global gold | +30% gold |
| Starting gold | +100 gold at the start of each run |
| Streak reward | Doubles a 7-day streak payout (then triples, and so on) |
| Quest reward | +40% chance of a gem from daily quests |

Upgrades get dearer as you deepen them: the first level of an upgrade costs 1 point, the
second 2, the third 3, and so on. Spreading points across several upgrades is much cheaper
than pushing one to the top.

Because each extra point costs another 10 levels, and levels keep getting more expensive,
prestiging soon after level 50 earns points faster than grinding far past it. The reason to
wait is the collection, which you have to rebuild from nothing each time.
