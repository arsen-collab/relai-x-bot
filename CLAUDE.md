# relai-x-bot

Marketing automation for Relai, a Swiss Bitcoin-only self-custody app.
Owner: Arsen Thagapsov, Marketing Lead. Timezone Europe/Zurich.

Posts to the official company X account @relai_app via GitHub Actions.

**Scope: X only.** This repo automates posts to @relai_app. It does not
cover App Store/Play Store review monitoring or any other non-X tooling.

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
| `post_evergreen.py` | `evergreen.yml` | Mondays | One line from `evergreen.txt`, 34-line rotation |

Both target 09:00-13:00 Europe/Zurich, hard cutoff 20:00.

### Offline tools

`find_evergreen_candidates.py`. Run manually against a downloaded X data
archive (zip, unzipped folder, or a direct tweet.js path). Lists standalone,
text-only tweets over a like threshold as CSV, sorted by likes. Feeds
candidates for the evergreen pool; does not touch `evergreen.txt` itself.
Takes no credentials, makes no API calls, not part of any workflow.

The raw X archive contains far more than public tweets (DMs, ad data). Never
commit it; `.gitignore` blocks the common patterns but treat that as a
backstop, not a guarantee.

### Shared module

`x_api.py`. Hand-rolled OAuth 1.0a HMAC-SHA1 signing, stdlib only.
Verified against X's documented test vector. Do not replace this with tweepy;
removing the pip install step was deliberate, it was a failure point.

---

## Architecture decisions, and why

**Four scheduled slots per posting day, any of which can post.**
Before posting, a run checks the account's recent posts for the exact text
and exits if found. GitHub runner acquisition fails often on this repo, so
one chance per day was not enough. Four independent chances, deduplicated by
reading the account rather than by keeping state.

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
Any commit resets it.

---

## Secrets

Set in repo Settings, never in code. Names only:

- `API_KEY`, `API_KEY_SECRET`, `ACCESS_TOKEN`, `ACCESS_TOKEN_SECRET` — X, OAuth 1.0a, do not expire
- `X_USER_ID` — optional, saves one API read per run

Never print, log or commit secret values.

---

## Costs

X API is pay per use. Roughly $0.02 per post, and posts containing a link
cost far more. Reads for the duplicate check add up. Current run rate is
about $2/month. Rates are only visible in the X Developer Console, not
published, so do not quote figures from memory.

---

## Compliance

Relai AG is VQF-regulated in Switzerland. Relai EU SASU holds MiCA CASP
authorization and is supervised by the AMF in France.

Anything posted from @relai_app is an external, EU-retail-facing marketing
communication under **MiCA Art. 66**, which requires it to be fair, clear and
not misleading. Forward-looking return or price projections engage
**EBA/GL/2024/11**.

**Rules for this repo:**

- Never add, edit or reword content in `evergreen.txt` without being asked.
  The pool went through Compliance review as a specific list.
- Flag regulatory exposure explicitly with the regulator and article. Flag it
  once, state the specific change needed, then move on. Do not repeat flags
  or add generic caution.
- Anything touching public copy is an advisory draft. Guglielmo in Compliance
  reviews before it goes live.
- New third-party services are ICT dependencies under **DORA** and need a
  register entry. Mention it once when introducing one.

---

## Testing

Every workflow has a `dry_run` input defaulting to true. Always dry run first.

A dry run exits before any API call, so it does **not** test authentication.
Only a live run does that.

The repo is public. Actions logs are public. Do not log anything sensitive.
