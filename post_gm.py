#!/usr/bin/env python3
"""
Relai X bot - daily GM post.

Posts a fixed line to @relai_app once a day, at a random-ish time
between 09:00 and 10:00 Europe/Zurich.

The window is only one hour wide and DST shifts by one hour, so no fixed
UTC cron lands inside it year round. Four runs fire across 07:00-09:00 UTC;
the script works out which of them actually fall inside the local window
today, then picks one winner among those. The rest exit immediately.

SLOT 0 means a human triggered the run manually, which always posts.
"""

import os
import sys
import random
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import tweepy

TZ = ZoneInfo("Europe/Zurich")

TWEET_TEXT = "GM stay humble and stack sats 🫡"

WINDOW_START_HOUR = 9
WINDOW_END_HOUR = 10

# Must match the cron entries in .github/workflows/gm_tweet.yml
SLOT_UTC_TIMES = {1: (7, 5), 2: (7, 35), 3: (8, 5), 4: (8, 35)}


def get_credentials():
    keys = ["API_KEY", "API_KEY_SECRET", "ACCESS_TOKEN", "ACCESS_TOKEN_SECRET"]
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        sys.exit(f"ERROR: missing variables: {', '.join(missing)}")
    return {k: os.environ[k] for k in keys}


def valid_slots(today):
    """Which slots land inside the local window on this date."""
    valid = []
    for slot, (h, m) in SLOT_UTC_TIMES.items():
        utc = datetime(today.year, today.month, today.day, h, m, tzinfo=timezone.utc)
        local = utc.astimezone(TZ)
        if WINDOW_START_HOUR <= local.hour < WINDOW_END_HOUR:
            valid.append(slot)
    return valid


def winning_slot(today, candidates):
    """Deterministic per-day pick. Same result for every run that day."""
    if not candidates:
        return None
    rng = random.Random(today.strftime("%Y-%m-%d") + "gm")
    return rng.choice(candidates)


def main():
    dry_run = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")
    slot = int(os.environ.get("SLOT", "0"))

    now = datetime.now(TZ)
    candidates = valid_slots(now)
    winner = winning_slot(now, candidates)

    print(f"Now: {now:%Y-%m-%d %H:%M %Z}")
    print(f"Slot {slot} | valid slots today {candidates} | winner {winner}")

    if slot != 0:
        if slot not in candidates:
            print("This slot falls outside the local window today. Exiting.")
            return
        if slot != winner and not dry_run:
            print("Not today's slot. Exiting.")
            return

    creds = get_credentials()

    print("---")
    print(TWEET_TEXT)
    print("---")

    if dry_run:
        print("DRY_RUN enabled. Nothing posted.")
        return

    client = tweepy.Client(
        consumer_key=creds["API_KEY"],
        consumer_secret=creds["API_KEY_SECRET"],
        access_token=creds["ACCESS_TOKEN"],
        access_token_secret=creds["ACCESS_TOKEN_SECRET"],
    )

    response = client.create_tweet(text=TWEET_TEXT)
    print(f"Posted: https://x.com/relai_app/status/{response.data.get('id')}")


if __name__ == "__main__":
    main()
