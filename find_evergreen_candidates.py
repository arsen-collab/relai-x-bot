#!/usr/bin/env python3
"""
Relai X bot - evergreen candidate finder.

Scans an X (Twitter) personal data archive for @relai_app and lists
standalone text tweets over a like threshold, as raw material for
evergreen.txt. This script only produces a CSV to review. It never
touches evergreen.txt itself.

A candidate tweet is:
  - over --min-likes likes (default 100)
  - text only: no links, no images/video/gif
  - not a reply
  - not a quote tweet
  - not a retweet

Input can be the .zip X sends you, the folder you unzipped it into, or
a direct path to a tweet.js / tweets.js file. X splits large archives
into tweet.js, tweet-part1.js, tweet-part2.js, ... this script reads
all of them.

Usage:
  python3 find_evergreen_candidates.py path/to/twitter-archive.zip
  python3 find_evergreen_candidates.py path/to/unzipped-folder
  python3 find_evergreen_candidates.py path/to/data/tweets.js
"""

import csv
import json
import os
import re
import sys
import zipfile
import fnmatch

MIN_LIKES_DEFAULT = 100
OUTPUT_DEFAULT = "evergreen_candidates.csv"

# Heuristic signals that a tweet is time-bound rather than evergreen.
# These are hints for a human reviewer to sort/filter by, not a filter
# this script applies itself. A flagged tweet may still be a good
# evergreen candidate; an unflagged one may still be dated in a way
# these patterns miss.
FLAG_PATTERNS = [
    ("price", re.compile(r"\$\s?\d|\b\d[\d,.]*\s?(?:k|K|usd|USD|chf|CHF)\b")),
    ("year", re.compile(r"\b20(1[0-9]|2[0-6])\b")),
    ("relative_time", re.compile(r"\b(today|yesterday|tonight|this week|this month|last week|last month|last year|right now|breaking|just (?:in|happened))\b", re.IGNORECASE)),
    ("named_event", re.compile(r"\b(halving|ETF|FOMC|CPI|Fed|SEC|election|ATH|all[- ]time high)\b", re.IGNORECASE)),
]


def heuristic_flags(text):
    return [name for name, pattern in FLAG_PATTERNS if pattern.search(text)]

# X archives wrap the JSON in a JS variable assignment, e.g.
# "window.YTD.tweets.part0 = [ ... ]". Strip everything up to the
# first "=" before parsing.
def _parse_blob(text):
    _, _, json_part = text.partition("=")
    return json.loads(json_part.strip().rstrip(";"))


def _tweet_js_names(names):
    return sorted(n for n in names if fnmatch.fnmatch(os.path.basename(n), "tweet*.js"))


def load_tweets(path):
    """Returns a flat list of raw tweet dicts from any supported input shape."""
    blobs = []

    if os.path.isfile(path) and path.lower().endswith(".zip"):
        with zipfile.ZipFile(path) as zf:
            for name in _tweet_js_names(zf.namelist()):
                blobs.append(zf.read(name).decode("utf-8"))
    elif os.path.isdir(path):
        matches = []
        for root, _dirs, files in os.walk(path):
            for f in files:
                if fnmatch.fnmatch(f, "tweet*.js"):
                    matches.append(os.path.join(root, f))
        for name in sorted(matches):
            with open(name, encoding="utf-8") as fh:
                blobs.append(fh.read())
    elif os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            blobs.append(fh.read())
    else:
        sys.exit(f"ERROR: {path} not found.")

    if not blobs:
        sys.exit(f"ERROR: no tweet.js / tweets.js files found under {path}.")

    tweets = []
    for blob in blobs:
        for entry in _parse_blob(blob):
            tweets.append(entry.get("tweet", entry))
    return tweets


def exclusion_reason(t, min_likes):
    """None if t qualifies, otherwise a short string naming why it was dropped."""
    if int(t.get("favorite_count", 0)) <= min_likes:
        return "likes"
    if t.get("in_reply_to_status_id_str"):
        return "reply"
    if t.get("is_quote_status"):
        return "quote"
    if t.get("retweeted_status") or t.get("full_text", "").startswith("RT @"):
        return "retweet"
    entities = t.get("entities") or {}
    if entities.get("urls"):
        return "link"
    media = (t.get("extended_entities") or entities).get("media")
    if media:
        return "media"
    return None


def find_candidates(tweets, min_likes):
    candidates = []
    dropped = {}
    for t in tweets:
        reason = exclusion_reason(t, min_likes)
        if reason:
            dropped[reason] = dropped.get(reason, 0) + 1
            continue
        candidates.append(t)
    candidates.sort(key=lambda t: int(t.get("favorite_count", 0)), reverse=True)
    return candidates, dropped


def write_csv(candidates, path):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["tweet_id", "created_at", "likes", "retweets", "flags", "url", "text"])
        for t in candidates:
            tweet_id = t.get("id_str", t.get("id", ""))
            text = t.get("full_text", "")
            writer.writerow([
                tweet_id,
                t.get("created_at", ""),
                t.get("favorite_count", ""),
                t.get("retweet_count", ""),
                ";".join(heuristic_flags(text)),
                f"https://x.com/relai_app/status/{tweet_id}",
                text,
            ])


def main():
    if len(sys.argv) < 2:
        sys.exit(f"Usage: python3 {os.path.basename(__file__)} <archive.zip|folder|tweet.js> [min_likes] [output.csv]")

    path = sys.argv[1]
    min_likes = int(sys.argv[2]) if len(sys.argv) > 2 else MIN_LIKES_DEFAULT
    output = sys.argv[3] if len(sys.argv) > 3 else OUTPUT_DEFAULT

    tweets = load_tweets(path)
    candidates, dropped = find_candidates(tweets, min_likes)
    write_csv(candidates, output)

    print(f"Scanned {len(tweets)} tweets.")
    for reason, count in sorted(dropped.items(), key=lambda kv: -kv[1]):
        print(f"  dropped {count} for: {reason}")
    print(f"{len(candidates)} candidates over {min_likes} likes, text-only, standalone.")
    print(f"Written to {output}. This is a review list, not evergreen.txt.")


if __name__ == "__main__":
    main()
