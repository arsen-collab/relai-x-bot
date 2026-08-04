#!/usr/bin/env python3
"""
Relai X bot - daily market update.

Posts "<Weekday> market update:  1 BTC = 1 BTC" to @relai_app once a day,
at a random-ish time between 11:00 and 13:00 Europe/Zurich.

Four scheduled runs fire inside that window. Each gets a SLOT number (1-4).
The script picks one winner per day from the date, so exactly one run posts
and the other three exit immediately. SLOT 0 means a human triggered the run
manually, which always posts.
"""

import os
import sys
import random
from datetime import datetime
from zoneinfo import ZoneInfo

import tweepy

TZ = ZoneInfo("Europe/Zurich")
TOTAL_SLOTS = 4


def get_credentials():
    keys = ["API_KEY", "API_KEY_SECRET", "ACCESS_TOKEN", "ACCESS_TOKEN_SECRET"]
    creds = {}
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        sys.exit(f"ERROR: missing variables: {', '.join(missing)}")
    for k in keys:
        creds[k] = os.environ[k]
    return creds


def build_tweet(now):
    return f"{now.strftime('%A')} market update:\n\n1 BTC = 1 BTC"


def winning_slot(now):
    """Deterministic per-day pick. Same result for every run that day."""
    rng = random.Random(now.strftime("%Y-%m-%d"))
    return rng.randint(1, TOTAL_SLOTS)


def main():
    dry_run = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")
    slot = int(os.environ.get("SLOT", "0"))

    now = datetime.now(TZ)
    winner = winning_slot(now)

    print(f"Now: {now:%Y-%m-%d %H:%M %Z} | slot {slot} | today's slot {winner}")

    if slot != 0 and slot != winner and not dry_run:
        print("Not today's slot. Exiting.")
        return

    creds = get_credentials()
    tweet = build_tweet(now)

    print("---")
    print(tweet)
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

    response = client.create_tweet(text=tweet)
    print(f"Posted: https://x.com/relai_app/status/{response.data.get('id')}")


if __name__ == "__main__":
    main()
