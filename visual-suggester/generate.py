#!/usr/bin/env python3
"""
Weekly visual suggester - generation.

Drafts this week's visual concepts for Relai's social channels and writes
batches/YYYY-Www.md for a human to review, plus a matching .json for
notify_slack.py and the review board.

Where a concept comes from
--------------------------
Four sources, in rough order of how cheap they are to ship:

  evergreen line   a line already in evergreen.txt or fresh.txt. The words
                   passed compliance review as a specific list, so only the
                   picture is new.
  archive theme    a subject that landed more than once on @relai_app,
                   evidenced by weekly-suggester/state/pool.json.
  format rerun     a format Paula has already built, with a new subject. She
                   has the layout, so the build is short.
  net new          neither. Allowed, and where a genuinely new shape comes
                   from, but it costs a build from scratch.

And what stops it repeating itself: state/board.json, a committed snapshot of
Paula's Design board, is handed to the model as prior art. Every concept has
to name the nearest thing already on that board and say how it differs.

What this script will never do: write to evergreen.txt or fresh.txt, or to
anything post_tweet.py, post_evergreen.py or post_fresh.py reads. It writes to
batches/ and state/ only. Nothing here creates a Notion task either; that is
route.py handing a payload to the design-brief-creator skill, after review.

Every concept lands at Compliance: unapproved.

stdlib only. The Anthropic API goes through anthropic_api.py at the repo root
for the same reason x_api.py hand-rolls OAuth: no pip install step here.

Env:
  ANTHROPIC_API_KEY  required for a live run
  DRY_RUN            1/true/yes exits before any API call
  BATCH_WEEK         optional, YYYY-Www. Defaults to the current ISO week.
"""

import json
import os
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

sys.path.insert(0, HERE)
sys.path.insert(0, REPO_ROOT)
import config  # noqa: E402
import anthropic_api  # noqa: E402

BOARD_FILE = os.path.join(HERE, "state", "board.json")
MADE_FILE = os.path.join(HERE, "state", "made.json")
REJECTED_FILE = os.path.join(HERE, "state", "rejected.json")
BATCH_DIR = os.path.join(HERE, "batches")

COPY_SKILL_FILE = os.path.join(REPO_ROOT, "skills", "relai-social-copy", "SKILL.md")
DESIGN_SKILL_FILE = os.path.join(REPO_ROOT, "skills", "design-brief-creator", "SKILL.md")

TZ = ZoneInfo("Europe/Zurich")

FORMAT_KEYS = [entry["key"] for entry in config.FORMATS]
SHAPE_BY_KEY = {entry["key"]: entry["shape"] for entry in config.FORMATS}

# Concept ids (V01, V02, ...) are assigned here, not by the model, so they are
# sequential and stable across the concept call and the sketch call, neither of
# which can see the other.
CONCEPT_SCHEMA = {
    "type": "object",
    "properties": {
        "concepts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "format": {"type": "string"},
                    "shape": {"type": "string", "enum": ["single image", "carousel"]},
                    "subject": {"type": "string"},
                    "headline": {"type": "string"},
                    "caption": {"type": "string"},
                    "visual_direction": {"type": "string"},
                    "purpose": {"type": "string"},
                    "target_feeling": {"type": "string"},
                    "source_kind": {
                        "type": "string",
                        "enum": ["evergreen line", "archive theme",
                                 "format rerun", "net new"],
                    },
                    "source_ref": {"type": "string"},
                    "nearest_existing": {"type": "string"},
                    "novelty": {"type": "string"},
                    "needs_check": {"type": "array", "items": {"type": "string"}},
                    "rationale": {"type": "string"},
                    "flags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["format", "shape", "subject", "headline", "caption",
                             "visual_direction", "purpose", "target_feeling",
                             "source_kind", "source_ref", "nearest_existing",
                             "novelty", "needs_check", "rationale", "flags"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["concepts"],
    "additionalProperties": False,
}

MOCK_SCHEMA = {
    "type": "object",
    "properties": {
        "mocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "concept_id": {"type": "string"},
                    "svg": {"type": "string"},
                },
                "required": ["concept_id", "svg"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["mocks"],
    "additionalProperties": False,
}


def read_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")


def normalize(text):
    return re.sub(r"[^a-z0-9 ]", "", (text or "").lower().replace("\n", " ")).strip()


def read_pool(path):
    """Approved copy lines from an evergreen or fresh pool file."""
    if not os.path.exists(path):
        return []
    lines = []
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line == "#" or line.startswith("# "):
                continue
            lines.append(line.replace("\\n", " / "))
    return lines


def compile_checks(entries):
    return [(label, re.compile(pattern, re.IGNORECASE)) for label, pattern in entries]


def violations(text, checks):
    return [label for label, pattern in checks if pattern.search(text)]


def call_claude(api_key, system_text, user_text, schema, key, label=None):
    return anthropic_api.call_json(
        api_key, config.MODEL, system_text, user_text, schema, key,
        config.MAX_TOKENS, config.EFFORT, label=label,
    )


# --- prompts ---------------------------------------------------------------

SYSTEM_PREAMBLE = """You are proposing visual concepts for Relai's social channels. Relai is a Swiss Bitcoin-only self-custody app.

Two skills follow and both are binding. The first is the voice and compliance
spec for anything Relai publishes: every headline and caption you write is
governed by it, including its hard rules. The second is the design brief spec:
every concept you propose has to be buildable inside its visual rules.

Treat every rule in both as a hard constraint, not a preference. Before
returning a concept, check its headline and caption against the hard rules
section of the voice skill. If one breaks a rule, discard the concept and
propose a different one. Never soften a rule-breaking line into a borderline
one.

You are proposing, not approving. A human reviews every concept, edits it, and
decides which ones reach the designer. Be honest rather than tidy: a concept
that needs a figure verified is more useful with that said than without.

Return only the JSON your schema requires. No preamble, no markdown fences,
no commentary.

--- BEGIN BINDING VOICE AND COMPLIANCE SKILL ---
{copy_skill}
--- END BINDING VOICE AND COMPLIANCE SKILL ---

--- BEGIN BINDING DESIGN BRIEF SKILL ---
{design_skill}
--- END BINDING DESIGN BRIEF SKILL ---"""


FIELD_RULES = """Field rules:

- format: one of the catalog keys below, or exactly "new_format" if no catalog
  format fits. Prefer a catalog format: the designer already has the layout.
  At most two of your concepts may be "new_format".
- shape: "single image" or "carousel". Must match the catalog format's shape.
  A new_format concept should be "single image" unless the idea genuinely
  cannot be told in one frame. Single portrait is the house default.
- subject: three to six words naming what the concept is about.
- headline: the line set ON the image. Under {max_headline} characters. It is
  not the caption repeated and it is not a tweet. Tighten it until it holds at
  large size. No hashtags, no links, no @ mentions.
- caption: what is posted alongside, English only. Every number, statistic and
  piece of context lives here, never on the image. Under {max_caption}
  characters.
- visual_direction: one visual device and no more. Never two combined, never
  illustration-heavy. Concrete enough to build from: say what the device is,
  where the one accent colour goes, and what to avoid. Generous white space.
  Logo bottom right. No font names, the designer decides those.
- purpose: one sentence on what the asset is for.
- target_feeling: one sentence on how it should land.
- source_kind and source_ref: where the idea came from. For "evergreen line",
  source_ref is that line, quoted. For "archive theme", the theme plus what in
  the archive evidences it. For "format rerun", the catalog format plus the
  board item you are re-running. For "net new", one line on why it belongs.
- nearest_existing: the closest item already on the design board, by its exact
  title. "nothing close" only when that is genuinely true. Check the list.
- novelty: one line on how your concept differs from that nearest item. If the
  difference is only the wording, it is not a new concept. Do not propose it.
- needs_check: every figure, price, date or factual claim in the concept that a
  human has to verify before the asset is built, each named specifically. Relai
  marketing numbers come from its own backtest tool or verified data and are
  never approximated, so a concept that leans on a number you cannot source
  must say so here rather than guess. Empty array only if the concept contains
  no figure or factual claim at all.
- rationale: one line on why this earns a slot this week.
- flags: compliance terms the concept brushes against, empty array if clean.
  Name the term, for example "savings terminology". A human reads this list and
  an empty array on a concept that needed a flag is worse than a flag on a
  clean one."""


def concept_prompt(count, board, evergreen, fresh, archive, made, avoid):
    formats = []
    saturation = board.get("format_saturation", {})
    for entry in config.FORMATS:
        shipped = saturation.get(entry["key"], 0)
        formats.append(
            f"{entry['key']}  ({entry['shape']}, {shipped} on the board)\n"
            f"  What it is: {entry['what']}\n"
            f"  Only works if: {entry['needs']}\n"
            f"  Already shipped: {'; '.join(entry['shipped'])}"
        )

    prior = []
    for concept in board.get("concepts", []):
        line = f"- {concept['title']}"
        if concept.get("headline"):
            line += f"  |  headline: {concept['headline'][:90]}"
        if concept.get("format_guess"):
            line += f"  |  {concept['format_guess']}"
        prior.append(line)

    sections = [
        f"Propose {count} visual concepts for this week.",
        "",
        "Aim for a spread across the four source kinds rather than eight of",
        "one. Aim for a spread across formats too: a format with a high count",
        "on the board is not banned, but it is saturated, and a fifth version",
        "of it needs a better reason than a first version of something else.",
        "",
        FIELD_RULES.format(max_headline=config.MAX_HEADLINE_CHARS,
                           max_caption=config.MAX_CAPTION_CHARS),
        "",
        "=" * 70,
        "FORMAT CATALOG",
        "",
        "Every format here has shipped at least once, so the designer has a",
        "layout for it. The count is how many items on the board look like it.",
        "",
        "\n\n".join(formats),
        "",
        "=" * 70,
        "ALREADY ON THE DESIGN BOARD",
        "",
        f"{len(prior)} concepts, {board.get('covers', {}).get('oldest', '?')} to "
        f"{board.get('covers', {}).get('newest', '?')}. This is prior art. Do not",
        "propose any of these again. Name the nearest one for every concept you",
        "do propose.",
        "",
        "\n".join(prior) if prior else "(the board snapshot is empty)",
    ]

    if made:
        sections += [
            "",
            "=" * 70,
            "BRIEFED SINCE THE SNAPSHOT",
            "",
            "Every visual brief filed since the board snapshot above was taken,",
            "whether it came from this tool or was written straight into a chat",
            "session. This list is current. Do not propose any of these again.",
            "",
            "\n".join(f"- {item['subject']}: {item['headline']}" for item in made),
        ]

    if evergreen or fresh:
        sections += [
            "",
            "=" * 70,
            "APPROVED COPY, THE CHEAPEST SOURCE",
            "",
            "These lines are in Relai's live posting pools. They went through",
            "compliance review as a specific list, so a concept built on one",
            "only needs the picture approving, not the words. You may tighten a",
            "line to fit an image, but say so in source_ref and keep the",
            "meaning exactly.",
            "",
            "\n".join(f"- {line}" for line in evergreen + fresh),
        ]

    if archive:
        sections += [
            "",
            "=" * 70,
            "WHAT LANDED ON X",
            "",
            "The strongest standalone posts from the archive, ranked by likes",
            "plus twice reposts with a recency decay. No impression data was",
            "available, so this is a rough signal of what landed, not a precise",
            "one. Use it as evidence of a theme worth a picture, not as copy to",
            "reuse verbatim.",
            "",
            "\n".join(f"- ({item['likes']} likes, {item['date']}) "
                      f"{' '.join(item['text'].split())[:160]}"
                      for item in archive),
        ]

    if avoid:
        sections += [
            "",
            "=" * 70,
            "ALREADY IN THIS BATCH",
            "",
            "Do not repeat or closely paraphrase these:",
            "",
            "\n".join(f"- {headline}" for headline in avoid),
        ]

    return "\n".join(sections)


def mock_prompt(concepts):
    palette = config.MOCK_PALETTE
    lines = [
        "Sketch every concept below as one rough SVG.",
        "",
        "These are thumbnails for a human judging composition on a review",
        "board. They are not deliverables and they are never sent to the",
        "designer, who works from the written direction. So: get the shape,",
        "the hierarchy and the placement right, and do not attempt polish.",
        "",
        "Rules for each SVG:",
        '- Root element exactly: <svg viewBox="0 0 1080 1350" '
        'xmlns="http://www.w3.org/2000/svg"> with no width or height '
        "attributes, so it scales to whatever box it is dropped in.",
        "- Self-contained. No external images, no fonts, no scripts, no CSS",
        "  imports, no base64 payloads. Plain shapes, paths and <text>.",
        "- Use font-family=\"sans-serif\" and nothing else. The real typeface",
        "  is the designer's decision.",
        "- Monochrome. Four values only, and no others: "
        f"paper {palette['paper']}, muted {palette['muted']}, "
        f"ink {palette['ink']}, accent {palette['accent']}."
        " Do not introduce a colour. Colour is the designer's decision and a"
        " sketch that looks brand-coloured gets mistaken for one.",
        "- Paper fill covers the whole canvas. `accent` marks the one accent",
        "  position: the smallest area on the sketch, on the single thing the",
        "  eye should reach second. Nothing else may use that value, so the",
        "  accent placement stays readable without implying a hue.",
        "- Render the headline as real text, at the size it would actually be",
        "  set. If it does not fit the canvas at display size, that is a",
        "  finding worth seeing, so do not shrink it to fit.",
        "- Represent the visual device with simple geometry. A chart is two",
        "  polylines. A prop is a silhouette built from a few paths. A phone",
        "  is a rounded rect. Do not draw a logo; put a small muted rect",
        "  bottom right where the logo goes.",
        "- No caption text on the sketch. The caption is posted alongside the",
        "  image, never set on it.",
        "- For a carousel, sketch the cover slide only, and put a row of small",
        "  muted dots at the bottom showing the slide count.",
        "",
        "Return one entry per concept id, in the same order.",
        "",
        "CONCEPTS",
    ]
    for concept in concepts:
        lines += [
            "",
            f"{concept['id']}  [{concept['format']}, {concept['shape']}]",
            f"  headline: {concept['headline']}",
            f"  device:   {concept['visual_direction']}",
        ]
    return "\n".join(lines)


# --- generation ------------------------------------------------------------

def build_system_text():
    with open(COPY_SKILL_FILE, encoding="utf-8") as fh:
        copy_skill = fh.read()
    design_skill = ""
    if os.path.exists(DESIGN_SKILL_FILE):
        with open(DESIGN_SKILL_FILE, encoding="utf-8") as fh:
            design_skill = fh.read()
    else:
        print(f"WARNING: {DESIGN_SKILL_FILE} not found, concepts will be off-spec.")
    return SYSTEM_PREAMBLE.format(copy_skill=copy_skill, design_skill=design_skill)


def check_concept(concept, seen, drop_checks, board_titles):
    """Mechanical reasons this concept must not reach the review board.

    Copy rules apply to the headline and caption because those get published.
    They are not applied to visual_direction: that text is an instruction to a
    designer, not published copy, and a direction saying "avoid any price
    projection" would trip the projection check on the word itself.
    """
    reasons = []
    headline = (concept.get("headline") or "").strip()
    caption = (concept.get("caption") or "").strip()

    if not headline:
        reasons.append("empty headline")
    if len(headline) > config.MAX_HEADLINE_CHARS:
        reasons.append(f"headline over {config.MAX_HEADLINE_CHARS} chars")
    if len(caption) > config.MAX_CAPTION_CHARS:
        reasons.append(f"caption over {config.MAX_CAPTION_CHARS} chars")
    if not (concept.get("visual_direction") or "").strip():
        reasons.append("no visual direction")

    reasons += violations(f"{headline}\n{caption}", drop_checks)

    fmt = concept.get("format")
    if fmt not in FORMAT_KEYS and fmt != "new_format":
        reasons.append(f"unknown format {fmt!r}")
    elif fmt in SHAPE_BY_KEY and concept.get("shape") != SHAPE_BY_KEY[fmt]:
        reasons.append(f"{fmt} is a {SHAPE_BY_KEY[fmt]}, not a {concept.get('shape')}")

    key = normalize(headline)
    if key in seen:
        reasons.append("duplicate of another concept")
    if key and key in board_titles:
        reasons.append("headline matches something already on the board")

    return reasons


def collect(api_key, system_text, prompt_builder, want, drop_checks, flag_checks,
            board_titles):
    """Request `want` concepts, dropping any that fail a mechanical check.

    A dropped concept is re-requested, never softened. That is the voice
    skill's own rule for a broken hard rule.
    """
    kept, dropped_log = [], []
    seen = set()

    for attempt in range(1 + config.MAX_REGENERATION_ROUNDS):
        need = want - len(kept)
        if need <= 0:
            break
        if attempt:
            print(f"  re-requesting {need} after drops (round {attempt + 1})")
        batch = call_claude(
            api_key, system_text,
            prompt_builder(need, [k["headline"] for k in kept]),
            CONCEPT_SCHEMA, "concepts", label="concepts",
        )

        for concept in batch:
            reasons = check_concept(concept, seen, drop_checks, board_titles)
            if reasons:
                dropped_log.append({
                    "headline": (concept.get("headline") or "")[:120],
                    "reasons": reasons,
                })
                continue

            concept["headline"] = concept["headline"].strip()
            concept["caption"] = concept["caption"].strip()
            seen.add(normalize(concept["headline"]))
            concept["flags"] = sorted(
                set(f for f in (concept.get("flags") or []) if f)
                | set(violations(f"{concept['headline']}\n{concept['caption']}",
                                 flag_checks))
            )
            kept.append(concept)
            if len(kept) == want:
                break

    return kept[:want], dropped_log


# A sketch is decoration on a review card, and it is written by a model, so it
# is checked before it is stored rather than trusted. Anything that could
# fetch, execute or phone home is rejected outright and the card simply shows
# no sketch.
SVG_FORBIDDEN = re.compile(
    r"<\s*(script|foreignObject|iframe|image|use|animate|set|audio|video)\b"
    r"|\bon[a-z]+\s*="
    r"|javascript:"
    r"|<!ENTITY|<!DOCTYPE"
    r"|\b(?:href|xlink:href|src)\s*=\s*[\"']?(?!#)",
    re.IGNORECASE,
)


def clean_svg(svg):
    """Return the sketch if it is inert and well-formed enough, else None."""
    if not svg:
        return None
    svg = svg.strip()
    if svg.startswith("```"):
        svg = re.sub(r"^```[a-z]*\n?|\n?```$", "", svg).strip()
    if not svg.startswith("<svg") or not svg.endswith("</svg>"):
        return None
    if SVG_FORBIDDEN.search(svg):
        return None
    if len(svg) > 40000:
        return None
    return svg


def collect_mocks(api_key, system_text, concepts):
    """One sketch per concept. A failure here is not fatal: the batch is still
    reviewable, the cards just show the written direction with no sketch."""
    try:
        result = call_claude(api_key, system_text, mock_prompt(concepts),
                             MOCK_SCHEMA, "mocks", label="sketches")
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: sketching failed: {exc}")
        return {}

    mocks, rejected = {}, []
    for entry in result:
        svg = clean_svg(entry.get("svg"))
        if svg:
            mocks[entry["concept_id"]] = svg
        else:
            rejected.append(entry.get("concept_id", "?"))
    if rejected:
        print(f"  rejected as unsafe or malformed: {', '.join(rejected)}")
    missing = [c["id"] for c in concepts if c["id"] not in mocks]
    if missing:
        print(f"  no sketch for {', '.join(missing)}")
    return mocks


# --- output ----------------------------------------------------------------

def render_batch(week_label, run_date, generated_at, concepts, dropped, board):
    lines = [
        f"# Visual concepts, week {int(week_label.split('-W')[1])}, {run_date}",
        "",
        f"Generated: {generated_at}",
        f"Board snapshot: {board.get('concept_count', 0)} prior concepts, "
        f"to {board.get('covers', {}).get('newest', '?')}",
        "Status: unreviewed",
        "",
        "Advisory draft. Nothing here has been sent to the designer and nothing",
        "here is approved to publish. Tick one box per concept, then hand this",
        "file to a chat session.",
        "",
    ]

    for concept in concepts:
        lines += [
            f"## {concept['id']}  {concept['subject']}",
            "[ ] make   [ ] cut",
            "",
            f"Format:    {concept['format']} ({concept['shape']})",
            f"Headline:  {concept['headline']}",
            f"Caption:   {concept['caption']}",
            f"Visual:    {concept['visual_direction']}",
            f"Purpose:   {concept['purpose']}",
            f"Feeling:   {concept['target_feeling']}",
            "",
            f"Source:    {concept['source_kind']} | {concept['source_ref']}",
            f"Nearest:   {concept['nearest_existing']}",
            f"Novelty:   {concept['novelty']}",
            f"Why now:   {concept['rationale']}",
        ]
        if concept["needs_check"]:
            lines.append("Verify first:")
            lines += [f"  - {item}" for item in concept["needs_check"]]
        else:
            lines.append("Verify first: nothing, no figures or claims in it")
        lines += [
            f"Flags:     {', '.join(concept['flags']) if concept['flags'] else 'none'}",
            "Compliance: unapproved",
            "",
        ]

    if dropped:
        lines += [
            "---",
            "",
            f"## Dropped before review ({len(dropped)})",
            "",
            "These failed a mechanical check and were regenerated rather than",
            "softened. Listed so a false positive in the patterns stays visible.",
            "",
        ]
        for item in dropped:
            lines.append(f"- {', '.join(item['reasons'])}: {item['headline']}")
        lines.append("")

    return "\n".join(lines)


def main():
    dry_run = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")

    now = datetime.now(TZ)
    # BATCH_WEEK forces the label, matching notify_slack.py. Used to generate a
    # week ahead of its run day, or to re-run one that was lost.
    week_label = os.environ.get("BATCH_WEEK", "").strip()
    if not week_label:
        year, week, _ = now.isocalendar()
        week_label = f"{year}-W{week:02d}"
    batch_md = os.path.join(BATCH_DIR, f"{week_label}.md")
    batch_json = os.path.join(BATCH_DIR, f"{week_label}.json")

    board = read_json(BOARD_FILE, None)
    if board is None:
        sys.exit(
            f"ERROR: {os.path.relpath(BOARD_FILE, REPO_ROOT)} not found.\n"
            "Refresh the design board snapshot and commit it:\n"
            "  python3 visual-suggester/snapshot.py <dump.json>"
        )

    made = read_json(MADE_FILE, {"concepts": []}).get("concepts", [])
    rejected = read_json(REJECTED_FILE, {"concepts": []}).get("concepts", [])

    evergreen = read_pool(os.path.join(REPO_ROOT, config.EVERGREEN_POOL))
    fresh = read_pool(os.path.join(REPO_ROOT, config.FRESH_POOL))
    if not evergreen:
        sys.exit(f"ERROR: {config.EVERGREEN_POOL} is empty or missing.")

    pool = read_json(os.path.join(REPO_ROOT, config.X_POOL), None)
    archive = []
    if pool:
        archive = pool["items"][:30]
    else:
        print(f"WARNING: {config.X_POOL} not found. No archive evidence this run.")

    # Prior art the model must not re-propose, and the mechanical dedupe set
    # behind it. Cut concepts are in here too: a cut is a decision, and it
    # should not come back next week.
    board_titles = {normalize(c["title"]) for c in board.get("concepts", [])}
    board_titles |= {normalize(c.get("headline")) for c in board.get("concepts", [])}
    board_titles |= {normalize(c.get("headline")) for c in made}
    board_titles |= {normalize(c.get("headline")) for c in rejected}
    board_titles.discard("")

    print(f"Now: {now:%Y-%m-%d %H:%M %Z} | week {week_label}")
    print(f"Board: {board.get('concept_count', 0)} prior concepts, "
          f"snapshot to {board.get('covers', {}).get('newest', '?')}")
    print(f"Approved copy: {len(evergreen)} evergreen + {len(fresh)} fresh")
    print(f"Archive evidence: {len(archive)} posts")
    print(f"Sent to the designer before: {len(made)} | cut before: {len(rejected)}")
    print(f"Target: {config.CONCEPTS} concepts")

    if os.path.exists(batch_md):
        print(f"{os.path.relpath(batch_md, REPO_ROOT)} already exists. Nothing to do.")
        return

    if dry_run:
        print("\nDRY_RUN enabled. No API call, so this does not test the API key.")
        print(f"Would write {os.path.relpath(batch_md, REPO_ROOT)}")
        print("\nFormat saturation on the board:")
        # Sorted here rather than trusting the file: board.json is written
        # with sort_keys, which alphabetizes the saturation map on the way in.
        saturation = board.get("format_saturation", {})
        for key, count in sorted(saturation.items(), key=lambda kv: -kv[1]):
            print(f"  {count:>3}  {key}")
        print("\nPrior art head:")
        for concept in board.get("concepts", [])[:5]:
            print(f"  {concept['created']}  {concept['title'][:70]}")
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ERROR: ANTHROPIC_API_KEY is not set.")

    system_text = build_system_text()
    drop_checks = compile_checks(config.DROP_CHECKS)
    flag_checks = compile_checks(config.FLAG_CHECKS)

    print("\nConcepts:")
    concepts, dropped = collect(
        api_key, system_text,
        lambda need, avoid: concept_prompt(need, board, evergreen, fresh,
                                           archive, made, avoid),
        config.CONCEPTS, drop_checks, flag_checks, board_titles,
    )
    if not concepts:
        sys.exit("ERROR: every concept failed a check. Nothing written.")
    for index, concept in enumerate(concepts, start=1):
        concept["id"] = f"V{index:02d}"

    mocks = {}
    if config.MOCKS:
        print(f"\nSketching {len(concepts)} concepts...")
        mocks = collect_mocks(api_key, system_text, concepts)
        print(f"  {len(mocks)} sketched")

    os.makedirs(BATCH_DIR, exist_ok=True)
    with open(batch_md, "w", encoding="utf-8") as fh:
        fh.write(render_batch(
            week_label,
            now.strftime("%Y-%m-%d"),
            now.strftime("%Y-%m-%d %H:%M %Z"),
            concepts,
            dropped,
            board,
        ))

    write_json(batch_json, {
        "week": week_label,
        "generated_at": now.strftime("%Y-%m-%d %H:%M %Z"),
        "status": "unreviewed",
        "batch_file": os.path.relpath(batch_md, REPO_ROOT),
        "board_snapshot": {
            "concept_count": board.get("concept_count", 0),
            "newest": board.get("covers", {}).get("newest", ""),
        },
        "concepts": [
            {
                "id": c["id"],
                "format": c["format"],
                "shape": c["shape"],
                "subject": c["subject"],
                "headline": c["headline"],
                "caption": c["caption"],
                "visual_direction": c["visual_direction"],
                "purpose": c["purpose"],
                "target_feeling": c["target_feeling"],
                "source_kind": c["source_kind"],
                "source_ref": c["source_ref"],
                "nearest_existing": c["nearest_existing"],
                "novelty": c["novelty"],
                "needs_check": c["needs_check"],
                "rationale": c["rationale"],
                "flags": c["flags"],
                "compliance": "unapproved",
                "mock_svg": mocks.get(c["id"]),
            }
            for c in concepts
        ],
        "brief_defaults": {
            "platform": config.BRIEF_PLATFORM,
            "languages": config.BRIEF_LANGUAGES,
            "priority": config.BRIEF_PRIORITY,
            "due_days": config.BRIEF_DUE_DAYS,
            "image_spec": config.BRIEF_IMAGE_SPEC,
        },
        "mock_palette_is_placeholder": True,
        "dropped_count": len(dropped),
    })

    print(f"\n{len(concepts)} concepts, {len(dropped)} dropped")
    by_source = {}
    for concept in concepts:
        by_source[concept["source_kind"]] = by_source.get(concept["source_kind"], 0) + 1
    print("By source: " + ", ".join(f"{v} {k}" for k, v in sorted(by_source.items())))
    flagged = [c["id"] for c in concepts if c["flags"]]
    print(f"Flagged for compliance: {', '.join(flagged) if flagged else 'none'}")
    needs = [c["id"] for c in concepts if c["needs_check"]]
    print(f"Carry a figure to verify: {', '.join(needs) if needs else 'none'}")
    print(f"Wrote {os.path.relpath(batch_md, REPO_ROOT)}")
    print(f"Wrote {os.path.relpath(batch_json, REPO_ROOT)}")
    print("Every concept is at Compliance: unapproved. Nothing has been sent "
          "to the designer.")


if __name__ == "__main__":
    main()
