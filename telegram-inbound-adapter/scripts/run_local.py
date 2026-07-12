"""Runs the Lambda handler behind a plain HTTP server for local testing.

Reads config/secrets from .env (via telegram_inbound_adapter.settings), then
exposes POST /telegram/webhook by translating each request into the same
event shape API Gateway (HTTP API, payload format 2.0) sends to Lambda.

Usage:
    .venv\\Scripts\\python.exe scripts\\run_local.py [port]

Then tunnel it (e.g. `cloudflared tunnel --url http://localhost:8000`) and
point Telegram's webhook at the tunnel URL + /telegram/webhook.
"""

import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from telegram_inbound_adapter.telemetry import setup_console_telemetry  # noqa: E402

setup_console_telemetry()

from opentelemetry import trace  # noqa: E402

from telegram_inbound_adapter.handler import lambda_handler  # noqa: E402

_REDACTED_HEADERS = {"x-telegram-bot-api-secret-token"}
_tracer = trace.get_tracer(__name__)


class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        headers = dict(self.headers.items())
        event = {
            "headers": headers,
            "body": body,
            "requestContext": {"http": {"method": "POST", "path": self.path}},
        }

        # Root span for the whole request: without it, each boto3/httpx call
        # made while handling it starts its own standalone trace instead of
        # nesting under one -- this is what makes them all share a trace_id.
        with _tracer.start_as_current_span(f"POST {self.path}") as span:
            span.set_attribute("http.request.method", "POST")
            span.set_attribute("url.path", self.path)
            span.set_attribute("http.request.body", body)
            for key, value in headers.items():
                shown = "***redacted***" if key.lower() in _REDACTED_HEADERS else value
                span.set_attribute(f"http.request.header.{key.lower()}", shown)

            response = lambda_handler(event, None)
            span.set_attribute("http.response.status_code", response.get("statusCode", 200))

        self.send_response(response.get("statusCode", 200))
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(response.get("body", "").encode("utf-8"))

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        print(f"[run_local] {self.address_string()} - {format % args}")


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    server = ThreadingHTTPServer(("0.0.0.0", port), WebhookHandler)
    print(f"Listening on http://localhost:{port}  (POST /telegram/webhook)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
