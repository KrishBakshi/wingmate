from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


ROOT_DIR = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = Path(os.getenv("TEMPLATES_DIR", ROOT_DIR / "templates"))
GMAIL_CREDENTIALS_PATH = Path(
    os.getenv("GMAIL_CREDENTIALS_PATH", ROOT_DIR / "credentials.json")
)
GMAIL_TOKEN_PATH = Path(os.getenv("GMAIL_TOKEN_PATH", ROOT_DIR / "token.json"))

# Template conformance gate on send (see services/template_matcher.py).
# THRESHOLD: fraction of a template's fixed wording a body must reproduce to
# count as "sent from that template". MIN_BLOCK: shortest shared run of
# characters that counts, so incidental words cannot add up to a pass.
TEMPLATE_MATCH_THRESHOLD = float(os.getenv("TEMPLATE_MATCH_THRESHOLD", "0.75"))
TEMPLATE_MATCH_MIN_BLOCK = int(os.getenv("TEMPLATE_MATCH_MIN_BLOCK", "8"))

# Identity retrieval (see services/identity_service.py). One file, two sections:
# `public` is work history and proof of work, free to quote in outbound;
# `private` is contact and negotiation detail, and retrieval of it is gated so
# nothing in it reaches a recipient without the user answering for it first.
DATA_DIR = Path(os.getenv("DATA_DIR", ROOT_DIR / "data"))
IDENTITY_PATH = Path(os.getenv("IDENTITY_PATH", DATA_DIR / "identity.yaml"))
