#!/usr/bin/env python3
"""
Relai X bot - evergreen posts.

Posts one line from evergreen.txt every Monday, targeting 09:00-13:00
Europe/Zurich.

Timing policy:
  This content is not time sensitive, so a late post is better than no
  post. The guard is deliberately loose: anything up to 20:00 local goes
  out, which absorbs roughly 7 to 11 hours of GitHub cron delay depending
  on slot and season. Only a delay past 20:00 skips the day, to avoid
  posting in the middle of the night.

Rotation:
  The pool is shuffled once with a fixed seed then walked in strict order,
  so every line posts once before any repeats. With N lines posting weekly,
  the same line returns every N weeks.

SLOT 0 means a human triggered the run manually, which bypasses the slot
pick but still respects the 20:00 cutoff.
"""

import os
import sys
import random
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import tweepy

TZ = ZoneInfo("Europe/Zurich")
POOL_FILE = "evergreen.txt"

# Target window, and the cutoff after which the day is skipped.
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
# 08:00-11:00 UTC lands inside 09:00-13:00 Zurich in both CET and CEST.
SLOT_UTC_TIMES = {1: (8, 10), 2: (9, 0), 3: (9, 50), 4: (10, 40)}

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


def valid_slots(today):
    """Which slots land inside the target window on this date."""
    valid = []
    for slot, (h, m) in SLOT_UTC_TIMES.items():
        utc = datetime(today.year, today.month, today.day, h, m, tzinfo=timezone.utc)
        if WINDOW_START_HOUR <= utc.astimezone(TZ).hour < WINDOW_TARGET_END_HOUR:
            valid.append(slot)
    return valid


def winning_slot(today, candidates):
    if not candidates:
        return None
    return random.Random(today.strftime("%Y-%m-%d") + "eg").choice(candidates)


def get_credentials():
    keys = ["API_KEY", "API_KEY_SECRET", "ACCESS_TOKEN", "ACCESS_TOKEN_SECRET"]
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        sys.exit(f"ERROR: missing variables: {', '.join(missing)}")
    return {k: os.environ[k] for k in keys}


def main():
    dry_run = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")
    slot = int(os.environ.get("SLOT", "0"))

    now = datetime.now(TZ)
    today = now.date()
    candidates = valid_slots(today)
    winner = winning_slot(today, candidates)

    print(f"Now: {now:%Y-%m-%d %H:%M %Z} ({now:%A})")
    print(f"Slot {slot} | valid slots today {candidates} | winner {winner}")

    if today.weekday() not in POSTING_WEEKDAYS and slot != 0:
        print("Not a posting day. Exiting.")
        return

    if not dry_run:
        if now.hour >= HARD_CUTOFF_HOUR:
            print(
                f"It is {now:%H:%M} local, past the {HARD_CUTOFF_HOUR}:00 cutoff. "
                "Skipping rather than posting overnight."
            )
            return
        if now.hour >= WINDOW_TARGET_END_HOUR:
            print(f"Note: {now:%H:%M} is past target window. Posting anyway.")

    if slot != 0:
        if slot not in candidates:
            print("This slot falls outside the window today. Exiting.")
            return
        if slot != winner and not dry_run:
            print("Not today's slot. Exiting.")
            return

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

    creds = get_credentials()
    client = tweepy.Client(
        consumer_key=creds["API_KEY"],
        consumer_secret=creds["API_KEY_SECRET"],
        access_token=creds["ACCESS_TOKEN"],
        access_token_secret=creds["ACCESS_TOKEN_SECRET"],
    )

    response = client.create_tweet(text=tweet)
    print(f"Posted: https://x.com/relai_app/status/{response.data.get('id')}")


if __name__ == "__main__":
    main()
