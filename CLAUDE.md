# relai-x-bot

Marketing automation for Relai, a Swiss Bitcoin-only self-custody app.
Owner: Arsen Thagapsov, Marketing Lead. Timezone Europe/Zurich.

Posts to the official company X account @relai_app via GitHub Actions.

**Scope: X posting, plus the content suggesters that feed off the X archive.**
This repo automates posts to @relai_app. It does not cover App Store/Play
Store review monitoring or any other non-X tooling.

Two things sit just outside a strict reading of that, both deliberately:

- The weekly suggesters post a review pointer to Slack. The Slack message is
  the handoff to a human, not a channel.
- `visual-suggester/` proposes visual concepts that mostly ship on Instagram,
  not X. It lives here because it is built on the same X archive ranking, the
  same approved copy pools, the same compliance module and the same
  design-brief skill as the X image branch. Splitting it into its own repo
  would mean four of those five things existing twice. Added 9 Sep 2026.

---

## Working style

- Output first, questions after. Build it, then flag what needs correcting.
- No options menus when there is a clear recommendation. Give the recommendation.
- Bullets over paragraphs. One sentence per point.
- **Never use em dashes.** They make writing read as AI-generated.
- Be direct about uncertainty. "Likely" without a source is not acceptable.
  If a figure comes from a third party rather than the vendor, say so.

---

## Current state

### Live bots

| File | Workflow | Schedule | Content |
|---|---|---|---|
| `post_tweet.py` | `daily_tweet.yml` | Daily | `<Weekday> market update:\n\n1 BTC = 1 BTC` |
| `post_evergreen.py` | `evergreen.yml` | Every 2 days | One line from `evergreen.txt`, 223-line rotation |
| `post_fresh.py` | `fresh.yml` | Days evergreen does not post | Top line of `fresh.txt`, then drains it |

All three target 09:00-13:00 Europe/Zurich, hard cutoff 20:00.

**`fresh.txt` is the fast lane, and it is a queue, not a rotation.** Approved
copy posts within a day or two instead of waiting out the evergreen cycle,
which at 224 lines every 2 days takes over a year to come round. After a
successful post the line is removed from `fresh.txt`, appended to
`fresh_posted.txt`, and the change is committed. The drain is the state; there
is no separate state file.

It runs on the days evergreen does not, importing `is_posting_day` from
`post_evergreen` rather than copying the arithmetic, so the two can never post
on the same day even if `INTERVAL_DAYS` changes. An empty queue exits before
any API call, which is the normal case and costs nothing.

`fresh.txt` is **approved copy only**, same standing as `evergreen.txt`.
Anything in it posts publicly with no further review. It is not mirrored to
`relai-threads-bot`; that repo mirrors `evergreen.txt` only.

### Weekly X suggester

`weekly-suggester/`. Drafts 15 suggestions a week from the X archive for
manual review. Does not post. See `weekly-suggester/README.md`.

| File | When | What |
|---|---|---|
| `rank.py` | Manual, per archive | Archive to `state/pool.json`. Pure Python, no model calls |
| `generate.py` | `weekly_suggester.yml`, Mon | Drafts the batch with Claude Sonnet, writes `batches/YYYY-Www.{md,json}` |
| `notify_slack.py` | Same workflow | Posts a pointer to the batch, not the batch |
| `config.py` | Never | Every tunable: filters, counts, model, patterns |

**Ranking is offline on purpose.** The archive is ~105 MB and gitignored, so
the runner cannot see it. `pool.json` is committed and is what the Action
reads. The archive does not change week to week, so scheduling the sort was
always waste.

**It cannot reach the live pool.** The suggester writes to `batches/` and
`state/` only. Every line is written at `Compliance: unapproved`. Promotion
into `evergreen.txt` is a separate manual decision.

**Config is a Python module, not YAML or TOML.** PyYAML needs a pip install
and `tomllib` only exists from 3.11, while `rank.py` runs on the system
Python 3.9 on a Mac. `find_evergreen_candidates.py` already keeps its pattern
list this way.

### Weekly visual suggester

`visual-suggester/`. Drafts 8 visual concepts a week, sketches each one, and
puts them on a review board. Does not post and does not write to Notion. See
`visual-suggester/README.md`.

| File | When | What |
|---|---|---|
| `snapshot.py` | Manual, monthly | Design board dump to `state/board.json`. Pure Python, no model calls |
| `generate.py` | `visual_suggester.yml`, Tue | Drafts concepts and sketches with Claude Sonnet, writes `batches/YYYY-Www.{md,json}` |
| `notify_slack.py` | Same workflow | Posts a pointer to the batch |
| `build_board.py` | Manual, weekly | Batch plus `board_template.html` to `board/YYYY-Www.html`, published as the review artifact |
| `route.py` | Manual, after review | Briefs out, flagged held, cuts recorded |
| `config.py` | Never | Every tunable: format catalog, counts, model, brief defaults |

**Tuesday, not Monday.** The X batch lands Monday. Two review boards arriving
in the same hour means one of them does not get reviewed.

**It knows what Relai already made from a committed snapshot, not from
Notion.** `state/board.json` is refreshed in a chat session and committed, so
the Action needs no Notion credential and no new DORA register entry. A stale
snapshot costs a repeated concept, caught by review, and `state/made.json`
covers the repeats the tool itself could cause. Refresh monthly.

**The format catalog is read off the board, not invented.** Twelve formats,
each with the precondition it actually needs and a saturation count. `versus`
is at eight, so a ninth needs a better reason than a first of something else.
Add a format only after it has shipped.

**The sketches are thumbnails, never deliverables.** They exist so composition
can be judged at the moment of the decision. Paula works from the written
direction and never sees them. `config.MOCK_PALETTE` is a placeholder, not
Relai's brand values, which are in the brand book and not in this repo.

**A flagged concept never reaches Paula.** Unlike an X rewrite, a visual has
no already-published source line, so the standing approval does not reach it.
It stops in `queued/` for written sign-off. See Compliance below.

### Shared modules

`x_api.py`. Hand-rolled OAuth 1.0a HMAC-SHA1 signing, stdlib only.
Verified against X's documented test vector. Do not replace this with tweepy;
removing the pip install step was deliberate, it was a failure point.

`anthropic_api.py`. One structured-output call over urllib, with the retry
policy and the refusal and max_tokens handling. Both suggesters use it.

`compliance_checks.py`. `DROP_CHECKS` and `FLAG_CHECKS`, imported by both
suggesters' `config.py`. **One copy on purpose.** Two would drift and the
drift would be silent. A pattern edit here lands on both suggesters at once,
which is the point. The archive-ranking lists (`TIME_BOUND`,
`NOT_STANDALONE`) stayed in `weekly-suggester/config.py`; they are specific to
sorting the X archive.

### Offline tools

`find_evergreen_candidates.py`. Run manually against a downloaded X data
archive (zip, unzipped folder, or a direct tweet.js path). Lists standalone,
text-only tweets over a like threshold as CSV, sorted by likes. Feeds
candidates for the evergreen pool; does not touch `evergreen.txt` itself.
Takes no credentials, makes no API calls, not part of any workflow.

The raw X archive contains far more than public tweets (DMs, ad data). Never
commit it; `.gitignore` blocks the common patterns but treat that as a
backstop, not a guarantee.

### Skills

`skills/relai-social-copy/SKILL.md` is the binding voice and compliance spec.
`generate.py` loads it in full into its system prompt. Editing it changes what
the suggester produces, so treat it as compliance-reviewed content.

`skills/design-brief-creator/SKILL.md` handles the image branch of the review
step, filing briefs on Paula's Notion board. `visual-suggester/generate.py`
also loads it in full, alongside the voice skill, so a concept is drafted
against the same visual rules the brief will be written to.

Both skills being loaded by both suggesters means an edit to either one
changes what two pipelines produce. Treat them as compliance-reviewed
content.

Both are also installed as user skills in `~/.claude/skills/` so chat sessions
pick them up without this repo open. **Two copies means they can drift.** A
change here needs the same change copied to `~/.claude/skills/`, same as
`evergreen.txt` and the sibling threads repo.

---

## Architecture decisions, and why

**Four scheduled slots per posting day, any of which can post.**
Before posting, a run checks the account's recent posts for the exact text
and exits if found. GitHub runner acquisition fails often on this repo, so
one chance per day was not enough. Four independent chances, deduplicated by
reading the account rather than by keeping state.

**That deduplication only works when every slot computes the same line, so
`post_fresh.py` needs a second guard.** Evergreen is a rotation: all four
slots on a given day derive the same line from `EPOCH`, so slots 2 to 4
find it on the account and exit. A queue drains. Once slot 1 posts and
drains line A, line B is the new top, so slot 2 asks whether line B is on
the account, finds it is not, and posts it too. On 5 Sep 2026 that put
three lines out in 70 minutes, at 11:52, 12:38 and 13:02 UTC.

`posted_today()` closes it by reading `fresh_posted.txt` for today's date
before any API call, so the three losing slots cost nothing. The drain is
still the state; no new state file. Slot 0 is manual dispatch and
overrides, matching the existing convention in `in_window` and the
evergreen-day check.

A post that succeeded but failed to push writes no log entry, so the guard
correctly does not fire and the `already_posted` check still drains the
line without reposting. That recovery path is unchanged and is covered by
the test.

**Window guard on the local clock, not the cron.**
GitHub cron is best effort and has been landing 6 to 8 hours late here. A run
can never fire early, only late, so each script checks the real Europe/Zurich
time before posting. Past the cutoff it skips the day rather than posting at
the wrong hour.

**Cron times sit off the hour.** The top of the hour is GitHub's busiest
moment for runner allocation.

**DST is handled by picking UTC cron times that land inside the target
window in both CET and CEST.** 08:00-11:00 UTC works for a 09:00-13:00 local
window. Verify this whenever a window changes.

**Rotation is deterministic, seeded on a fixed date.**
`EPOCH` anchors it. Changing `EPOCH` or `SHUFFLE_SEED` reshuffles everything.
Do not change them casually.

**No state files, no database.** Everything derives from the date or from
reading the account. Nothing to reconcile after a missed run.

---

## Known problems

**GitHub scheduled runs are unreliable on this repo.** Delays of 6 to 8
hours, plus failures with "job was not acquired by Runner of type hosted".
Manual dispatch completes in 14 seconds. The repo was made public to get a
larger runner pool; effect still being observed as of 7 Aug 2026.

If it does not resolve: move the trigger off GitHub cron. An external
scheduler (cron-job.org) calling GitHub's workflow dispatch API gets the same
immediate behaviour as manual runs. Needs a fine-grained PAT with Actions
write. No code changes.

**X duplicate content.** X rejects identical or near-identical text posted
within roughly 24 to 48 hours. This is why the evergreen pool needs to stay
large and why any new recurring post needs enough variation. Not confirmed by
X, figure comes from a scheduling vendor.

**GitHub disables scheduled workflows after 60 days of repo inactivity.**
Any commit resets it. The weekly suggester commits its batch, so it also
resets the clock.

**`find_evergreen_candidates.py` globs `tweet*.js`.** In a real archive that
also matches `tweet-headers.js` (ids and timestamps only) and `tweetdeck.js`
(column config). Those entries have no `favorite_count`, so the likes
threshold drops them silently and the tool's output is unaffected. Anything
else reusing `load_tweets` needs its own guard; `rank.py` has one.

---

## Secrets

Set in repo Settings, never in code. Names only:

- `API_KEY`, `API_KEY_SECRET`, `ACCESS_TOKEN`, `ACCESS_TOKEN_SECRET` — X, OAuth 1.0a, do not expire
- `X_USER_ID` — optional, saves one API read per run
- `ANTHROPIC_API_KEY` — weekly suggester, `generate.py`
- `SLACK_WEBHOOK_URL` — weekly suggester, `notify_slack.py`. Incoming Webhook
  pointed at Arsen's own DM, same pattern as `relai-review-monitor` and
  `relai-aso-report`. A webhook's destination is fixed at creation

Never print, log or commit secret values.

---

## Costs

X API is pay per use. Roughly $0.02 per post, and posts containing a link
cost far more. Reads for the duplicate check add up. Current run rate is
about $2/month. Rates are only visible in the X Developer Console, not
published, so do not quote figures from memory.

The weekly suggester adds Anthropic API usage: two Sonnet calls a week, plus
a re-request round when suggestions get dropped. The voice skill is cached
across the calls in a run.

The visual suggester adds two more Sonnet calls a week, one for the concepts
and one for the sketches. Both skills are cached across the calls in a run.
The sketch call is the more expensive of the two on output tokens.

Published Sonnet rates are per million tokens and change, so check the current
rate rather than quoting one from memory.

---

## Compliance

Relai AG is VQF-regulated in Switzerland. Relai EU SASU holds MiCA CASP
authorization and is supervised by the AMF in France.

Anything posted from @relai_app is an external, EU-retail-facing marketing
communication under **MiCA Art. 66**, which requires it to be fair, clear and
not misleading. Forward-looking return or price projections engage
**EBA/GL/2024/11**.

**Rules for this repo:**

- Never add, edit or reword content in `evergreen.txt` or `fresh.txt` without
  being asked. The evergreen pool went through Compliance review as a specific
  list, and `fresh.txt` posts within two days with no further gate.
- **Standing approval for archive rewrites, decided by Arsen on 3 Sep 2026.**
  A suggestion that rewrites a tweet already published from @relai_app carries
  his approval as Marketing Lead, so `route.py` promotes it into `fresh.txt`
  automatically and it posts within two days. A net-new line has never been
  published and still waits for Guglielmo in `weekly-suggester/queued/`.
  This narrows the prior control; it does not remove it. Under **MiCA Art. 66**
  the rewrite path rests on the source line already having gone out from the
  account, so if that premise stops holding, the split stops being defensible.
- `route.py` re-runs `DROP_CHECKS` and `FLAG_CHECKS` on any line bound for
  `fresh.txt`. Copy is editable on the review board, so an edit can introduce
  a violation the batch never had. A line that trips a check is diverted to
  `queued/` with the reason recorded, never softened. Savings terminology
  always diverts: it needs written approval regardless of who wrote the line.
- `evergreen.txt` is manually mirrored into the sibling `relai-threads-bot`
  repo (its own pool, not a live fetch, so it can run independently once
  private). Any change here needs the same change brought over there too,
  or the pools drift. This already drifted once when the step was skipped.
- **Do not copy the full file over any more, as of 7 Sep 2026.** The Threads
  pool is a 214-line subset: nine ASCII and emoji art lines are excluded
  there because their shape depends on exact spacing and the Threads API
  does not round-trip whitespace, which broke a run on 6 Sep 2026. They
  post fine on X and stay here. A wholesale copy reintroduces them. Bring
  individual line additions over by hand instead. The two rotations are no
  longer in step and are not meant to be; `relai-threads-bot` has its own
  `SHUFFLE_SEED`. See that repo's CLAUDE.md under "Pool source".
- Flag regulatory exposure explicitly with the regulator and article. Flag it
  once, state the specific change needed, then move on. Do not repeat flags
  or add generic caution.
- Anything touching public copy is an advisory draft. Guglielmo in Compliance
  reviews before it goes live.
- New third-party services are ICT dependencies under **DORA** and need a
  register entry. Mention it once when introducing one.
- The weekly suggester produces advisory drafts only. It writes to
  `weekly-suggester/batches/` and `state/`, never to a file a posting bot
  reads. Every suggestion starts at `Compliance: unapproved` and the queue
  gate is how MiCA Art. 66 gets enforced. Do not remove either.
- **The visual suggester holds every flagged concept, with no rewrite path.**
  The 3 Sep 2026 standing approval narrows the copy control because the source
  line already went out from @relai_app. A visual concept has no such source:
  it is a new asset, so under **MiCA Art. 66** the flagged terms need written
  approval before it goes live, not after Paula has built it. A flagged
  concept stops in `visual-suggester/queued/` and Guglielmo sees it first.
  Do not extend the rewrite path to visuals; the premise it rests on is
  absent. `route.py` re-runs both check sets on the headline and caption
  first, because both are editable on the review board.
- Sending an unflagged concept to Paula's board is not publication. A Notion
  task is internal work, and what she builds is reviewed before it posts.
- Every visual concept carries a `needs_check` list: the figures, prices and
  dates a human must verify before the asset is built. Carry it into the
  brief. Marketing numbers come from Relai's own backtest tool or verified
  data and are never approximated, so a figure nobody sourced must not be set
  in artwork.
- `config.MOCK_PALETTE` is a placeholder, not Relai's brand palette. The
  sketches are indicative of composition only. Do not treat a sketch as a
  colour decision and do not send one to Paula.
- Suggestions using Savings, Sparen or Sparplan are auto-flagged and need
  written compliance approval before going live. The flag is not a
  resolution. A clean mechanical check is not approval either; the regex
  checks cover only the hard rules a pattern can decide.

---

## Testing

Every workflow has a `dry_run` input defaulting to true. Always dry run first.

A dry run exits before any API call, so it does **not** test authentication.
Only a live run does that.

The repo is public. Actions logs are public. Do not log anything sensitive.
