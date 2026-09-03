#!/usr/bin/env python3
"""
Weekly X suggester - Slack notification.

Posts a pointer to the week's batch, not the batch itself. Fifteen suggestions
in a Slack message is unreadable and invites review in the wrong place. The
review happens in a chat session against the file.

stdlib only, same reason as the rest of this folder.

Posts through an Incoming Webhook, matching relai-review-monitor and
relai-aso-report. A webhook created against your own DM reaches the same place
a bot token would, with one secret instead of an app install and two scopes.

Env:
  SLACK_WEBHOOK_URL  Incoming Webhook. Its destination is fixed at creation.
  DRY_RUN            1/true/yes prints the message and exits without posting
  BATCH_WEEK         optional, YYYY-Www. Defaults to the current ISO week.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

sys.path.insert(0, HERE)
import config  # noqa: E402

BATCH_DIR = os.path.join(HERE, "batches")

TZ = ZoneInfo("Europe/Zurich")


def post_to_slack(webhook_url, text):
    request = urllib.request.Request(
        webhook_url,
        data=json.dumps({"text": text}).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()
    # The URL is the credential, so it must never reach a log line. Actions
    # logs on this repo are public.
    except urllib.error.HTTPError as exc:
        sys.exit(f"ERROR: Slack webhook returned HTTP {exc.code}.")
    except urllib.error.URLError as exc:
        sys.exit(f"ERROR: Slack unreachable: {exc.reason}")


def build_message(batch):
    week = batch["week"]
    suggestions = batch["suggestions"]
    counts = {}
    for suggestion in suggestions:
        counts[suggestion["type"]] = counts.get(suggestion["type"], 0) + 1
    by_type = ", ".join(f"{count} {kind}" for kind, count in sorted(counts.items()))

    lines = [
        f"*Week {int(week.split('-W')[1])} Content Ideas*",
        f"`{batch['batch_file']}`",
        "",
        f"{len(suggestions)} suggestions: {by_type}",
        f"Ranking basis: {batch['ranking_basis']}",
    ]
    if batch.get("dropped_count"):
        lines.append(f"{batch['dropped_count']} dropped before review, listed at the end of the file.")

    # Compliance flags stay in the batch file and in the JSON, not here. Slack
    # is a pointer, and a flag list in a notification invites the review to
    # happen in Slack instead of against the file.
    lines.append("")
    if config.REVIEW_URL:
        lines.append(f"Review board: {config.REVIEW_URL}")
        lines.append("Tick post, image or cut, edit any line in place, then hit Save decisions.")
    else:
        lines.append("Reply in a chat session to review: post, image or cut per line.")
    return "\n".join(lines)


def main():
    dry_run = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")

    week = os.environ.get("BATCH_WEEK")
    if not week:
        year, iso_week, _ = datetime.now(TZ).isocalendar()
        week = f"{year}-W{iso_week:02d}"

    batch_path = os.path.join(BATCH_DIR, f"{week}.json")
    if not os.path.exists(batch_path):
        print(f"No batch for {week} at {os.path.relpath(batch_path, REPO_ROOT)}. Nothing to notify.")
        return

    with open(batch_path, encoding="utf-8") as fh:
        batch = json.load(fh)

    message = build_message(batch)
    print("---")
    print(message)
    print("---")

    if dry_run:
        print("DRY_RUN enabled. Nothing posted.")
        return

    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        sys.exit("ERROR: SLACK_WEBHOOK_URL is not set.")

    post_to_slack(webhook_url, message)
    print("Posted to Slack.")


if __name__ == "__main__":
    main()
