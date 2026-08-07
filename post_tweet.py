#!/usr/bin/env python3
"""
Relai X bot - daily market update.

Posts "<Weekday> market update:  1 BTC = 1 BTC" to @relai_app every day,
targeting 09:00-13:00 Europe/Zurich.

Reliability design:
  Four runs fire each day. Any of them can post. Before posting, a run
  checks the account's recent posts for today's exact text and exits if it
  is already there. So a run that fails to get a GitHub runner costs
  nothing, because the next slot picks it up.

  A run can never fire early, only late, so the script checks the real
  local clock. Anything up to 20:00 goes out. Past that the day is skipped,
  which keeps the weekday in the text matching the day it posts.
"""

import os
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import x_api

TZ = ZoneInfo("Europe/Zurich")

WINDOW_START_HOUR = 9
WINDOW_TARGET_END_HOUR = 13
HARD_CUTOFF_HOUR = 20

MAX_CHARS = 280

# Cron times must match .github/workflows/daily_tweet.yml.
# 08:00-11:00 UTC lands inside 09:00-13:00 Zurich in both CET and CEST.
# Deliberately off the hour: the top of the hour is GitHub's busiest moment.
SLOT_UTC_TIMES = {1: (8, 7), 2: (8, 53), 3: (9, 37), 4: (10, 23)}


def build_tweet(now):
    return f"{now.strftime('%A')} market update:\n\n1 BTC = 1 BTC"


def in_window(today, slot):
    """Whether this slot's scheduled time sits inside the target window."""
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

    if not in_window(today, slot):
        print("This slot falls outside the window today. Exiting.")
        return

    if not dry_run:
        if now.hour >= HARD_CUTOFF_HOUR:
            print(f"It is {now:%H:%M}, past the {HARD_CUTOFF_HOUR}:00 cutoff. Skipping.")
            return
        if now.hour < WINDOW_START_HOUR:
            print(f"Before {WINDOW_START_HOUR}:00 local. Too early. Exiting.")
            return
        if now.hour >= WINDOW_TARGET_END_HOUR:
            print(f"Note: {now:%H:%M} is past target window. Posting anyway.")

    tweet = build_tweet(now)

    if len(tweet) > MAX_CHARS:
        sys.exit(f"ERROR: tweet is {len(tweet)} chars, limit is {MAX_CHARS}.")

    print("---")
    print(tweet)
    print("---")

    if dry_run:
        print("DRY_RUN enabled. Nothing posted.")
        return

    creds = x_api.get_credentials()

    if x_api.already_posted(creds, tweet):
        print("Today's update is already on the account. Nothing to do.")
        return

    tweet_id = x_api.post(creds, tweet)
    if tweet_id:
        print(f"Posted: https://x.com/relai_app/status/{tweet_id}")


if __name__ == "__main__":
    main()
