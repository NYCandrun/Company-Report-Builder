"""In-process execution of deterministic work items.

Work that needs no judgment, such as crawling the first-party site, capturing
ordinary pages and PDFs, and the single-writer reducers, runs inside
``research_control run`` instead of being dispatched to agent workers. It uses
the same scheduler lease, ledger, output-hash, and receipt contracts as agent
work, under the reserved worker identity ``runtime-executor``.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from research_control.capture import auto_capture_source
from research_control.discovery import DiscoveryEngine
from research_control.io import atomic_write_json, load_json, workflow
from research_control.media import is_media_url
from research_control.provision import engine_fingerprint
from research_control.reducers import reduce_capture_parts, reduce_discovery, reduce_extraction_parts
from research_control.runtime import RuntimeStore


RUNTIME_WORKER = "runtime-executor"


def _write_channel_receipt(root: Path, store: RuntimeStore, channel: str, relative: str) -> None:
    current = store.discovery_channel(channel)
    if not current or current["state"] == "open":
        raise ValueError(f"discovery channel is not terminal: {channel}")
    atomic_write_json(root / relative, {
        "schema_version": "1.0.0",
        "channel": channel,
        "status": current["state"],
        "passes": current["total_passes"],
        "new_sources": current["total_new_sources"],
        "evidence": current["completion_evidence"],
    })


def _first_party_discovery(root: Path, store: RuntimeStore, task: dict[str, Any]) -> dict[str, Any]:
    """Crawl the company host and/or audit its sitemaps, then write channel receipts."""
    channels = task["metadata"]["channels"]
    engine = DiscoveryEngine(root, store)
    engine.initialize()
    result: dict[str, Any] = {}
    if "company_site" in channels:
        result["seeded_sitemaps"] = engine.seed_sitemaps()
        rounds: list[dict[str, Any]] = []
        for _round in range(6):
            while True:
                crawl = engine.crawl_company_site()
                if crawl["status"] in {"saturated", "incomplete", "blocked"}:
                    break
            rounds.append({"crawl": crawl["status"], "fetched": crawl["pages_fetched"]})
            if crawl["status"] != "saturated":
                break
            # Sitemap URLs the link crawl missed feed the next crawl round.
            cached = engine.audit_sitemaps(refetch=False)
            fresh = engine.audit_sitemaps(refetch=True)
            if not cached["new_source_ids"] and not fresh["new_source_ids"]:
                break
        result["rounds"] = rounds
    if "sitemaps" in channels:
        for refetch in (False, True, False, True):
            if (store.discovery_channel("sitemaps") or {}).get("state") != "open":
                break
            engine.audit_sitemaps(refetch=refetch)
        if (store.discovery_channel("sitemaps") or {}).get("state") == "open":
            store.set_discovery_channel(
                "sitemaps", "incomplete", "sitemap audit kept finding new URLs; crawl the new branch first"
            )
    engine.write_catalog()
    for channel, receipt in zip(channels, task["metadata"]["receipts"]):
        _write_channel_receipt(root, store, channel, receipt)
    return result


def _capture(root: Path, store: RuntimeStore, task: dict[str, Any]) -> dict[str, Any]:
    source = store.source(task["metadata"]["source_id"])
    if not source:
        raise KeyError(f"unknown source: {task['metadata']['source_id']}")
    grade = "S" if source["channel"] == "independent_web" else "P"
    media = source["channel"] in {"video", "podcasts"} or is_media_url(source["canonical_url"])
    receipt = auto_capture_source(
        root, url=source["canonical_url"], source_id=source["source_id"], grade=grade, store=store, media=media,
    )
    # Record which policy, prompts, and engine were in force for this capture.
    path = root / task["metadata"]["receipt"]
    stored = load_json(path)
    stored["policy"] = engine_fingerprint(root)
    atomic_write_json(path, stored)
    return receipt


HANDLERS: dict[str, Callable[[Path, RuntimeStore, dict[str, Any]], Any]] = {
    "source_discovery": _first_party_discovery,
    "discovery_reducer": lambda root, store, _task: reduce_discovery(root, store),
    "capture": _capture,
    "capture_reducer": lambda root, store, _task: reduce_capture_parts(root, store),
    "extraction_reducer": lambda root, _store, _task: reduce_extraction_parts(root),
}


def run_automatic(
    root: Path,
    store: RuntimeStore,
    phases: list[str],
    complete: Callable[[RuntimeStore, dict[str, Any], str], Any],
    replan: Callable[[], Any],
) -> dict[str, Any]:
    """Execute every ready runtime-owned task in ``phases`` until none remain.

    ``phases`` is the current phase plus the phases before it, so deterministic
    work that went stale after its phase closed is redone automatically.
    """
    interval = float(
        workflow(root / "WORKFLOW.yaml").get("adaptive_runtime", {}).get("discovery", {})
        .get("min_host_interval_seconds", 1.0)
    )
    executed: list[str] = []
    failed: list[dict[str, str]] = []
    last_host: dict[str, float] = {}
    while True:
        store.refresh_ready()
        ready = [
            task for task in store.tasks(states={"ready", "retryable"})
            if task["metadata"].get("executor") == "runtime" and task["phase"] in phases
        ]
        if not ready:
            break
        for task in ready:
            handler = HANDLERS.get(task["task_type"])
            if handler is None:
                raise ValueError(f"{task['task_id']}: no runtime handler for task type {task['task_type']}")
            if not store.claim(RUNTIME_WORKER, task_id=task["task_id"], bypass_limits=True):
                continue
            store.start(task["task_id"], RUNTIME_WORKER)
            if task["task_type"] == "capture" and task["host_key"]:
                wait = interval - (time.monotonic() - last_host.get(task["host_key"], 0.0))
                if wait > 0:
                    time.sleep(wait)
                last_host[task["host_key"]] = time.monotonic()
            try:
                handler(root, store, task)
                complete(store, store.task(task["task_id"]) or task, RUNTIME_WORKER)
                executed.append(task["task_id"])
            except Exception as error:  # record the concrete failure; the scheduler decides retry
                failed.append({"task_id": task["task_id"], "reason": f"{type(error).__name__}: {error}"})
                current = store.task(task["task_id"])
                if current and current["state"] in {"leased", "running", "validating"}:
                    store.fail(task["task_id"], RUNTIME_WORKER, f"{type(error).__name__}: {error}")
        replan()
    return {"executed": len(executed), "failed": failed}
