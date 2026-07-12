"""Invokes the Lambda handler directly for local testing, with OpenTelemetry
console output wired up first (see telemetry.py).

Reads config/secrets from .env (via telegram_outbound_adapter.settings).
Unlike telegram-inbound-adapter (HTTP webhook), this Lambda is SNS-triggered,
so there's no server to run -- instead this loads a JSON file shaped like the
SNS event Lambda receives and invokes the handler with it directly.

Usage:
    .venv\\Scripts\\python.exe scripts\\run_local.py scripts\\sample_sns_event.json
    type scripts\\sample_sns_event.json | .venv\\Scripts\\python.exe scripts\\run_local.py -
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from telegram_outbound_adapter.telemetry import setup_console_telemetry  # noqa: E402

setup_console_telemetry()

from opentelemetry import trace  # noqa: E402

from telegram_outbound_adapter.handler import lambda_handler  # noqa: E402

_tracer = trace.get_tracer(__name__)


def _load_event(path: str) -> dict:
    if path == "-":
        return json.loads(sys.stdin.read())
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(1)

    event = _load_event(sys.argv[1])

    # Root span for the whole invocation: without it, each boto3/httpx call
    # made while handling it starts its own standalone trace instead of
    # nesting under one.
    with _tracer.start_as_current_span("run_local invoke") as span:
        span.set_attribute("event", json.dumps(event)[:4000])
        response = lambda_handler(event, None)
        span.set_attribute("response", json.dumps(response)[:4000])

    print(f"[run_local] response: {response}")
    # Give the periodic metric exporter (5s interval, see telemetry.py) a
    # chance to flush before the process exits.
    time.sleep(6)


if __name__ == "__main__":
    main()
