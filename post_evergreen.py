#!/usr/bin/env python3
"""
Relai X bot - evergreen posts.

Posts one line from evergreen.txt every Monday, targeting 09:00-13:00
Europe/Zurich.

Reliability design:
  Four runs fire each Monday. Any of them can post. Before posting, a run
  checks the account's recent posts for this week's exact line and exits if
  it is already there. So a run that fails to get a GitHub runner costs
  nothing, because the next slot picks it up.

  This content is not time sensitive, so a late post beats a missed one.
  Anything up to 20:00 local goes out. Only past 20:00 is the day skipped,
  to avoid posting overnight.

Rotation:
  The pool is shuffled once with a fixed seed then walked in strict order,
  so every line posts once before any repeats. With N lines posting weekly,
  the same line returns every N weeks.
"""

import os
import sys
import random
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import x_api

TZ = ZoneInfo("Europe/Zurich")
POOL_FILE = "evergreen.txt"

WINDOW_START_HOUR = 9
WINDOW_TARGET_END_HOUR = 13
HARD_CUTOFF_HOUR = 20

# Monday is 0.
POSTING_WEEKDAYS = {0}

# Fixed reference point. Do not change once live, it anchors the rotation.
EPOCH = date(2026, 1, 1)

MAX_CHARS = 280
MIN_POOL_SIZE = 4

# Cron times must match .github/workflows/evergreen.yml.
# Deliberately off the hour: the top of the hour is GitHub's busiest moment.
SLOT_UTC_TIMES = {1: (8, 7), 2: (8, 53), 3: (9, 37), 4: (10, 23)}

SHUFFLE_SEED = "relai-evergreen-v1"


def load_pool(path=POOL_FILE):
    if not os.path.exists(path):
        sys.exit(f"ERROR: {path} not found.")

    lines = []
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            # "# " or a bare "#" is a comment. "#word" is a hashtag.
            if not line or line == "#" or line.startswith("# "):
                continue
            lines.append(line.replace("\\n", "\n"))

    if not lines:
        sys.exit(f"ERROR: {path} contains no tweets.")

    seen = set()
    dupes = [t for t in lines if t in seen or seen.add(t)]
    if dupes:
        sys.exit(f"ERROR: duplicate line in {path}: {dupes[0][:60]}...")

    long_ones = [t for t in lines if len(t) > MAX_CHARS]
    if long_ones:
        sys.exit(f"ERROR: line over {MAX_CHARS} chars: {long_ones[0][:60]}...")

    if len(lines) < MIN_POOL_SIZE:
        sys.exit(f"ERROR: pool has {len(lines)} lines, need at least {MIN_POOL_SIZE}.")

    return lines


def post_index(today):
    """How many posting days have elapsed since EPOCH, excluding today."""
    if today < EPOCH:
        sys.exit("ERROR: current date is before EPOCH.")
    count = 0
    cursor = EPOCH
    while cursor < today:
        if cursor.weekday() in POSTING_WEEKDAYS:
            count += 1
        cursor = date.fromordinal(cursor.toordinal() + 1)
    return count


def pick_tweet(pool, today):
    order = list(pool)
    random.Random(SHUFFLE_SEED).shuffle(order)
    return order[post_index(today) % len(order)]


def in_window(today, slot):
    if slot == 0:
        return True
    h, m = SLOT_UTC_TIMES.get(slot, (0, 0))
    utc = datetime(today.year, today.month, today.day, h, m, tzinfo=timezone.utc)
    return WINDOW_START_HOUR <= utc.astimezone(TZ).hour < WINDOW_TARGET_END_HOUR


def main():
    dry_run = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")
    slot = int(os.environ.get("SLOT", "0"))

    now = datetime.now(TZ)
    today = now.date()

    print(f"Now: {now:%Y-%m-%d %H:%M %Z} ({now:%A}) | slot {slot}")

    if today.weekday() not in POSTING_WEEKDAYS and slot != 0:
        print("Not a posting day. Exiting.")
        return

    if not in_window(today, slot):
        print("This slot falls outside the window today. Exiting.")
        return

    if not dry_run:
        if now.hour >= HARD_CUTOFF_HOUR:
            print(f"It is {now:%H:%M}, past the {HARD_CUTOFF_HOUR}:00 cutoff. Skipping.")
            return
        if now.hour >= WINDOW_TARGET_END_HOUR:
            print(f"Note: {now:%H:%M} is past target window. Posting anyway.")

    pool = load_pool()
    tweet = pick_tweet(pool, today)

    print(f"Pool: {len(pool)} lines | index {post_index(today) % len(pool)}")
    print(f"Repeat gap: {len(pool)} weeks")
    print("---")
    print(tweet)
    print("---")

    if dry_run:
        print("DRY_RUN enabled. Nothing posted.")
        return

    creds = x_api.get_credentials()

    if x_api.already_posted(creds, tweet):
        print("This week's post is already on the account. Nothing to do.")
        return

    tweet_id = x_api.post(creds, tweet)
    if tweet_id:
        print(f"Posted: https://x.com/relai_app/status/{tweet_id}")


if __name__ == "__main__":
    main()
