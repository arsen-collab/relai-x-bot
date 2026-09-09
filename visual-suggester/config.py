#!/usr/bin/env python3
"""
Weekly visual suggester configuration.

A Python module rather than YAML or TOML, same reasoning as
weekly-suggester/config.py: no pip install step in this repo, and tomllib
only exists from Python 3.11 while snapshot.py runs offline on a Mac with the
system 3.9.

The compliance checks are not defined here. They are imported from
compliance_checks.py at the repo root, which weekly-suggester/config.py also
imports, so a pattern edit lands on both suggesters at once.

Tune the lists here. No logic lives in this file.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from compliance_checks import DROP_CHECKS, FLAG_CHECKS  # noqa: E402,F401


# --- paths -----------------------------------------------------------------

# Approved X copy, read only. A cleared line that has never been made into an
# image is the cheapest possible source of a concept: the words already
# passed review, only the picture is new.
EVERGREEN_POOL = "evergreen.txt"
FRESH_POOL = "fresh.txt"

# The X archive ranking, built by weekly-suggester/rank.py. Read only. Used as
# theme evidence: a subject that landed on X twice is worth a picture.
X_POOL = "weekly-suggester/state/pool.json"


# --- generation ------------------------------------------------------------

# Sonnet: drafting against a clear spec, not ambiguous reasoning. Same call as
# the X suggester.
MODEL = "claude-sonnet-5"

# Eight, not fifteen. A visual concept takes longer to judge than a line of
# copy, and a board nobody finishes reviewing is worse than a shorter one.
CONCEPTS = 8

# Concepts failing a mechanical check are dropped and re-requested, never
# softened. This caps the re-request rounds so a bad run cannot spin.
MAX_REGENERATION_ROUNDS = 2

MAX_TOKENS = 24000
EFFORT = "high"

# On-image headline. Shorter than a tweet on purpose: it has to hold at large
# size on a 1080 wide canvas.
MAX_HEADLINE_CHARS = 70
MAX_CAPTION_CHARS = 400

# A rough SVG per concept, rendered on the review board so the shape of the
# thing is visible at decision time rather than described. It is a sketch for
# judging composition, never a deliverable and never sent to Paula: the brief
# is what she works from. One extra Sonnet call a week.
#
# A failure here is not fatal. The batch is still reviewable, the cards just
# show the written direction with no sketch.
MOCKS = True

# Placeholder palette for the sketches only. Relai's real brand values are in
# the brand book and are not in this repo, so these are stand-ins chosen to
# read correctly in a thumbnail, not brand-accurate hex.
#
# TODO: replace with the brand book values. Until then the sketches are
# indicative of composition, not colour.
MOCK_PALETTE = {
    "accent": "#F7931A",   # placeholder orange
    "ink": "#0E1B2E",      # placeholder navy
    "paper": "#FFFFFF",
    "muted": "#9AA5B1",
}


# --- brief defaults --------------------------------------------------------
# Mirrors weekly-suggester/config.py. skills/design-brief-creator/SKILL.md is
# the source of truth for all of these; they are repeated here so the batch
# file records what the brief will say.

BRIEF_PLATFORM = ["IG"]
BRIEF_LANGUAGES = ["🇬🇧 EN", "🇩🇪 DE"]
BRIEF_PRIORITY = "Medium"

# Days from the day the brief is filed, not from the batch date.
BRIEF_DUE_DAYS = 3

BRIEF_IMAGE_SPEC = "1080 x 1350 px, portrait"


# --- Slack -----------------------------------------------------------------

# The destination is not configured here. An Incoming Webhook's target is
# fixed when the webhook is created, so SLACK_WEBHOOK_URL decides where the
# batch lands. Same secret as the X suggester, so both land in the same DM.

# The review board. Set once the artifact exists and is republished weekly
# rather than minted fresh. Empty string drops the link from the message.
REVIEW_URL = ""


# --- the format catalog ----------------------------------------------------
# Read off Paula's Design board rather than invented. Every format here has
# shipped at least once, so proposing a new subject inside one is proposing
# something she has already built and has a layout for.
#
# `needs` is the honest precondition. A concept proposed in a format whose
# precondition it cannot meet is a concept that dies in production, which is
# where most of the waste in this pipeline used to sit.
#
# Add a format here only after it has shipped. The model may also answer
# "new format", which is allowed and is where a genuinely new shape comes
# from, but it costs Paula a build from scratch so it should be the minority.

FORMATS = [
    {
        "key": "versus",
        "label": "Two-column versus",
        "shape": "single image",
        "what": "Two subjects side by side, thin vertical divider, one fact "
                "under each. The asymmetry is the whole point.",
        "needs": "Two subjects with a real, checkable asymmetry, and one "
                 "verified figure or fact per side. No projection.",
        "shipped": ["Bitcoin vs Rolex", "iPhone vs Bitcoin",
                    "Fort Knox vs Bitcoin audit frequency",
                    "Big Tech vs Bitcoin", "Polkadot vs Banana"],
    },
    {
        "key": "then_now",
        "label": "Then and now",
        "shape": "single image",
        "what": "One subject at two points in time, same two-column "
                "structure, the change carried by the two figures.",
        "needs": "A subject with a verified value at both dates. Historical "
                 "only, never a projected one.",
        "shipped": ["Burger priced in BTC 2016 vs 2026",
                    "1 BTC in 2011 vs 2026"],
    },
    {
        "key": "two_line_chart",
        "label": "One chart, two lines",
        "shape": "single image",
        "what": "A single simple chart, two lines starting together and "
                "diverging. Accent on the line the post is about.",
        "needs": "A real dataset for both lines and a source Relai can name. "
                 "No axis numbers invented to make the shape work.",
        "shipped": ["Working Harder, Buying Less",
                    "Stop Saving in Euro banknote decline"],
    },
    {
        "key": "single_prop",
        "label": "One prop carrying the metaphor",
        "shape": "single image",
        "what": "A single object or scene that states the idea without "
                "explaining it. Nothing else in the frame.",
        "needs": "A metaphor that reads in under a second with no caption. "
                 "One object, not a scene with several.",
        "shipped": ["Euro note behind prison bars", "Bank card in ice",
                    "Monopoly Man at the printing press",
                    "Your savings are melting",
                    "Bear silhouette with an orange arrow through it"],
    },
    {
        "key": "type_only",
        "label": "Type as the device",
        "shape": "single image",
        "what": "No imagery at all. Weight, size and one accent word do the "
                "work. Cheapest thing on this list to build.",
        "needs": "A line short enough to hold at large size, with one word "
                 "worth accenting.",
        "shipped": ["Businesses Want Bitcoin checklist",
                    "Week 36 type treatments"],
    },
    {
        "key": "big_number",
        "label": "One dominant number",
        "shape": "single image",
        "what": "A single figure at display size, one line of context under "
                "it, nothing competing.",
        "needs": "A figure from Relai's own verified data or a nameable "
                 "public source. Never approximated.",
        "shipped": ["Relai users are buying, bear market"],
    },
    {
        "key": "timeline",
        "label": "Left-to-right progression",
        "shape": "single image",
        "what": "A row of simple shapes or markers showing a change across "
                "time, read in one sweep.",
        "needs": "Three to five steps, each with a real date. Original "
                 "silhouettes, never a brand's product photography.",
        "shipped": ["Bitcoin HODL adoption timeline",
                    "Torn banknote decline timeline"],
    },
    {
        "key": "phone_mockup",
        "label": "App screen as the device",
        "shape": "single image",
        "what": "One Relai screen in a plain phone frame, headline beside "
                "or above it.",
        "needs": "The screen has to exist and be current. Do not propose a "
                 "screen for a feature that has not shipped.",
        "shipped": ["App update announcement template",
                    "Faster verification announcement"],
    },
    {
        "key": "whatsapp_chat",
        "label": "WhatsApp chat carousel",
        "shape": "carousel",
        "what": "A conversation between two people, one bubble colour each, "
                "the objection and the answer landing as dialogue.",
        "needs": "A real objection someone actually voices, and an answer "
                 "that does not read as advice.",
        "shipped": ["Friend-to-friend DCA", "Relai Private"],
    },
    {
        "key": "myth_rebuttal",
        "label": "Quote and answer carousel",
        "shape": "carousel",
        "what": "One belief per slide in quotes, the answer directly under "
                "it. Consistent template throughout.",
        "needs": "Five to seven beliefs that are genuinely common, each "
                 "answerable in one line without a claim.",
        "shipped": ["5 Bitcoin misconceptions debunked",
                    "5 rules every Bitcoin investor should follow",
                    "Relai 6th birthday, what they told us"],
    },
    {
        "key": "step_compounding",
        "label": "One step per slide",
        "shape": "carousel",
        "what": "The same calculation advanced one interval per slide, so "
                "the reader watches it move.",
        "needs": "Figures from Relai's own calculator or backtest tool. "
                 "Backward looking only.",
        "shipped": ["3% inflation, what it actually costs you"],
    },
    {
        "key": "testimonial",
        "label": "Real reviews carousel",
        "shape": "carousel",
        "what": "One real review per slide, name and country, nothing added.",
        "needs": "Published reviews, quoted exactly, with the source URL. "
                 "Never paraphrased into something better.",
        "shipped": ["Review of the week"],
    },
]

# Board rows that are request-driven rather than idea-driven. These are jobs
# Arsen sends Paula when something specific needs a picture, not concepts a
# suggester could have proposed, so they are dropped from the snapshot: they
# are neither format evidence nor a thing to avoid repeating.
#
# Matched case-insensitively against the row title.
NOT_A_CONCEPT = [
    "blog image", "blog images", "blog header", "blog headers", "blog post",
    "email header", "email image",
    "app icon", "3d icon", "brand book", "template", "templates",
    # Housekeeping and container rows, mostly from the board's first week.
    # They name a channel or an asset type, not an idea.
    "print product", "paid ad", "podcast cover", "social media posts",
    "ref programm", "de version",
    # A dated news series. Every edition is time-bound by design, so it is
    # not evergreen concept territory and must not be proposed here.
    "this week in bitcoin",
    "figma", "drive folder",
]
