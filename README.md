# Anki CollectQuest (fork)

A personal fork of [CollectQuest](https://ankiweb.net/shared/info/627746544) by Florent Baris — an RPG-style progression layer for Anki (XP, levels, daily quests, gold, gems, collectibles, streaks, prestige).

All credit for the original add-on goes to the upstream author. This fork exists only to carry a few local changes.

## Changes in this fork

Refer to the [changelog](CHANGELOG.md). Changes in this for begin with 

## Installing

Only step #3 applies if you're not already running the original version from AnkiWeb.

1. **Back up your progress first.** This is the `collectquest.json` file in `Anki2/<profile>/` directory. Without a copy there is no way back to your pre-fork progress.
2. Disable the original add-on.
3. Copy the files to a folder name that isn't a number, such as `collectquest-fork`, inside Anki's `addons21` folder (can be found via Anki's window:  **Tools → Add-ons → View Files**). Anki only auto-updates add-ons whose folder is the numeric id from AnkiWeb, so such name would let AnkiWeb overwrite the this add-on with something else.

**You can keep your existing progress.** Your level, XP, gold, gems, collectibles and prestige all carry over, and the day's quests are quietly swapped for the new ones the first time the fork refreshes. There is no need to start from scratch. The one exception is a save from a very old version of the original add-on, which this fork can no longer read; it gets renamed out of the way and you begin fresh, rather than it being overwritten.

Going back to the original later works, but the quests it finds will be ones it doesn't recognise, so they sit unchanged until the next day rolls them over.
