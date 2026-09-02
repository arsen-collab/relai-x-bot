#!/usr/bin/env python3
"""
Weekly X suggester - Slack notification.

Posts a pointer to the week's batch, not the batch itself. Fifteen suggestions
in a Slack message is unreadable and invites review in the wrong place. The
review happens in a chat session against the file.

stdlib only, same reason as the rest of this folder.

Env:
  SLACK_BOT_TOKEN  bot token with chat:write (and im:write for a DM)
  DRY_RUN          1/true/yes prints the message and exits without posting
  BATCH_WEEK       optional, YYYY-Www. Defaults to the current ISO week.
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
SLACK_API = "https://slack.com/api/"


def slack_call(method, token, payload):
    request = urllib.request.Request(
        SLACK_API + method,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        sys.exit(f"ERROR: Slack {method} returned HTTP {exc.code}.")
    except urllib.error.URLError as exc:
        sys.exit(f"ERROR: Slack unreachable: {exc.reason}")

    # Slack reports its own failures inside a 200.
    if not body.get("ok"):
        sys.exit(f"ERROR: Slack {method} failed: {body.get('error', 'unknown')}")
    return body


def resolve_channel(destination, token):
    """A U... destination is a user, so open the DM first. Anything else is a channel id."""
    if destination.startswith("U"):
        return slack_call("conversations.open", token, {"users": destination})["channel"]["id"]
    return destination


def build_message(batch):
    week = batch["week"]
    suggestions = batch["suggestions"]
    counts = {}
    for suggestion in suggestions:
        counts[suggestion["type"]] = counts.get(suggestion["type"], 0) + 1
    by_type = ", ".join(f"{count} {kind}" for kind, count in sorted(counts.items()))

    lines = [
        f"*Week {int(week.split('-W')[1])} X suggestions* ({week})",
        f"`{batch['batch_file']}`",
        "",
        f"{len(suggestions)} suggestions: {by_type}",
        f"Ranking basis: {batch['ranking_basis']}",
    ]
    if batch.get("dropped_count"):
        lines.append(f"{batch['dropped_count']} dropped on a mechanical voice check, listed at the end of the file.")

    flagged = [s for s in suggestions if s["flags"]]
    lines.append("")
    if flagged:
        lines.append(f"*Compliance flags on {len(flagged)}:*")
        for suggestion in flagged:
            lines.append(f"• {suggestion['id']}: {', '.join(suggestion['flags'])}")
    else:
        lines.append("No compliance flags raised.")

    lines += [
        "",
        "All lines are at Compliance: unapproved. Nothing is postable yet.",
        "Reply in a chat session to review: tick copy, image or cut per line.",
    ]
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

    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        sys.exit("ERROR: SLACK_BOT_TOKEN is not set.")

    destination = config.SLACK_DESTINATION
    channel = resolve_channel(destination, token)
    slack_call("chat.postMessage", token, {
        "channel": channel,
        "text": message,
        "unfurl_links": False,
        "unfurl_media": False,
    })
    print(f"Posted to {destination}.")


if __name__ == "__main__":
    main()
