"""Brand names, in one place.

Every user-visible occurrence of the product or company name should import from
here rather than hard-coding a string. Renaming the product then means editing
this file, not sweeping ~90 strings across two frontends and a Django app.

Note what is deliberately NOT here: the Django app label ``apps.corpus`` and its
tables. "Corpus" there means *the body of law* — a domain term that survives any
rebrand — not the brand.
"""

from __future__ import annotations

# The product: what a user sees in the app, on the consent screen, in emails.
BRAND_NAME = "Hudson Corpus"

# The company. Legal entity name; used where we speak as the operator (Terms,
# contracts, the "operated by" line).
COMPANY_NAME = "Hudson Legal Technologies"

# The MCP server's wire identifier, advertised as serverInfo.name and used as the
# connector key in the install snippet.
#
# Renamed from "iowa-legal-corpus" on 2026-07-13, during the zero-client window:
# no registered OAuth clients and no live tokens existed, so no local client
# config anywhere held the old string and nothing could be orphaned.
#
# That window is now closed. From here this value is FROZEN PERMANENTLY: the
# moment a real client writes it into a config file on a machine we cannot reach
# (`claude mcp add ... hudson-corpus`, claude_desktop_config.json), changing it
# silently breaks their connector with no server-side fix. It must not follow a
# future BRAND_NAME change — it is an opaque key, not a name.
MCP_SERVER_ID = "hudson-corpus"

# How we identify ourselves to servers we crawl (polite-crawler contact string).
CRAWLER_CONTACT = "nick@nickhudson.me"
