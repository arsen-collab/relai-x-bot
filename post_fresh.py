#!/usr/bin/env python3
"""
Relai X bot - fresh posts. The fast lane.

Posts the top line of fresh.txt, then removes it from the file and appends it
to fresh_posted.txt. A queue that drains, not a rotation. Approved copy goes
out within a day or two instead of waiting out the evergreen cycle, which at
224 lines every 2 days takes over a year to come round.

Why a separate file and not evergreen.txt:
  evergreen.txt is a fixed rotation that went through Compliance as a specific
  list, and it is mirrored line for line into relai-threads-bot. Dropping a new
  line into it reshuffles nothing but does change what the sibling repo must
  mirror, and the line would still wait months for its turn. This file is a
  different thing: a short queue, X only, emptied as it posts.

Scheduling:
  Runs on days evergreen does not, using the same EPOCH, so the two never
  post on the same day. A line approved today goes out within two days. The
  daily market update is unaffected and still posts every day.

Reliability design:
  Same as post_evergreen.py. Four slots a day, any of which can post, each
  checking the account for the exact text first. A slot that fails to get a
  runner costs nothing.

  The drain is the state. If the post succeeds but the commit does not, the
  next slot finds the line still queued, sees it already on the account, and
  drains it without posting again.
"""

import os
import subprocess
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import x_api

# Imported, not copied, so the two bots cannot drift into posting on the same
# day. is_posting_day is the whole coupling; everything else here is local.
from post_evergreen import (
    HARD_CUTOFF_HOUR,
    MAX_CHARS,
    WINDOW_START_HOUR,
    WINDOW_TARGET_END_HOUR,
    is_posting_day,
)

TZ = ZoneInfo("Europe/Zurich")
POOL_FILE = "fresh.txt"
POSTED_FILE = "fresh_posted.txt"

# Cron times must match .github/workflows/fresh.yml. Offset from evergreen's
# slots so the two bots never contend for a runner at the same minute.
SLOT_UTC_TIMES = {1: (8, 19), 2: (9, 11), 3: (9, 49), 4: (10, 41)}


def in_window(today, slot):
    """Local copy rather than post_evergreen's, because the slot times differ."""
    if slot == 0:
        return True
    h, m = SLOT_UTC_TIMES.get(slot, (0, 0))
    utc = datetime(today.year, today.month, today.day, h, m, tzinfo=timezone.utc)
    return WINDOW_START_HOUR <= utc.astimezone(TZ).hour < WINDOW_TARGET_END_HOUR


def is_comment(line):
    """"# " or a bare "#" is a comment. "#word" is a hashtag."""
    return line == "#" or line.startswith("# ")


def load_queue(path=POOL_FILE):
    """Returns (tweets, raw_lines). Raw lines are kept so the rewrite that
    drains the file preserves the header comments exactly."""
    if not os.path.exists(path):
        sys.exit(f"ERROR: {path} not found.")

    with open(path, encoding="utf-8") as fh:
        raw = fh.read().splitlines()

    tweets = [line.strip() for line in raw if line.strip() and not is_comment(line.strip())]

    seen = set()
    dupes = [t for t in tweets if t in seen or seen.add(t)]
    if dupes:
        sys.exit(f"ERROR: duplicate line in {path}: {dupes[0][:60]}...")

    long_ones = [t for t in tweets if len(t.replace("\\n", "\n")) > MAX_CHARS]
    if long_ones:
        sys.exit(f"ERROR: line over {MAX_CHARS} chars: {long_ones[0][:60]}...")

    return tweets, raw


def drain(tweet_raw, raw_lines, today):
    """Remove the posted line from fresh.txt and log it in fresh_posted.txt."""
    kept = []
    dropped = False
    for line in raw_lines:
        if not dropped and line.strip() == tweet_raw:
            dropped = True
            continue
        kept.append(line)

    with open(POOL_FILE, "w", encoding="utf-8") as fh:
        fh.write("\n".join(kept).rstrip("\n") + "\n")

    header = ""
    if not os.path.exists(POSTED_FILE):
        header = ("# Lines already posted from fresh.txt, newest last.\n"
                  "# A log, not a pool. Nothing reads this file.\n#\n")
    with open(POSTED_FILE, "a", encoding="utf-8") as fh:
        fh.write(f"{header}{today:%Y-%m-%d}  {tweet_raw}\n")


def commit_drain(tweet_raw):
    """Push the drained queue. A failure here is not fatal: the line is
    already posted, and the next run drains it after the already_posted check."""
    try:
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
        subprocess.run(["git", "config", "user.email",
                        "41898282+github-actions[bot]@users.noreply.github.com"], check=True)
        subprocess.run(["git", "add", POOL_FILE, POSTED_FILE], check=True)
        subprocess.run(["git", "commit", "-m",
                        f"Post from fresh queue: {tweet_raw[:50]}"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("Queue drained and pushed.")
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"WARNING: could not push the drained queue: {exc}")
        print("The line is posted. The next run will drain it.")


def main():
    dry_run = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")
    slot = int(os.environ.get("SLOT", "0"))

    now = datetime.now(TZ)
    today = now.date()

    print(f"Now: {now:%Y-%m-%d %H:%M %Z} ({now:%A}) | slot {slot}")

    # Evergreen owns its days. This bot takes the ones in between, so the two
    # never post on the same day.
    if is_posting_day(today) and slot != 0:
        print("Evergreen posts today. Exiting.")
        return

    if not in_window(today, slot):
        print("This slot falls outside the window today. Exiting.")
        return

    tweets, raw_lines = load_queue()
    if not tweets:
        print("Fresh queue is empty. Nothing to post.")
        return

    tweet_raw = tweets[0]
    tweet = tweet_raw.replace("\\n", "\n")

    print(f"Queue: {len(tweets)} waiting")
    print("---")
    print(tweet)
    print("---")

    if dry_run:
        print("DRY_RUN enabled. Nothing posted, queue untouched.")
        return

    if now.hour >= HARD_CUTOFF_HOUR:
        print(f"It is {now:%H:%M}, past the {HARD_CUTOFF_HOUR}:00 cutoff. Skipping.")
        return
    if now.hour >= WINDOW_TARGET_END_HOUR:
        print(f"Note: {now:%H:%M} is past target window. Posting anyway.")

    creds = x_api.get_credentials()

    if x_api.already_posted(creds, tweet):
        print("Already on the account. Draining without posting.")
        drain(tweet_raw, raw_lines, today)
        commit_drain(tweet_raw)
        return

    tweet_id = x_api.post(creds, tweet)
    if not tweet_id:
        print("Post failed. Queue left untouched, the next slot retries.")
        return

    print(f"Posted: https://x.com/relai_app/status/{tweet_id}")
    drain(tweet_raw, raw_lines, today)
    commit_drain(tweet_raw)


if __name__ == "__main__":
    main()
