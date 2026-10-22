#!/usr/bin/env python3
"""Send a finite, controlled set of synthetic telemetry to a local TraceHunt API.

Examples:
    python scripts/generate_events.py --count 30 --service checkout-api
    python scripts/generate_events.py --base-url http://localhost:8000 --error-rate 0.3

TRACEHUNT_API_URL and TRACEHUNT_API_KEY supply defaults. This writes demo data;
only point it at a workspace where synthetic logs and deployments are welcome.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone


def nonnegative_float(value: str) -> float:
    number = float(value)
    if not 0 <= number < float("inf"):
        raise argparse.ArgumentTypeError("must be finite and nonnegative")
    return number


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def probability(value: str) -> float:
    number = float(value)
    if not 0 <= number <= 1:
        raise argparse.ArgumentTypeError("must be between 0 and 1")
    return number


def post(base_url: str, path: str, payload: dict, api_key: str) -> object:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"API returned HTTP {error.code}: {detail}") from None
    except (urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError(f"API request failed: {error}") from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default=os.getenv("TRACEHUNT_API_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--api-key", default=os.getenv("TRACEHUNT_API_KEY", ""), help="API key (default: TRACEHUNT_API_KEY)")
    parser.add_argument("--count", type=positive_int, default=30, help="Number of log events; always finite (default: 30)")
    parser.add_argument("--interval", type=nonnegative_float, default=0.5, help="Seconds between events (default: 0.5)")
    parser.add_argument("--service", default="checkout-api", help="Synthetic service name (default: checkout-api)")
    parser.add_argument("--error-rate", type=probability, default=0.25, help="Probability of an error, 0 to 1 (default: 0.25)")
    parser.add_argument("--seed", type=int, default=42, help="Reproducible random seed (default: 42)")
    parser.add_argument("--no-deployment", action="store_true", help="Skip the initial synthetic deployment")
    args = parser.parse_args()
    if not args.base_url.startswith(("http://", "https://")):
        parser.error("--base-url must be an http:// or https:// URL")
    if not args.service.strip():
        parser.error("--service must not be empty")

    run_id = uuid.uuid4().hex[:10]
    rng = random.Random(args.seed)
    errors = 0
    sent = 0
    try:
        if not args.no_deployment:
            post(
                args.base_url,
                "/api/v1/deployments",
                {
                    "service": args.service,
                    "version": f"synthetic-{run_id}",
                    "environment": "demo",
                    "status": "success",
                    "commit_sha": run_id,
                },
                args.api_key,
            )
            print(f"Created synthetic deployment for {args.service} ({run_id}).", flush=True)
        for index in range(args.count):
            is_error = rng.random() < args.error_rate
            latency = rng.randint(750, 2400) if is_error else rng.randint(20, 190)
            status_code = 503 if is_error else 200
            post(
                args.base_url,
                "/api/v1/logs",
                {
                    "service": args.service,
                    "level": "error" if is_error else "info",
                    "message": (
                        f"Synthetic database connection timeout after {latency}ms"
                        if is_error else f"Synthetic request completed in {latency}ms"
                    ),
                    "trace_id": uuid.uuid4().hex,
                    "metadata": {
                        "synthetic": True,
                        "generator_run": run_id,
                        "sequence": index + 1,
                        "latency_ms": latency,
                        "status_code": status_code,
                        "route": "/api/checkout",
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                    },
                },
                args.api_key,
            )
            sent += 1
            errors += int(is_error)
            print(f"[{sent}/{args.count}] {'ERROR' if is_error else 'INFO '} {args.service} {latency}ms", flush=True)
            if index + 1 < args.count:
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print(f"\nStopped: sent {sent} logs ({errors} errors).", file=sys.stderr)
        return 130
    except (RuntimeError, ValueError) as error:
        print(f"FAILED after {sent} logs: {error}", file=sys.stderr)
        return 1
    print(f"Done: sent {sent} logs ({errors} errors); run={run_id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
