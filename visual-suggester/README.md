# Weekly visual suggester

Drafts 8 visual concepts a week for Relai's social channels, sketches each one,
and puts them on a review board. Output is an advisory draft. Nothing here
posts anything and nothing here creates a task on Paula's board.

Sibling of `weekly-suggester/`, same shape: generate on a schedule, review by
hand, route the decisions. The difference is what it proposes and what it is
checked against.

## The hard boundary

This tool writes to `batches/`, `board/`, `queued/` and `state/` and nowhere
else. It never touches `evergreen.txt` or `fresh.txt`, and it never writes to
Notion: filing a brief is `route.py` printing a payload for the
`design-brief-creator` skill, in a chat session, after review.

Every concept is written out at `Compliance: unapproved`.

## Pieces

| File | When it runs | What it does |
|---|---|---|
| `snapshot.py` | Manually, monthly | Normalizes a dump of Paula's Design board into `state/board.json`. No network, no model call. |
| `generate.py` | Weekly, in Actions | Reads `board.json` plus the copy pools and the X archive ranking, drafts the batch with Claude, writes `batches/YYYY-Www.{md,json}` |
| `notify_slack.py` | Weekly, after generate | Posts a pointer to the batch, not the batch |
| `build_board.py` | Manually, weekly | Injects the batch into `board_template.html`, writes `board/YYYY-Www.html` to publish as the review artifact |
| `route.py` | Manually, after review | Files every decision: briefs out, flagged held, cuts recorded |
| `config.py` | Never | Every tunable: the format catalog, counts, model, brief defaults |

`.github/workflows/visual_suggester.yml` runs generate then notify, Tuesday
morning, and commits the batch back. Tuesday, not Monday: the X batch lands
Monday and two review boards in the same hour means one does not get reviewed.

## Where a concept comes from

Four sources, in rough order of how cheap they are to ship. The batch reports
the spread, and a run that returns eight of one kind is a run worth looking at.

- **evergreen line.** A line already in `evergreen.txt` or `fresh.txt`. The
  words passed compliance review as a specific list, so only the picture is
  new. 223 cleared lines sit there and almost none have ever been an image.
- **archive theme.** A subject that landed more than once on @relai_app,
  evidenced by `weekly-suggester/state/pool.json`.
- **format rerun.** A format Paula has already built, with a new subject. She
  has the layout, so the build is short.
- **net new.** Neither. Allowed, capped at two per batch, and where a genuinely
  new shape comes from.

## The format catalog

`config.FORMATS` is twelve formats read off the board rather than invented.
Every one has shipped at least once, so proposing a new subject inside one is
proposing something Paula already has a layout for.

Each entry carries a `needs` line, the honest precondition. `two_line_chart`
needs a real dataset for both lines; `phone_mockup` needs a screen that
actually exists. A concept proposed in a format whose precondition it cannot
meet is a concept that dies in production, and that is where most of the waste
in this pipeline used to sit.

The model sees a saturation count beside each format, taken from the board
snapshot. `versus` is at eight. Saturated is not banned, but a fifth version of
a format needs a better reason than a first version of something else.

Add a format only after it has shipped. The model may also answer
`new_format`, which costs a build from scratch, so it is capped.

## The board snapshot

`state/board.json` is a committed snapshot of Paula's Design board. It is what
stops the tool proposing what Relai already made, and it is what the format
catalog's saturation counts come from.

**It is not fetched by the Action.** Reading Notion from a runner would need a
`NOTION_TOKEN` secret, an internal integration granted on the board, and a DORA
register entry for a new machine-to-machine path into a system that already
holds the design pipeline. For what: an exclusion list that goes stale slowly.

So it is refreshed from a chat session, where the Notion connector is already
authenticated as a human, and the result is committed. Same call as `rank.py`
running offline against the X archive.

To refresh: query the board, save the response, then

```bash
python3 visual-suggester/snapshot.py ~/Downloads/design-board.json
```

Then commit `state/board.json`.

`snapshot.py` drops request-driven rows, listed in `config.NOT_A_CONCEPT`. Blog
images, email headers, app icons and `This Week in Bitcoin` are jobs sent to
Paula when something specific needs a picture, not concepts a suggester could
have proposed, so counting them as prior art would suppress ideas nobody has
had yet. The first snapshot kept 47 of 81 rows.

A stale snapshot costs a repeated concept, caught by the reviewer.
`state/made.json` separately records every concept this tool has sent to Paula
and is never stale, so the repeats the tool itself could cause stay covered
even when the snapshot is a month behind. Monthly is enough.

## The sketches

`generate.py` draws every concept as a rough SVG, rendered on the review board.
The point is to judge composition at the moment of the decision rather than
read a paragraph describing it.

They are **not deliverables and are never sent to Paula**, who works from the
written direction. The palette in `config.MOCK_PALETTE` is a placeholder, not
Relai's brand values, which live in the brand book and are not in this repo.
The board says so on every card, and the review UI is deliberately teal so the
placeholder orange in a sketch is not mistaken for a brand decision.

A sketch is model-written SVG, so it is screened twice on the same rule:
`clean_svg` in `generate.py` before it is stored, and `svgIsInert` in the board
before it is inserted. Scripts, event handlers and any reference outside the
sketch itself are rejected, and the card falls back to showing the written
direction. A batch file can be hand-edited, and inert-on-adoption script nodes
are a browser detail rather than a guarantee to build on.

A failed sketch call is not fatal. The batch is still reviewable.

## Review and routing

`build_board.py` writes the week's board. Publish it as the **same** artifact
each week rather than minting a new one, so `config.REVIEW_URL` in the Slack
message stays valid.

The board holds the week's concepts with the sketch, the source, the nearest
thing already on the design board, and how the concept differs from it.
Headline, caption and visual direction are all editable in place. Edits
autosave to localStorage keyed by week, so a reload mid-review loses nothing.

`Save decisions` writes `visual-batch-YYYY-Www-decisions.json` to Downloads.
Then in a chat session:

- **make, and it is clean**: `route.py` prints a brief payload and the
  `design-brief-creator` skill files it on Paula's board and returns the URL.
  A Notion task is internal work, not publication; what she builds is reviewed
  before it posts, same as every other asset on that board.
- **make, and it carries a flag**: held in `queued/YYYY-Www.md`. Not sent to
  Paula. Nothing reads that file.
- **cut**: recorded in `state/rejected.json` so it never comes back.

Edits are filed as edits, with the original kept beside them, so a change is
never silent. Routing is idempotent per submission: `state/routed.json` stamps
the week, and briefs are tracked per concept, so shipping a review twice does
not leave Paula two of the same job.

## Why a flag holds a visual but not a copy rewrite

`weekly-suggester/route.py` promotes a rewrite of an already-published tweet
straight into `fresh.txt`, on Arsen's standing approval as Marketing Lead. That
rests on the source line having already gone out from the account.

A visual concept has no such source. It is a new asset, and under
**MiCA Art. 66** the flagged terms need written compliance approval before it
goes live, not after Paula has built it. So a flagged concept stops at
`queued/` and Guglielmo sees it first. Savings terminology always lands there.
This matches `skills/design-brief-creator/SKILL.md`, which stops to ask when a
line carries a compliance flag.

`route.py` re-runs `DROP_CHECKS` and `FLAG_CHECKS` on the headline and caption
before anything goes out, because both are editable on the board and an edit
can introduce a term the batch never had.

## The mechanical checks are a net, not approval

`DROP_CHECKS` and `FLAG_CHECKS` come from `compliance_checks.py` at the repo
root, the same module `weekly-suggester/config.py` imports. One copy on
purpose: two would drift and the drift would be silent.

They run on the **headline and caption only**, not the visual direction. That
text is an instruction to a designer rather than published copy, and a
direction reading "avoid any price projection" would trip the projection check
on the word itself.

Judgment rules are not mechanically checkable: whether a concept reads as
advice, whether a figure is verified, tone, political association. Those rely
on the model's self-check against the two skills and on the human review that
follows. **A clean check is not compliance approval.**

## needs_check

Every concept lists the figures, prices, dates and factual claims a human has
to verify before the asset is built. Relai marketing numbers come from its own
backtest tool or verified data and are never approximated, so a concept leaning
on a number the model cannot source has to say so rather than guess.

`route.py` carries the list into the brief payload as `verify_before_build`.
Carry it into the brief. A figure nobody sourced must not be set in artwork.

## Secrets

Repo Settings, names only. Both are already set for the X suggester and this
adds none.

- `ANTHROPIC_API_KEY` for `generate.py`
- `SLACK_WEBHOOK_URL` for `notify_slack.py`, the same webhook as the X
  suggester so both batches land in the same DM

The repo is public and so are Actions logs. Nothing here prints a secret. The
webhook URL is itself the credential, so it must stay out of error messages.

## Costs

Two Sonnet calls a week, one for the concepts and one for the sketches, plus a
re-request round when concepts get dropped. Both skills are cached across the
calls in a run. The sketch call is the more expensive of the two on output
tokens. Published Sonnet rates change, so check the current rate rather than
quoting one from memory.

## Testing

The workflow takes `dry_run`, defaulting to true. A dry run does all the local
work and exits before the API call, so it does **not** test the Anthropic key
or the Slack webhook. Only a live run does that.

`board/example.html` is a fixture built from four hand-written concepts, used to
check the review flow end to end without an API call. It is not a real batch.

## Python

stdlib only, no pip install step, matching the rest of the repo. `snapshot.py`
avoids `zoneinfo` so it runs on the system Python 3.9 on a Mac; the rest runs
on that and on the runner's 3.12. That is why `config.py` is a Python module
rather than YAML or TOML: PyYAML needs a pip install and `tomllib` only exists
from 3.11.
