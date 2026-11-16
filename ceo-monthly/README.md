# CEO monthly bot

One text tweet a month on Julian's personal X account, never on @relai_app:

> Relai holds more Bitcoin than @Apple

Each month uses the next active company in the list, starting over at the
top after the last one. There is no per-post approval: it posts on schedule,
and Arsen monitors the account weekly.

Workflow: `.github/workflows/ceo_monthly.yml`. Every setting is in
`config.py`.

## Change the company list

Edit `COMPANIES` in `config.py`. Each entry has a name, an X handle with the
`@`, and an `active` flag. Order matters.

- Set `active` to `False` to skip a company. The next active one takes its
  turn.
- **Any change re-maps every future month, not just the next one.** The
  company due is "months since start, modulo active companies", so adding,
  removing or toggling an entry shifts the rest. Run the preview before and
  after the change.
- After changing a handle, run `verify_handles` (see below).

## Change the wording

Edit `TEMPLATE` in `config.py`. `{handle}` becomes the company's handle and
`{name}` the company name. Example: `"Relai users hold more Bitcoin than {handle}"`.

Compliance owns this wording. There is no approval step, so an edit here
posts as written on the next post date. Get the new wording signed off first.

## Change the date or time

`POST_WEEKDAY` (0 is Monday, so 1 is Tuesday), `POST_WEEK` (1 to 4),
`POST_HOUR`, `POST_MINUTE`, all Europe/Zurich. Daylight saving is handled.

The workflow only runs at four fixed times a day, set up so that one lands
at 13:58 Zurich in both winter and summer. **If you move the time, the cron
lines in the workflow have to move too.** The preview prints a warning on any
month where no run lands within an hour after the post time.

`START_YEAR` / `START_MONTH` anchor the rotation. Changing them re-times
everything.

## Heads-up and stopping a post

1. **3 days before the post date** you get a Slack DM with the exact tweet,
   the company, the date and time, and the BitcoinTreasuries link. No action
   needed.
2. **On the post date from 13:58 Zurich** it posts, and you get a Slack
   message with the link.
3. **No run got through before 20:00** (GitHub's scheduler runs late on this
   repo): nothing posts, and the Slack message tells you to use `post_now`.

**To stop a post:** GitHub, Actions, *CEO Monthly Tweet*, the `...` menu,
*Disable workflow*. Do it before 13:58 on the post day, and enable it again
afterwards. Disabling skips that month; it does not shift the rotation.

**To drop a company for good:** set `active` to `False` in `config.py`. That
does re-map the following months, see above.

The approval step was removed on 16 Nov 2026 at Arsen's request, after
Compliance signed off the wording.

## Workflow actions

All default to dry run. A dry run makes no API call, sends nothing and
commits nothing.

| Action | Month | What it does |
|---|---|---|
| `preview` | optional start | Next 15 months: date, company, tweet, posted or scheduled |
| `post_now` | required | Posts that month's tweet now, whatever the time. Skips if already posted |
| `verify_handles` | none | Looks every handle up on X and prints its display name and badge. Uses @relai_app's token, one read |
| `run` | none | What the schedule does, on demand |

Locally, from the repo root (dry run is on unless `DRY_RUN=false`):

```bash
python3 ceo-monthly/post_monthly.py preview
```

## Double posting

Checked in this order before every post:

1. `posted.txt` has a line for the month: stop.
2. The exact text is in Julian's last 20 posts: log it, don't post.
3. X itself rejects an identical post.

`notices.txt` does the same for Slack, so four daily runs send one message,
not four.

## Secrets

In repo Settings, Secrets and variables, Actions:

| Name | What |
|---|---|
| `CEO_ACCESS_TOKEN` | Julian's access token |
| `CEO_ACCESS_TOKEN_SECRET` | Julian's access token secret |
| `CEO_X_USER_ID` | Julian's X user id. Optional, saves one read per post |

Reused as they are: `API_KEY`, `API_KEY_SECRET` (Relai's X app) and
`SLACK_WEBHOOK_URL`.

To create the three, run this locally. Julian opens the printed link while
logged in, clicks Authorize app and sends you the PIN. The script writes the
secrets directly; nothing is printed or pasted anywhere.

```bash
python3 scripts/x_authorize_account.py arsen-collab/relai-x-bot --prefix CEO_
```

**Always pass `--prefix CEO_` for this repo.** Without it the script writes
`ACCESS_TOKEN`, which is @relai_app's.

If the CEO secrets are ever set to @relai_app's token by mistake, the run
stops before posting.

## Tests

```bash
cd ceo-monthly && python3 -m unittest -v test_post_monthly
```
