#!/usr/bin/env python3
"""
Weekly X suggester - route a reviewed batch.

Takes the decisions JSON saved from the review board and files every
mechanical outcome in one pass:

  post   -> queued/YYYY-Www.md, at Compliance: unapproved
  cut    -> state/rejected.json
  image  -> printed as a brief payload, for the design-brief-creator skill

Edited lines are filed as edited. The original is kept beside them so a
change is never silent.

What this deliberately does NOT do:
  It never writes to fresh.txt or evergreen.txt. Promotion into the posting
  pool happens after Guglielmo signs off, and that is a separate command.
  Nothing here can put copy in front of the public.

stdlib only, same as the rest of this folder.

Usage:
  python3 weekly-suggester/route.py                  # newest file in ~/Downloads
  python3 weekly-suggester/route.py path/to.json
"""

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

QUEUED_DIR = os.path.join(HERE, "queued")
REJECTED_FILE = os.path.join(HERE, "state", "rejected.json")
BATCH_DIR = os.path.join(HERE, "batches")

DOWNLOAD_GLOB = os.path.expanduser("~/Downloads/x-batch-*-decisions.json")


def newest_download():
    hits = sorted(glob.glob(DOWNLOAD_GLOB), key=os.path.getmtime, reverse=True)
    if not hits:
        sys.exit(f"ERROR: no decisions file matching {DOWNLOAD_GLOB}.\n"
                 "Hit Save decisions on the review board first.")
    return hits[0]


def read_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
        fh.write("\n")


def render_queue(week, posts, existing):
    lines = [f"# Queued from week {int(week.split('-W')[1])}, routed {week}", ""]
    lines += [
        "Approved by Arsen as copy. Not postable yet. Each line needs written",
        "sign-off before it can move into fresh.txt. Promotion is a separate",
        "manual act; nothing reads this file.",
        "",
    ]
    for item in posts:
        lines.append(f"## {item['id']}  {item.get('theme', '')}".rstrip())
        lines.append("")
        lines.append(item["text"])
        lines.append("")
        if item.get("original_text"):
            lines.append("Edited during review. Original was:")
            for original in item["original_text"].splitlines():
                lines.append(f"> {original}")
            lines.append("")
        lines.append(f"Chars: {len(item['text'])}")
        lines.append("Compliance: unapproved")
        lines.append("")
    body = "\n".join(lines).rstrip() + "\n"
    return (existing.rstrip() + "\n\n" + body) if existing else body


def main():
    source = sys.argv[1] if len(sys.argv) > 1 else newest_download()
    payload = read_json(source)
    if not payload:
        sys.exit(f"ERROR: could not read {source}.")

    week = payload.get("week")
    decisions = payload.get("decisions", [])
    if not week or not decisions:
        sys.exit("ERROR: file has no week or no decisions.")

    print(f"Reading {source}")
    print(f"Week {week}, {len(decisions)} decided")

    posts = [d for d in decisions if d["action"] == "post"]
    cuts = [d for d in decisions if d["action"] == "cut"]
    images = [d for d in decisions if d["action"] == "image"]
    edited = [d for d in decisions if d.get("original_text")]

    # post -> queue file
    if posts:
        os.makedirs(QUEUED_DIR, exist_ok=True)
        path = os.path.join(QUEUED_DIR, f"{week}.md")
        existing = ""
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                existing = fh.read()
            already = [p["id"] for p in posts if f"## {p['id']}" in existing]
            if already:
                print(f"  Already queued, skipping: {', '.join(already)}")
                posts = [p for p in posts if p["id"] not in already]
        if posts:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(render_queue(week, posts, existing))
            print(f"  {len(posts)} queued -> {os.path.relpath(path, REPO_ROOT)}")

    # cut -> rejected
    if cuts:
        rejected = read_json(REJECTED_FILE, {"ids": {}, "lines": []})
        rejected.setdefault("ids", {})
        rejected.setdefault("lines", [])
        known = {(entry.get("week"), entry.get("suggestion_id")) for entry in rejected["lines"]}
        added = 0
        for cut in cuts:
            if (week, cut["id"]) in known:
                continue
            rejected["lines"].append({
                "week": week,
                "suggestion_id": cut["id"],
                "text": cut["text"],
                "theme": cut.get("theme", ""),
            })
            added += 1
        write_json(REJECTED_FILE, rejected)
        print(f"  {added} cut -> {os.path.relpath(REJECTED_FILE, REPO_ROOT)}")

    # image -> brief payload, printed for the skill to pick up
    if images:
        print(f"\n{len(images)} for design briefs:")
        print(json.dumps({
            "week": week,
            "briefs": [{
                "suggestion_id": item["id"],
                "headline_source": item["text"],
                "theme": item.get("theme", ""),
                "note": f"Repurposed from X batch, week {int(week.split('-W')[1])}, {item['id']}",
            } for item in images],
        }, ensure_ascii=False, indent=1))

    if edited:
        print(f"\nEdited during review: {', '.join(d['id'] for d in edited)}")

    undecided = None
    batch = read_json(os.path.join(BATCH_DIR, f"{week}.json"))
    if batch:
        decided_ids = {d["id"] for d in decisions}
        undecided = [s["id"] for s in batch["suggestions"] if s["id"] not in decided_ids]
    if undecided:
        print(f"\nStill undecided ({len(undecided)}): {', '.join(undecided)}")

    print("\nNothing here reaches fresh.txt or evergreen.txt. Queued copy needs "
          "sign-off first.")


if __name__ == "__main__":
    main()
