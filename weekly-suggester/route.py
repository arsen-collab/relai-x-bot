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

Two routes for copy, decided by Arsen on 2026-09-03:

  A rewrite of a tweet already published from @relai_app carries his standing
  approval, so it goes straight into fresh.txt and posts within two days.
  A net-new line has never been published and still waits for Guglielmo in
  queued/, at Compliance: unapproved.

  A line bound for fresh.txt is re-checked against config.DROP_CHECKS and
  FLAG_CHECKS first, because copy is editable on the review board and an edit
  can introduce a violation the batch never had. Anything that trips a check
  is diverted to queued/ with the reason, never softened and never dropped
  silently.

  It never touches evergreen.txt.

stdlib only, same as the rest of this folder.

Usage:
  python3 weekly-suggester/route.py                  # newest file in ~/Downloads
  python3 weekly-suggester/route.py path/to.json
"""

import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

sys.path.insert(0, HERE)
import config  # noqa: E402

FRESH_FILE = os.path.join(REPO_ROOT, "fresh.txt")

QUEUED_DIR = os.path.join(HERE, "queued")
REJECTED_FILE = os.path.join(HERE, "state", "rejected.json")
ROUTED_FILE = os.path.join(HERE, "state", "routed.json")
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
        "Held for compliance sign-off. Not postable. Nothing reads this file.",
        "",
        "Arsen's approval covers rewrites of tweets already published from the",
        "account. A line here is either net new, so nobody has published it,",
        "or it tripped a mechanical check. The reason is under each one.",
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
        if item.get("note"):
            lines.append(f"Note from review: {item['note']}")
            lines.append("")
        lines.append(f"Chars: {len(item['text'])}")
        if item.get("hold_reasons"):
            lines.append(f"Held because: {', '.join(item['hold_reasons'])}")
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

    # A scheduled router runs every couple of hours, so it will see the same
    # shipped review many times. queued/ and rejected.json are idempotent, but
    # a Notion task is not: creating it twice leaves Paula two of the same job.
    # This marker is the guard. Nothing routes twice for one Ship it.
    stamp = payload.get("submitted_at")
    routed = read_json(ROUTED_FILE, {"runs": {}})
    routed.setdefault("runs", {})
    if not payload.get("submitted"):
        print("Not marked shipped. The review is still open, nothing routed.")
        return
    if routed["runs"].get(week) == stamp:
        print(f"Already routed {week} at {stamp}. Nothing to do.")
        return

    # Briefs are tracked per suggestion, not per week. Ship a review, add two
    # more images, ship again: only the two new ones get briefed. The
    # week-level stamp above stops a re-run of the SAME submission; this stops
    # a second submission re-briefing what the first one already sent.
    routed.setdefault("briefed", {})
    briefed = set(routed["briefed"].get(week, []))

    # rewrite or net new comes from the batch file, not the board, because the
    # batch file is the record in the repo and cannot be edited in a browser.
    batch = read_json(os.path.join(BATCH_DIR, f"{week}.json"))
    kinds = {}
    if batch:
        kinds = {s["id"]: ("rewrite" if s.get("source_id") else "new")
                 for s in batch["suggestions"]}

    drop_checks = [(label, re.compile(pat, re.IGNORECASE))
                   for label, pat in config.DROP_CHECKS]
    flag_checks = [(label, re.compile(pat, re.IGNORECASE))
                   for label, pat in config.FLAG_CHECKS]

    def gate(item):
        """Reasons this line must not go straight to the posting pool."""
        reasons = [label for label, pat in drop_checks if pat.search(item["text"])]
        reasons += [label for label, pat in flag_checks if pat.search(item["text"])]
        if len(item["text"]) > 280:
            reasons.append("over 280 chars")
        return reasons

    posts = [d for d in decisions if d["action"] == "post"]
    promote, hold = [], []
    for item in posts:
        if kinds.get(item["id"]) != "rewrite":
            hold.append((item, ["net new, needs compliance sign-off"]))
            continue
        reasons = gate(item)
        if reasons:
            hold.append((item, reasons))
        else:
            promote.append(item)
    for item, reasons in hold:
        item["hold_reasons"] = reasons
    posts = [item for item, _ in hold]
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

    # approved rewrites -> the posting pool
    if promote:
        existing = ""
        if os.path.exists(FRESH_FILE):
            with open(FRESH_FILE, encoding="utf-8") as fh:
                existing = fh.read()
        lines, added = [], []
        for item in promote:
            one = item["text"].replace("\n", "\\n")
            if one in existing:
                print(f"  Already in fresh.txt, skipping: {item['id']}")
                continue
            lines.append(one)
            added.append(item["id"])
        if lines:
            with open(FRESH_FILE, "a", encoding="utf-8") as fh:
                fh.write("\n".join(lines) + "\n")
            print(f"  {len(lines)} approved rewrite(s) -> fresh.txt: {', '.join(added)}")
            print("    These post publicly within two days.")

    if hold:
        print(f"  {len(hold)} held for sign-off:")
        for item, reasons in hold:
            print(f"    {item['id']}: {', '.join(reasons)}")

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
    done = [i["id"] for i in images if i["id"] in briefed]
    if done:
        print(f"  Briefs already on Paula's board, skipping: {', '.join(done)}")
    images = [i for i in images if i["id"] not in briefed]
    if images:
        print(f"\n{len(images)} for design briefs:")
        print(json.dumps({
            "week": week,
            "briefs": [{
                "suggestion_id": item["id"],
                "headline_source": item["text"],
                "theme": item.get("theme", ""),
                "direction_from_review": item.get("note", ""),
                "source": f"Repurposed from X batch, week {int(week.split('-W')[1])}, {item['id']}",
            } for item in images],
        }, ensure_ascii=False, indent=1))

    if edited:
        print(f"\nEdited during review: {', '.join(d['id'] for d in edited)}")

    # Notes are instructions, not filing. They are printed rather than written
    # so they get read and acted on rather than buried in a file.
    noted = [d for d in decisions if d.get("note")]
    if noted:
        print("\nNotes from review:")
        for item in noted:
            action = item["action"] or "no decision yet"
            print(f"  {item['id']} ({action}): {item['note']}")

    undecided = None
    batch = read_json(os.path.join(BATCH_DIR, f"{week}.json"))
    if batch:
        decided_ids = {d["id"] for d in decisions}
        undecided = [s["id"] for s in batch["suggestions"] if s["id"] not in decided_ids]
    if undecided:
        print(f"\nStill undecided ({len(undecided)}): {', '.join(undecided)}")

    routed["runs"][week] = stamp
    routed["briefed"][week] = sorted(briefed | {i["id"] for i in images})
    write_json(ROUTED_FILE, routed)
    print(f"\nMarked {week} routed at {stamp}.")
    if images:
        print("Design briefs are NOT created by this script. Create them from "
              "the payload above with the design-brief-creator skill.")
    print("Approved rewrites are in fresh.txt and will post. Everything in "
          "queued/ needs sign-off first. evergreen.txt is never touched.")


if __name__ == "__main__":
    main()
