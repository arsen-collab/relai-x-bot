#!/usr/bin/env python3
"""
Relai X bot - daily market update.

Posts "<Weekday> market update:  1 BTC = 1 BTC" to @relai_app every day,
targeting 09:00-13:00 Europe/Zurich.

Timing policy:
  GitHub cron is best effort and can be delayed by hours. A delayed run
  can never fire early, only late, so this script checks the real local
  clock before posting. Anything up to 20:00 local goes out, which absorbs
  roughly 7 to 11 hours of delay depending on slot and season. Past 20:00
  the day is skipped, which also guarantees the weekday in the text always
  matches the day it actually posts.

  Note: extra slots do not buy more headroom. Only one slot per day is the
  winner; the rest exit. Headroom comes from firing early and cutting off
  late, which is why all four slots sit at the start of the window.

SLOT 0 means a human triggered the run manually, which bypasses the slot
pick but still respects the 20:00 cutoff.
"""

import os
import sys
import random
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import tweepy

TZ = ZoneInfo("Europe/Zurich")

# Target window, and the cutoff after which the day is skipped.
WINDOW_START_HOUR = 9
WINDOW_TARGET_END_HOUR = 13
HARD_CUTOFF_HOUR = 20

MAX_CHARS = 280

# Cron times must match .github/workflows/daily_tweet.yml.
# 08:00-11:00 UTC lands inside 09:00-13:00 Zurich in both CET and CEST.
SLOT_UTC_TIMES = {1: (8, 10), 2: (9, 0), 3: (9, 50), 4: (10, 40)}


def get_credentials():
    keys = ["API_KEY", "API_KEY_SECRET", "ACCESS_TOKEN", "ACCESS_TOKEN_SECRET"]
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        sys.exit(f"ERROR: missing variables: {', '.join(missing)}")
    return {k: os.environ[k] for k in keys}


def build_tweet(now):
    return f"{now.strftime('%A')} market update:\n\n1 BTC = 1 BTC"


def valid_slots(today):
    """Which slots land inside the target window on this date."""
    valid = []
    for slot, (h, m) in SLOT_UTC_TIMES.items():
        utc = datetime(today.year, today.month, today.day, h, m, tzinfo=timezone.utc)
        if WINDOW_START_HOUR <= utc.astimezone(TZ).hour < WINDOW_TARGET_END_HOUR:
            valid.append(slot)
    return valid


def winning_slot(today, candidates):
    """Deterministic per-day pick. Same result for every run that day."""
    if not candidates:
        return None
    return random.Random(today.strftime("%Y-%m-%d") + "mkt").choice(candidates)


def main():
    dry_run = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")
    slot = int(os.environ.get("SLOT", "0"))

    now = datetime.now(TZ)
    today = now.date()
    candidates = valid_slots(today)
    winner = winning_slot(today, candidates)

    print(f"Now: {now:%Y-%m-%d %H:%M %Z} ({now:%A})")
    print(f"Slot {slot} | valid slots today {candidates} | winner {winner}")

    if not dry_run:
        if now.hour >= HARD_CUTOFF_HOUR:
            print(
                f"It is {now:%H:%M} local, past the {HARD_CUTOFF_HOUR}:00 cutoff. "
                "Skipping today rather than posting overnight."
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

    tweet = build_tweet(now)

    if len(tweet) > MAX_CHARS:
        sys.exit(f"ERROR: tweet is {len(tweet)} chars, limit is {MAX_CHARS}.")

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
