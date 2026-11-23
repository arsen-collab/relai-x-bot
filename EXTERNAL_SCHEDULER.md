# External scheduler (cron-job.org)

**Optional as of 23 Nov 2026.** The Claude scheduled task `trigger-x-posting`
already dispatches `external_trigger.yml` at 09:07 and 10:07 Zurich while the
Claude app is open. cron-job.org is the upgrade for weekends and days the
laptop is closed.

GitHub cron starts this repo's scheduled runs about 8 hours late. In November
2026 every evergreen, fresh and market-update post went out 17:00-19:00
Zurich instead of 09:00-13:00, and the fourth slot regularly hit the 20:00
cutoff. A `workflow_dispatch` starts in seconds, so cron-job.org now calls
`.github/workflows/external_trigger.yml` four times a day. That workflow
dispatches evergreen, fresh and (Tuesday and Friday only) the market update
with the slot number. The GitHub cron lines stay as a backup; a late backup
run finds the day already done and exits.

The CEO monthly bot is not on this yet. It posts once a month at 13:58 and
its own cron lines are untouched.

## 1. GitHub token (Arsen, about 3 minutes)

GitHub, Settings, Developer settings, Personal access tokens, Fine-grained
tokens, Generate new token.

- Name: `cron-job.org relai-x-bot trigger`
- Expiration: the longest allowed. Put the expiry date in your calendar a week
  early; when it lapses, posting silently falls back to the late GitHub cron.
- Resource owner: `arsen-collab`
- Repository access: Only select repositories, `relai-x-bot`
- Permissions: Repository permissions, **Actions: Read and write**. Nothing
  else (Metadata read-only is added automatically).

Copy the token straight into cron-job.org in step 2. Never paste it into
Claude, Slack, a file in this repo or a commit. If it leaks, revoke it in the
same GitHub screen.

## 2. cron-job.org jobs (four, identical except slot and time)

Create an account at cron-job.org. Then Create cronjob, four times:

| Job title | Time (Europe/Zurich) | Body |
|---|---|---|
| relai-x slot 1 | 09:07 every day | `{"ref":"main","inputs":{"slot":"1","dry_run":"false"}}` |
| relai-x slot 2 | 09:53 every day | `{"ref":"main","inputs":{"slot":"2","dry_run":"false"}}` |
| relai-x slot 3 | 10:37 every day | `{"ref":"main","inputs":{"slot":"3","dry_run":"false"}}` |
| relai-x slot 4 | 11:23 every day | `{"ref":"main","inputs":{"slot":"4","dry_run":"false"}}` |

Same for all four:

- URL:
  `https://api.github.com/repos/arsen-collab/relai-x-bot/actions/workflows/external_trigger.yml/dispatches`
- Schedule: custom, every day, at the time above. Set the job timezone to
  **Europe/Zurich** so DST is handled for you.
- Advanced, Request method: **POST**
- Advanced, Headers:
  - `Accept: application/vnd.github+json`
  - `Authorization: Bearer <the token from step 1>`
  - `X-GitHub-Api-Version: 2022-11-28`
  - `Content-Type: application/json`
- Advanced, Request body: the JSON from the table.
- Notifications: email on failure, and when the job is disabled after
  repeated failures.

Use "Test run" on slot 1 first. A good response is **HTTP 204** with an
empty body, and a new "External Trigger" run appears under Actions. 401 or
403 means the token or its permission is wrong; 422 means the body is off.

To test without posting, use the same request with `"dry_run":"true"`.

## How it behaves

- Evergreen and fresh still split the days between them and still check the
  account (evergreen) or `fresh_posted.txt` (fresh) before posting, so four
  slots never post four times.
- Slot times only need to sit inside 09:00-13:00 Zurich. The window check in
  the scripts uses each slot's fixed UTC time, which is inside the window in
  both CET and CEST.
- To pause all posting: disable the four jobs in cron-job.org **and** disable
  the posting workflows in GitHub Actions (the backup cron would otherwise
  still post, late).

## Compliance

cron-job.org is a new third-party ICT service under **DORA**. It holds a token
that can start workflows in this repo, and through them post to @relai_app.
It needs a register entry.
