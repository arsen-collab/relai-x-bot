#!/usr/bin/env python3
"""
Mechanical compliance checks, shared by every suggester in this repo.

These are the hard rules from skills/relai-social-copy/SKILL.md that a regex
can decide on its own. A match means the suggestion is dropped and
regenerated, per the skill's own drop-and-regenerate rule.

This is a net, not a substitute for review. Judgment rules (advice framing,
unverified claims, tone, political association) are not mechanically checkable
and rely on the model's self-check plus the human review that follows. Do not
read a clean check as compliance approval.

Lives at the repo root, next to x_api.py, for the same reason: two copies of
the compliance patterns would drift, and the drift would be silent. Both
weekly-suggester/config.py and visual-suggester/config.py import from here.
Changing a pattern here changes both, which is the point.

stdlib only, and no imports at all, so the system Python 3.9 that runs rank.py
offline on a Mac loads it as happily as the runner's 3.12.
"""

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
