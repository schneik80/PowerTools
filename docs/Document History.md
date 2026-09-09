# Document History

[Back to README](../README.md)

## Overview

The **Document History** command adds a **History** button to the Autodesk Fusion Quick Access Toolbar (QAT) and opens a palette that shows the active document's version history as a stack of day rows, newest at the top.

Each row is one calendar day. Inside a day, every person who saved gets their own track, and each save is a dot placed at the time of day it happened, on a clock that runs from midnight on the left to midnight on the right. Between two rows, a label says how much time passed &mdash; "Next day", "3 days later", "1 year, 2 months and 3 days later".

That layout answers questions a single version list cannot: who was working on this design, how a working day was shaped, whether two people were saving over each other, and how long the design sat untouched between bursts of work.

Reaching Fusion's own history panel otherwise means right-clicking the root component in the browser panel &mdash; a non-obvious interaction that is easy to overlook.

## Prerequisites

- A document must be open in Autodesk Fusion.
- The document must be saved to an Autodesk Hub. Version history is cloud data, so an unsaved document has none.

## Access

Select **History** from the **Quick Access Toolbar (QAT)**, immediately to the left of **Save**.

![access](./assets/dochistory.PNG)

## Reading the view

### Day rows

Rows run newest first. Each row's heading gives the date &mdash; **Today** and **Yesterday** are named rather than dated &mdash; and the number of saves that day. Rows alternate between a plain and a shaded band so a long history stays countable.

The column of circles down the left is the author gutter: one identity disc per track, coloured from the person's Autodesk user id so the same person is the same colour in every row. The gutter is frozen against the left edge, so it still says who no matter how far the view is scrolled.

Where a day has more than six people, the remaining tracks merge into a single track marked **+N**. Nothing is dropped &mdash; every save still has its own dot and its own hover card.

### The clock axis

By default a row is a 00:00 to 24:00 clock fitted to the palette width, so noon sits in the same column in every row and one day's shape can be compared with the day above it.

Saves closer together than the dots are wide are nudged apart so a burst does not collapse into a blob. When a dot has been moved, a faint hairline marks the time it actually happened, and the hover card always carries the exact timestamp.

Where a day is too crowded for that nudging to keep the dots on the right side of the hour markers &mdash; a morning save pushed past **12 PM** would read as an afternoon one &mdash; the row drops its interior markers and keeps only midnight at each end. It then says what order the day's events came in rather than what time they happened, which is all the drawing can honestly support. Narrowing the palette makes this more likely, since there is less width for the same day.

### The markers

| Marker | Meaning |
|---|---|
| Plain grey dot | An ordinary save. |
| Small open ring | An edit that made no new version &mdash; a property change, a part number, a marker &mdash; only shown with **Show other changes** on. Creating a milestone or a release is not shown this way; it marks the save it was made against, on the dot. |
| Grey dot with a blue ring | A milestone. |
| Blue dot with a blue ring | A release &mdash; a milestone you gave a revision name, such as "A" or "Rev B". Milestones Fusion names for itself ("Milestone V7", "Item Update") are shown as milestones, not releases. |
| Outer ring | The version a public share link points at. |

The legend below the view lists only the markers that occur in this document's history.

### The index

Every dot can carry a small three-part number above it, counted from the oldest event forward. There are two ways to see them:

- **Rest the pointer on a track.** That person's numbers appear for as long as the pointer is in their row, and nothing else moves. Each number is drawn on a small patch of the row's own background, so it stays readable where it crosses the track above.
- **Turn on Index** to show all of them at once. The day rows open up while it is on, so that every number sits inside its own author's track rather than drifting over the one above, and close again when it is off. They open by only as much as the longest number in the history needs, so a document with no releases barely grows at all.

| Event | What it counts up |
|---|---|
| A release | The first figure. The second and third restart at zero. |
| A save or a milestone | The second figure. The third restarts at zero. |
| Any other change | The third figure. |

Counting starts at `0.0.0`, and the first figure is left off until a release has actually been named &mdash; before that it is always zero, so printing it spends a third of every number on a digit that cannot change. A document with no releases therefore shows two-figure numbers throughout, and the rows stay tighter for it:

```
             counted as   printed as
save           0.1.0         1.0
save           0.2.0         2.0
property       0.2.1         2.1
property       0.2.2         2.2
release A      1.0.0         1.0.0
save           1.1.0         1.1.0
milestone      1.2.0         1.2.0
```

So a two-figure number means "no release yet at this point" and a three-figure one carries its release count. The release itself is also the only number drawn in the accent colour, so the two never have to be told apart by counting figures.

Because a save restarts the third figure, turning **Show other changes** on and off never renumbers a save &mdash; the other changes fill in around them and the saves keep the numbers they had.

The numbers lean at an angle above their dots, each ending at the mark it names. That is what lets every event carry one: printed flat, a number needs as much clear width as it is wide, and a busy day does not have it. Only where a day holds more saves than the row can separate at all do some numbers drop out, and the hover card still carries those.

A release's number is drawn in the accent its dot is filled with, so the releases stand out when scanning a long history; every other number is plain text.

### The elapsed-time labels

Between two day rows, a rule and a phrase say how long the design was untouched. The weight of the rule scales with the gap &mdash; a hairline for the next day, a dashed rule for a week or more &mdash; so a long silence is felt before it is read.

### The hover card

Rest the pointer on an open ring to see what the change was &mdash; "Property change", the property and its new value, when, and who. There is no thumbnail or version number, because no version was made.

Rest the pointer on a dot to see that version's thumbnail, version number, milestone and release markers, the description typed at save time, the exact local timestamp, and who saved it.

Both carry the event's [index](#the-index) number, whether or not **Index** is on &mdash; so pointing at an event always tells you its number, including the ones a crowded day had to leave off the plot.

The thumbnail is fetched from the cloud only for the version you actually rest on, and cached for the rest of the session, so scanning across a busy day costs nothing.

## Layout options

| Option | What it does |
|---|---|
| **Show other changes** | Adds the edits that did not produce a version &mdash; property changes, part numbers, markers &mdash; each as a small open ring on its author's track. This can add people: someone who edited a property but never saved does not appear at all with this off. Creating a milestone or a release is left out, because the save it was made against already carries it; the consequence is that someone who only named a release, and never saved, is credited on neither. Hidden entirely for a document whose history could not be read from the cloud, since those edits are not visible there. |
| **Show thread across days** | Switches the horizontal axis from the clock to the version's position in the history: every save is one column apart, and a line threads them in order across the day rows. Empty time then costs no width, so a long history scrolls sideways inside the box, with a dashed seam wherever the axis crosses from one day into the next. |
| **Index** | Numbers every event with a version of its own, and opens the day rows up to fit them. Leave it off and rest the pointer on a track to read one person's numbers without the view growing. See [The index](#the-index) below. |
| **Show all N days** | Appears when a history runs past 60 days. The view renders the most recent 60 by default; this draws the rest. |

The clock view is the default because it is the one that never scrolls sideways and keeps every row on the same scale. Turn the thread on when the question is "what order did these happen in", rather than "when in the day".

## Notes

- The palette takes a moment to open while it reads the history from Fusion's cloud; Fusion shows a busy indicator in the status bar meanwhile.
- The palette shows a snapshot taken when it was opened. Select **History** again to re-read the history after saving.
- Authorship comes from Fusion's cloud data. If the design is not in a hub, or you are offline, the palette still draws the history but every save is attributed to the document's creator, because that is all the desktop API can tell it.
- The history is read from the cloud, so a document with hundreds of versions takes a moment to open. Fusion shows a busy indicator while it reads.
- Fusion exposes a public share link on the document rather than on a specific version, so the public-share ring marks the current version.
- Where Fusion could not resolve who saved a version, the track is drawn as an unknown author rather than dropped, and a version with no usable date collects in a trailing **Date unknown** row.

> **Developers:** see the [architecture notes](./arch/Document%20History.md).

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
