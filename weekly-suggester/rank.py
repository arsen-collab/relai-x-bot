#!/usr/bin/env python3
"""
Weekly X suggester - ranking.

Pure Python. No model calls, no credentials, no network. Reads an X data
archive, filters it down to standalone evergreen-eligible tweets, scores them,
and writes state/pool.json.

Run this by hand whenever a fresh archive is downloaded, then commit
state/pool.json. The archive is ~105 MB, contains DMs and ad data, and is
gitignored, so the GitHub Action cannot see it. generate.py reads
state/pool.json instead. The archive does not change week to week, so there is
nothing to gain from re-sorting it on a schedule either.

pool.json holds the full eligible set rather than a fixed top 40, so the
weekly run still has fresh material after months of used ids accumulating.
generate.py takes its shortlist off the top of it.

Usage:
  python3 weekly-suggester/rank.py                       # uses config.ARCHIVE
  python3 weekly-suggester/rank.py path/to/archive.zip
  python3 weekly-suggester/rank.py path/to/unzipped-folder
  python3 weekly-suggester/rank.py path/to/data/tweets.js

Add --show to print the head of the shortlist and an example of what each
filter dropped. Pattern tuning is a loop: run with --show, look for a rule
that is catching the wrong thing, edit config.py, run again.
"""

import collections
import difflib
import json
import os
import re
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

# The archive parsing (zip / folder / direct file, multi-part tweet*.js, the
# window.YTD.tweets.part0 wrapper) is already solved and verified in the
# existing offline tool. Reuse it rather than keeping a second copy in sync.
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, HERE)
import config  # noqa: E402
from find_evergreen_candidates import load_tweets  # noqa: E402

POOL_OUT = os.path.join(HERE, "state", "pool.json")

# X archive timestamps: "Sat Aug 08 10:02:17 +0000 2026"
CREATED_AT_FORMAT = "%a %b %d %H:%M:%S %z %Y"

DAYS_PER_MONTH = 30.44


def load_evergreen_pool(path):
    """Live pool lines, comment syntax matching post_evergreen.py."""
    if not os.path.exists(path):
        sys.exit(f"ERROR: {path} not found. Ranking needs it to exclude what already posts.")
    lines = []
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line == "#" or line.startswith("# "):
                continue
            lines.append(line.replace("\\n", "\n"))
    return lines


def normalize(text):
    """Lowercase, punctuation-stripped form for near-duplicate comparison."""
    return re.sub(r"[^a-z0-9 ]", "", text.lower().replace("\n", " ")).strip()


def compile_patterns(entries):
    return [(label, re.compile(pattern, re.IGNORECASE)) for label, pattern in entries]


PLAIN_CHARS = re.compile(r"[A-Za-z0-9 \n.,:;!?'\"()/%$€-]")


def structural_reason(text):
    """Shape checks that no word list catches.

    Likes reward ASCII art, emoji walls and hashtag spam. All three rank well
    and none of them is rewrite material.
    """
    plain = len(PLAIN_CHARS.findall(text))
    if text and plain / len(text) < config.MIN_PLAIN_RATIO:
        return "junk: not mostly plain text"
    tokens = re.findall(r"[a-z#]{2,}", text.lower())
    if tokens:
        _, repeats = collections.Counter(tokens).most_common(1)[0]
        if repeats > config.MAX_TOKEN_REPEAT:
            return "junk: repeated token"
    return None


def created_at(tweet):
    return datetime.strptime(tweet["created_at"], CREATED_AT_FORMAT)


def exclusion_reason(tweet, time_bound, not_standalone, hard_rules):
    """None if the tweet is evergreen-eligible, else a short reason string."""
    # load_tweets globs tweet*.js, which in a real export also matches
    # tweet-headers.js (id and timestamp only) and tweetdeck.js (column
    # config, no tweet key at all). The existing candidate finder drops those
    # silently via its likes threshold; here the guard has to be explicit.
    if "full_text" not in tweet or "created_at" not in tweet:
        return "not_a_tweet_record"

    text = tweet.get("full_text", "")
    entities = tweet.get("entities") or {}

    # This export carries no is_quote_status and no retweeted_status field, so
    # quote tweets are caught by the URL filter (a quote always carries a t.co
    # link to the quoted status) and retweets by the text prefix.
    if tweet.get("in_reply_to_status_id") or tweet.get("in_reply_to_status_id_str"):
        return "reply"
    if text.startswith("RT @"):
        return "retweet"
    if entities.get("urls"):
        return "link"
    if entities.get("user_mentions") or "@" in text:
        return "mention"
    if (tweet.get("extended_entities") or entities).get("media"):
        return "media"
    if len(text) < config.MIN_CHARS:
        return "too_short"
    structural = structural_reason(text)
    if structural:
        return structural
    if config.LANGUAGES and tweet.get("lang") not in config.LANGUAGES:
        return f"lang_{tweet.get('lang')}"
    for label, pattern in time_bound:
        if pattern.search(text):
            return f"time_bound: {label}"
    for label, pattern in not_standalone:
        if pattern.search(text):
            return f"not_standalone: {label}"
    # The same hard-rule checks generate.py runs on its output, applied to the
    # input. A tweet whose idea is the violation cannot be rewritten into
    # compliance while keeping the idea, so it is not rewrite material. This
    # matters more than it sounds: the archive's top performers skew heavily
    # towards other cryptocurrencies and forward-looking price framing.
    for label, pattern in hard_rules:
        if pattern.search(text):
            return f"breaks_hard_rule: {label}"
    return None


def score(tweet, reference):
    """likes + 2*reposts, halved every config.HALF_LIFE_MONTHS of age.

    Decay is measured against the newest tweet in the archive, not against
    today, so re-running the same archive always produces the same pool.json.
    """
    likes = int(tweet.get("favorite_count", 0))
    reposts = int(tweet.get("retweet_count", 0))
    raw = likes + 2 * reposts
    age_months = (reference - created_at(tweet)).days / DAYS_PER_MONTH
    decay = 0.5 ** (max(age_months, 0.0) / config.HALF_LIFE_MONTHS)
    return raw, round(raw * decay, 3)


def matches_pool(text, pool_normalized, ratio):
    """True if text is a near-duplicate of anything already in evergreen.txt."""
    matcher = difflib.SequenceMatcher()
    matcher.set_seq2(normalize(text))
    for existing in pool_normalized:
        matcher.set_seq1(existing)
        # Cheap upper bounds first; ratio() is the costly call.
        if matcher.real_quick_ratio() < ratio or matcher.quick_ratio() < ratio:
            continue
        if matcher.ratio() > ratio:
            return True
    return False


def one_line(text, width=88):
    collapsed = " ".join(text.split())
    return collapsed[:width] + ("..." if len(collapsed) > width else "")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    show = "--show" in sys.argv

    archive_path = args[0] if args else os.path.join(REPO_ROOT, config.ARCHIVE)
    pool_path = os.path.join(REPO_ROOT, config.EVERGREEN_POOL)

    analytics = os.path.join(HERE, "archive", "analytics.csv")
    if os.path.exists(analytics):
        print(f"NOTE: {analytics} exists but is not read.")
        print("      Ranking uses likes and reposts. Wire the impression data in before trusting it.")

    tweets = load_tweets(archive_path)
    evergreen = load_evergreen_pool(pool_path)
    pool_normalized = [normalize(line) for line in evergreen]
    time_bound = compile_patterns(config.TIME_BOUND)
    not_standalone = compile_patterns(config.NOT_STANDALONE)
    hard_rules = compile_patterns(config.DROP_CHECKS)

    kept, dropped, examples = [], {}, {}
    for tweet in tweets:
        reason = exclusion_reason(tweet, time_bound, not_standalone, hard_rules)
        if reason:
            dropped[reason] = dropped.get(reason, 0) + 1
            if reason != "not_a_tweet_record" and len(examples.setdefault(reason, [])) < 2:
                examples[reason].append(tweet.get("full_text", ""))
            continue
        kept.append(tweet)

    if not kept:
        sys.exit("ERROR: no eligible tweets found. Check the archive path.")

    # Reference point for the decay: the newest surviving tweet.
    reference = max(created_at(t) for t in kept)

    # Near-duplicate check runs after the cheap filters because it is the
    # expensive one.
    items, near_dupes = [], 0
    for tweet in kept:
        if matches_pool(tweet["full_text"], pool_normalized, config.NEAR_MATCH_RATIO):
            near_dupes += 1
            continue
        raw, decayed = score(tweet, reference)
        items.append({
            "id": tweet.get("id_str", str(tweet.get("id", ""))),
            "text": tweet["full_text"],
            "score": decayed,
            "raw_score": raw,
            "likes": int(tweet.get("favorite_count", 0)),
            "reposts": int(tweet.get("retweet_count", 0)),
            "date": created_at(tweet).strftime("%Y-%m-%d"),
        })

    items.sort(key=lambda i: i["score"], reverse=True)

    # The account has reposted the same line verbatim on different dates more
    # than once. Sorted descending, keeping the first occurrence keeps the
    # best-scoring instance and drops the rest.
    seen, deduped = set(), []
    for item in items:
        key = normalize(item["text"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    repeats = len(items) - len(deduped)
    items = deduped

    payload = {
        "ranking_basis": "likes + (2 * reposts), 18 month half-life decay",
        "ranking_is_weak_proxy": True,
        "ranking_note": "No impression data available, so this is engagement volume, not engagement rate.",
        "reference_date": reference.strftime("%Y-%m-%d"),
        "archive_tweets_scanned": len(tweets),
        "evergreen_pool_lines": len(evergreen),
        "items": items,
    }

    os.makedirs(os.path.dirname(POOL_OUT), exist_ok=True)
    with open(POOL_OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
        fh.write("\n")

    non_records = dropped.pop("not_a_tweet_record", 0)
    print(f"Scanned {len(tweets) - non_records} tweet records"
          f" ({non_records} non-tweet entries in tweet*.js skipped).")
    print(f"Reference date for the decay: {payload['reference_date']}.")
    for reason, count in sorted(dropped.items(), key=lambda kv: -kv[1]):
        print(f"  dropped {count:>6} for: {reason}")
    print(f"  dropped {near_dupes:>6} for: already in evergreen.txt (difflib > {config.NEAR_MATCH_RATIO})")
    print(f"  dropped {repeats:>6} for: same text posted more than once")
    print(f"{len(items)} eligible -> {os.path.relpath(POOL_OUT, REPO_ROOT)}")
    print(f"Top {config.SHORTLIST_SIZE} of these become each week's shortlist.")
    print("Ranking is a weak proxy. Commit pool.json, it is what the weekly Action reads.")

    if show:
        print(f"\n=== shortlist head ({min(15, len(items))} of {config.SHORTLIST_SIZE}) ===")
        for item in items[:15]:
            print(f"{item['score']:>9}  {item['date']}  {one_line(item['text'])}")
        print("\n=== dropped, up to 2 examples per rule ===")
        for reason in sorted(examples):
            print(f"\n{reason} ({dropped[reason]})")
            for text in examples[reason]:
                print(f"  {one_line(text)}")


if __name__ == "__main__":
    main()
