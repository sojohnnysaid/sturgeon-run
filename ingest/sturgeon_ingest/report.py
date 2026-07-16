"""Data-quality report assembly and writing."""
from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("sturgeon_ingest.report")


def make_run_id() -> str:
    """e.g. 20260715T2236Z-ab12cd"""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")
    suffix = secrets.token_hex(3)
    return f"{stamp}-{suffix}"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_source_report(
    source: str,
    snapshot_mode: bool,
    records_fetched: int,
    records_kept: int,
    drop_reasons: dict[str, int],
    notes: str,
) -> dict:
    # Only surface non-zero drop reasons for a clean report.
    reasons = {k: v for k, v in drop_reasons.items() if v}
    records_dropped = sum(reasons.values())
    return {
        "source": source,
        "snapshot_mode": snapshot_mode,
        "records_fetched": records_fetched,
        "records_kept": records_kept,
        "records_dropped": records_dropped,
        "drop_reasons": reasons,
        "notes": notes,
    }


def build_report(run_id: str, snapshot_mode: bool, sources: list[dict]) -> dict:
    return {
        "run_id": run_id,
        "generated_at": now_iso(),
        "snapshot_mode": snapshot_mode,
        "sources": sources,
    }


def write_report(report: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    log.info("Wrote quality report: %s", path)
