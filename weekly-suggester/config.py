#!/usr/bin/env python3
"""
Weekly X suggester configuration.

A Python module rather than YAML or TOML. PyYAML needs a pip install, which
this repo deliberately does not have, and tomllib only exists from Python 3.11
while rank.py runs offline on a Mac with the system 3.9. A module works on
both, keeps comments, and lets regex patterns stay raw strings instead of
escaped twice. find_evergreen_candidates.py already keeps its pattern list
this way.

Tune the lists here. No logic lives in this file.
"""

# --- paths -----------------------------------------------------------------

# Live evergreen pool. Read only, for exclusion. Never written to.
EVERGREEN_POOL = "evergreen.txt"

# Default archive location, relative to the repo root. Override on the command
# line: python3 weekly-suggester/rank.py ~/Downloads/twitter-2026-.../data
ARCHIVE = "weekly-suggester/archive"


# --- ranking ---------------------------------------------------------------

# Below this, a tweet is too short to carry an idea.
MIN_CHARS = 40

# Working shortlist handed to generate.py each week.
SHORTLIST_SIZE = 40

# How many of the shortlist are shown to the model as voice and theme
# reference for the net-new suggestions.
REFERENCE_POOL_SIZE = 20

# Recency decay. A tweet loses half its score every HALF_LIFE_MONTHS, so a
# 2021 post with high raw counts does not outrank a 2025 one forever.
HALF_LIFE_MONTHS = 18.0

# difflib ratio above which a candidate counts as already in the pool.
NEAR_MATCH_RATIO = 0.85

# The archive holds de, it, es and qme (media-only) tweets too. X copy is
# written in English, so non-English tweets are not rewrite material.
# Set to None to keep every language.
LANGUAGES = ["en"]


# --- generation ------------------------------------------------------------

# Sonnet: drafting against a clear spec, not ambiguous reasoning.
MODEL = "claude-sonnet-5"

REWRITES = 9
NET_NEW = 6

# Suggestions failing a mechanical check are dropped and re-requested, never
# softened. This caps the re-request rounds so a bad run cannot spin.
MAX_REGENERATION_ROUNDS = 2

MAX_TOKENS = 16000
EFFORT = "high"

MAX_SUGGESTION_CHARS = 280


# --- Slack -----------------------------------------------------------------

# DM Arsen. Replace with a private channel id to route the batch elsewhere.
SLACK_DESTINATION = "U02C08MR0KW"


# --- time-bound patterns ---------------------------------------------------

# A shortlist candidate matching any of these is dropped at rank time. This
# list is what makes the pool evergreen, so tune it here. Case insensitive,
# applied to the raw tweet text.
TIME_BOUND = [
    ("price figure", r"\$\s?\d|\b\d[\d,.]*\s?(?:k|usd|chf|eur|€)\b"),
    ("percentage move", r"\b\d+([.,]\d+)?\s?%"),
    ("relative time", r"\b(today|yesterday|tonight|tomorrow|this (?:week|month|year|morning)"
                      r"|last (?:week|month|year)|next (?:week|month|year)|right now"
                      r"|just (?:in|now|happened|launched|landed|dropped)|now live|breaking"
                      r"|new:|coming soon|recent|recently|the other day|as of now"
                      r"|currently|at the moment"
                      r"|in the (?:last|past) \d+ (?:days?|weeks?|months?|years?))\b"),
    ("calendar date", r"\b20(?:1[0-9]|2[0-9])\b"
                      r"|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}\b"
                      r"|\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b"),
    # Note the trailing s? on the countable nouns. \bhalving\b does not match
    # "halvings", because \b needs a non-word character and s is a word
    # character. Every plural here has to be spelled out.
    ("named event", r"\b(halvings?|halvenings?|ETFs?|FOMC|CPI|the fed|SEC|MiCA|elections?"
                    r"|ATH|all[- ]time highs?|bull (?:run|market)|bear market"
                    r"|conferences?|meetups?"
                    r"|webinars?|AMA|giveaways?|contests?|black friday|christmas"
                    r"|new year)\b"),
    ("campaign or version", r"\b(v\d+(\.\d+)?|version \d|beta|waitlist|early access"
                            r"|sign ?up now|download now|limited|offer|promo|code:"
                            r"|referral code)\b"),
    # "just launched", "just mined", "just crossed": any recent-action verb,
    # not only the handful worth naming.
    ("just happened", r"\bjust \w+ed\b"),
    ("announcement", r"\b(announcement|announcing|we are announcing|rebrand(?:ing)?"
                     r"|introducing|now available|now live|launching|we(?:'| a)re live"
                     r"|partnership with|welcome to the team|hiring"
                     r"|we(?:'ve| have) (?:decided|added|launched|listed)"
                     r"|(?:added|listed) (?:to|on) our (?:app|platform))\b"),
]


# --- not standalone --------------------------------------------------------

# The archive's best performers include a lot of thread openers and
# engagement bait. Both look strong on likes and neither survives being
# lifted out of context: the payoff of "Bitcoin on exchange is better than
# self-custody. Let me explain why" lives in the replies, and rewriting the
# opener alone produces a line that says the opposite of what Relai means.
# These are dropped at rank time, not handed to the model to untangle.
NOT_STANDALONE = [
    ("thread opener", r"(?:^|\n)\s*(?:1/|1 /|🧵)|\bthread\b|\ba thread\b|\bread on\b"
                      r"|\blet me explain\b|\bhere is why\b|\bhere's why\b"
                      r"|\bhere is how\b|\bhere's how\b|\bbreakdown below\b"
                      r"|\bmore below\b|\bkeep reading\b"),
    ("engagement bait", r"\b(should we|what do you think|agree\?|thoughts\?|who else"
                        r"|drop a |comment |retweet |repost |tag a |like and "
                        r"|follow (?:us|me) |stop scrolling|keep scrolling"
                        r"|continue scrolling|hold my beer|you get a relai"
                        r"|hoodie|merch|t[- ]shirt)"),
    # A question put to the audience is a conversation starter, not a reusable
    # line. The skill's own position: questions are cheap, use them rarely.
    ("audience question", r"^\s*(would you|what would you|what do you|do you|did you"
                          r"|have you|which|who wants|how many of you|tell me|guess"
                          r"|can you|anyone else|am i the only)\b"),
    ("internal or test post", r"\b(test(?:ing)? (?:tweet|post|longer)|ignore this"
                              r"|this is a test|asdf)\b"),
    ("unusable string", r"\bnpub1[a-z0-9]{20,}|\bbc1[a-z0-9]{20,}|\b(?:lnbc|lnurl)[a-z0-9]{20,}"),
]


# --- structural junk -------------------------------------------------------

# Likes reward things that do not survive a rewrite: ASCII art, emoji walls,
# hashtag spam. These are shape checks rather than word checks, so they live
# as numbers here and as code in rank.py.

# Fraction of characters that must be plain letters, digits, spaces or basic
# punctuation. Below this the tweet is mostly box-drawing characters or emoji.
MIN_PLAIN_RATIO = 0.75

# A single word repeated more than this many times is spam, not a sentence.
MAX_TOKEN_REPEAT = 4


# --- mechanical voice checks -----------------------------------------------

# Applied to every generated suggestion. These are the hard rules from
# skills/relai-social-copy/SKILL.md that a regex can decide on its own. A
# match means the suggestion is dropped and regenerated, per the skill's own
# drop-and-regenerate rule.
#
# This is a net, not a substitute for review. Judgment rules (advice framing,
# unverified claims, tone, political association) are not mechanically
# checkable and rely on the model's self-check plus the human review that
# follows. Do not read a clean check as compliance approval.
DROP_CHECKS = [
    ("em dash", r"—|–"),

    ("crypto as a synonym for Bitcoin",
     r"\b(crypto\w*|altcoins?|shitcoins?|meme ?coins?|blockchain|DLT|web3|NFTs?"
     r"|ethereum|cardano|solana|ripple|dogecoin|litecoin|kaspa|monero|tether"
     r"|stablecoins?|ETH|XRP|SOL|ADA|DOGE|LTC|USDT|USDC)\b"),

    ("Bitcoins plural", r"\bBitcoins\b"),

    ("savings plan as a product name", r"\b(savings plan|Sparplan|plan d.épargne)\b"),

    ("yield or capital protection claim",
     r"\b(interest|yield|APY|guaranteed|risk[- ]free|capital protection"
     r"|protect your capital|safely grow)\b"),

    # Deliberately broad. Anything that puts a number, a date, or an outcome
    # in the future is MiCA Art. 66 and EBA/GL/2024/11 territory, and a
    # rewrite cannot keep the idea without keeping the exposure.
    ("forward-looking price framing",
     r"\b(will (?:hit|reach|go to|moon|pump|rise|climb|be worth|only need|need)"
     r"|you will \w+|price target|to the moon|buy the dip|cheaper.{0,20}buy"
     r"|going to \$?\d|next bull|guaranteed return|could (?:become|be worth|reach|hit)"
     r"|in \d+ years?|by 20\d\d|financially free|financial freedom|life[- ]changing"
     r"|get rich|make you rich|retire early"
     # Any framing of a price move as a signal, per the skill's explicit
     # MiCA Art. 66 rule. Covers pumps, dumps, dips, tops and bottoms.
     r"|pump\w*|dump\w*|the dip|price (?:action|move)|going (?:up|down)"
     r"|(?:cycle|market) (?:top|bottom))\b"),

    # "No investment, financial, or legal advice" and "no guaranteed
    # outcomes". Directive buy language and portfolio framing both read as
    # advice to an EU retail audience.
    ("reads as investment advice",
     r"\b(reasons? to buy|why you should (?:buy|own|hold)|you should (?:buy|own|hold)"
     r"|retirement plan|pensions?|mutual funds?|your portfolio|allocation"
     r"|generational wealth|invest now|start investing today)\b"),

    ("past performance claim",
     r"\b(outperformed|beat the market|would have made|would be worth"
     r"|\d+x(?:ed)?\b|best performing)\b"),

    # "No political association with any party or movement." Naming a
    # politician or a central banker is not automatically association, but it
    # is never worth a rewrite.
    ("political or central bank figure",
     r"\b(president|politicians?|senator|congress|parliament|lagarde|powell"
     r"|trump|biden|bukele|ECB|IMF|central bank)\b"),

    # Named competitors only. An earlier, broader "better than \w+" caught
    # "1 bitcoin in self-custody is better than 2 bitcoin on an exchange",
    # which is a core Relai message about custody, not a competitor
    # comparison. Keep this rule narrow.
    ("broker or exchange comparison",
     r"\b(unlike (?:other|most) (?:exchanges|brokers|apps|platforms)"
     r"|(?:better|cheaper|faster|safer) than (?:coinbase|binance|kraken|bitpanda"
     r"|revolut|swissborg|bitcoin suisse|paypal|our competitors)"
     r"|vs\.? ?(?:coinbase|binance|kraken|bitpanda|revolut|swissborg))\b"),

    # A quoted third party with an attribution line is someone else's claim.
    # Relai cannot stand behind it, and it is not Relai voice to rewrite.
    ("third-party quote", r'^\s*["“].*["”]\s*\n+\s*[-–—]\s*\w'),
]

# Terms that do not disqualify a suggestion but need written compliance
# approval before it goes live. Added to the suggestion's flags array.
FLAG_CHECKS = [
    ("savings terminology", r"\b(savings?|saving|Sparen|épargne)\b"),
    ("past performance", r"\b(returned|gained|outperformed|since 20\d\d"
                         r"|over the last \w+ years)\b"),
    ("stack sats, X and merch only",
     r"\b(stack sats|stacking sats|zero[- ]fee stacking)\b"),
]
