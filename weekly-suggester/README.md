# Weekly X suggester

Drafts 15 X suggestions a week from Relai's own archive, in Relai voice, for
Arsen to review. Output is an advisory draft. Nothing here posts anything.

## The hard boundary

This tool writes to `batches/` and `state/` and nowhere else. It never touches
`evergreen.txt` or anything `post_tweet.py` and `post_evergreen.py` read.
Promoting a line into the live pool is a separate manual decision, taken after
Compliance signs off. Every suggestion is written out at
`Compliance: unapproved`, and nothing moves to a posting queue with that unset.

## Pieces

| File | When it runs | What it does |
|---|---|---|
| `rank.py` | Manually, when a new archive is downloaded | Filters and scores the archive into `state/pool.json`. Pure Python, no model calls, no network. |
| `generate.py` | Weekly, in Actions | Reads `pool.json`, drafts the batch with Claude, writes `batches/YYYY-Www.{md,json}` |
| `notify_slack.py` | Weekly, after generate | Posts a pointer to the batch, not the batch |
| `config.py` | Never | Every tunable: filters, counts, model, patterns |

`.github/workflows/weekly_suggester.yml` runs generate then notify, Monday
morning, and commits the batch back.

## Why ranking is offline

The brief had `rank.py` running weekly in the Action. It cannot: the archive is
~105 MB, contains DMs and ad data, and is gitignored, so the runner never sees
it. Ranking is a manual step whose output is committed.

This costs nothing. The archive does not change between weeks, so re-sorting it
on a schedule was always waste. `pool.json` holds the full eligible set rather
than a fixed top 40, so the weekly run still has fresh material after months of
used ids piling up.

## Running the ranking

```bash
python3 weekly-suggester/rank.py ~/Downloads/twitter-2026-08-08-<hash>/data --show
```

Accepts the zip X sends you, the unzipped folder, or a direct `tweets.js` path.
Then commit `state/pool.json`.

Never commit the archive itself. `.gitignore` blocks the common patterns but
treat that as a backstop, not a guarantee.

## Tuning the filters

`--show` prints the head of the shortlist plus two examples of what each rule
dropped. That is the tuning loop: run it, find a rule catching the wrong thing,
edit `config.py`, run again.

The pattern lists are a starting point, not a finished job. Two things they are
fighting:

- **The archive's best performers skew towards rules that did not exist yet.**
  Ranking by likes surfaces other cryptocurrencies, forward-looking price
  claims and politician references, because those got engagement. The
  hard-rule checks run at rank time as well as on the output, because a tweet
  whose *idea* is the violation cannot be rewritten into compliance while
  keeping the idea.
- **Likes also reward things that do not survive a rewrite.** Thread openers
  whose payoff is in the replies, audience questions, ASCII art, hashtag spam,
  test posts. `NOT_STANDALONE` and the structural checks in `rank.py` handle
  those.

Expect to loosen a rule occasionally. One already known: the `crypto` drop
catches contrastive lines like "Bitcoin is not crypto", which are on-message.
That is a deliberately conservative call, and there is plenty of pool left.

## Ranking basis

`likes + (2 * reposts)`, halved every 18 months of age, decayed against the
newest tweet in the archive rather than today so the same archive always
produces the same `pool.json`.

This is a **weak proxy** and the batch header says so. It is engagement volume,
not engagement rate. If `archive/analytics.csv` ever exists with impression
data, switch to engagements divided by impressions and drop the caveat.
`rank.py` notices the file and prints a reminder; it does not read it yet.

## The mechanical checks are a net, not approval

`DROP_CHECKS` in `config.py` covers the hard rules a regex can decide: em
dashes, other cryptocurrencies, forward-looking price framing, yield claims,
named-competitor comparisons. A suggestion matching one is dropped and
re-requested, never softened, and the drop is listed at the end of the batch
file so a false positive stays visible.

Judgment rules are not mechanically checkable: whether a line reads as advice,
whether a claim is verified, tone, political association. Those rely on the
model's self-check against the skill and on the human review that follows. A
clean check is not compliance approval.

`FLAG_CHECKS` is the softer half: terms that need written compliance approval
before going live, added to a suggestion's `flags` array rather than dropping
it. Savings terminology is the main one.

## Review and routing

Not automated. Arsen opens a chat, reads the batch file, ticks one box per
line, and then:

- **copy**: moves to `queued/YYYY-Www.md`, still `Compliance: unapproved`. It
  sits there until Guglielmo signs off. Nothing posts automatically.
- **image**: the `design-brief-creator` skill drafts a brief and creates the
  Notion task on Paula's board, then returns the URL. The Notion Platform field
  has no X option, so X-sourced content goes in as IG plus whatever else Arsen
  picks, and the brief notes where the copy came from.
- **cut**: id goes to `state/rejected.json` so it never comes back.

`state/used.json` records only ids used as *rewrite sources*. Ids shown to the
model as voice reference stay available, otherwise the strongest tweets in the
archive would be spent as reference material inside a month.

## Secrets

Repo Settings, names only:

- `ANTHROPIC_API_KEY` for `generate.py`
- `SLACK_WEBHOOK_URL` for `notify_slack.py`. Incoming Webhook, same pattern as
  `relai-review-monitor` and `relai-aso-report`. Point it at your own DM when
  creating it; the destination is fixed then and cannot be changed after.

A bot token would also work and would allow choosing the destination at post
time, but that needs an app install and two scopes to reach the same DM. One
secret beats three moving parts.

The repo is public and so are Actions logs. Nothing here prints a secret. The
webhook URL is itself the credential, so it must stay out of error messages.

## Testing

Both workflow steps take `dry_run`, defaulting to true. A dry run does all the
local work and exits before the API call, so it does **not** test the Anthropic
key or the Slack token. Only a live run does that.

## Python

stdlib only, no pip install step, matching the rest of the repo. Runs on the
system Python 3.9 on a Mac and on the runner's 3.12. That is why `config.py` is
a Python module rather than YAML or TOML: PyYAML needs a pip install and
`tomllib` only exists from 3.11.
