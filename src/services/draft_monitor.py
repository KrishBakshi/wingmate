"""Regeneration monitor for outbound drafts.

Persists a per-(template + recipient) counter to a git-ignored JSON log so we
can *actually* tell when the same email has been generated many times, rather
than eyeballing it. When a signature crosses `THRESHOLD` regenerations, the
caller is told to review the relevant skill `SCRATCHPAD.md` and re-check the
draft against `data/identity.yaml` (missed pattern? hallucination? drift?).

This module never raises into the draft path: if the log can't be read or
written, it degrades to a soft result so a monitoring hiccup can never block an
actual Gmail draft.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from config.settings import ROOT_DIR

# On the Nth generation of the *same* email (template + recipient) — i.e. when
# count reaches THRESHOLD — stop, open the skill SCRATCHPAD.md, and figure out
# what's going wrong. Trips ON the 3rd time (>=), not after it.
THRESHOLD = 3

LOG_PATH = ROOT_DIR / "runs" / "draft_monitor.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _signature(template: str, to: Optional[str]) -> str:
    return f"{template}::{(to or 'none').strip().lower()}"


def _load() -> Dict[str, Any]:
    try:
        with LOG_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and isinstance(data.get("entries"), dict):
            return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return {"threshold": THRESHOLD, "entries": {}}


def _save(data: Dict[str, Any]) -> bool:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
        return True
    except OSError:
        return False


def record(template: str, to: Optional[str], threshold: int = THRESHOLD) -> Dict[str, Any]:
    """Record one generation and return the running count + review flag."""

    data = _load()
    sig = _signature(template, to)
    entry = data["entries"].get(sig) or {
        "template": template,
        "to": to,
        "count": 0,
        "first_seen": _now(),
        "history": [],
    }
    entry["count"] += 1
    entry["last_seen"] = _now()
    entry["history"] = (entry.get("history", []) + [entry["last_seen"]])[-20:]
    data["entries"][sig] = entry
    persisted = _save(data)

    over = entry["count"] >= threshold
    result = {
        "signature": sig,
        "template": template,
        "to": to,
        "count": entry["count"],
        "threshold": threshold,
        "over_threshold": over,
        "review_recommended": over,
        "persisted": persisted,
    }
    if over:
        result["review_message"] = (
            f"'{template}' for {to or 'this recipient'} has been generated "
            f"{entry['count']} times (>= {threshold}). Open the relevant skill "
            "SCRATCHPAD.md and re-check against data/identity.yaml: missed "
            "pattern, hallucination, or drift from the identity context?"
        )
    return result


def status(template: Optional[str] = None, to: Optional[str] = None) -> Dict[str, Any]:
    """Return current counts, optionally filtered by template and/or recipient."""

    data = _load()
    entries = []
    for sig, entry in sorted(data["entries"].items()):
        if template and entry.get("template") != template:
            continue
        if to and (entry.get("to") or "").strip().lower() != to.strip().lower():
            continue
        entries.append(
            {
                "signature": sig,
                **{k: entry.get(k) for k in ("template", "to", "count", "first_seen", "last_seen")},
                "over_threshold": entry.get("count", 0) >= THRESHOLD,
            }
        )
    return {"threshold": THRESHOLD, "count": len(entries), "entries": entries}


def reset(template: Optional[str] = None, to: Optional[str] = None) -> Dict[str, Any]:
    """Clear matching counters (or all counters when no filter is given)."""

    data = _load()
    if template is None and to is None:
        removed = len(data["entries"])
        data["entries"] = {}
    else:
        removed = 0
        for sig in list(data["entries"]):
            entry = data["entries"][sig]
            if template and entry.get("template") != template:
                continue
            if to and (entry.get("to") or "").strip().lower() != to.strip().lower():
                continue
            del data["entries"][sig]
            removed += 1
    _save(data)
    return {"removed": removed, "remaining": len(data["entries"])}
