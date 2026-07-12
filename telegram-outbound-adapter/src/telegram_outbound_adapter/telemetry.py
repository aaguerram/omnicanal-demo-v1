"""Console-only OpenTelemetry setup for local development (see scripts/run_local.py).

Not used by the deployed Lambda — handler.py never imports this module, so
production behavior and cold-start time are unaffected.
"""

import json
import logging
import re

from opentelemetry import metrics as metrics_api
from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import ConsoleLogExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

_SENSITIVE_KEY = re.compile(r"token|secret", re.IGNORECASE)
_TELEGRAM_BOT_TOKEN_IN_URL = re.compile(r"/bot[^/]+/")
_ATTR_VALUE_LIMIT = 4000

# HTTP header redaction is name-based, not content-based: the secret lives in
# the *value* of an innocuously-named header like "authorization", so the
# key-pattern matching _redact() does for JSON bodies (matching keys like
# "connection_token") wouldn't catch it.
_SENSITIVE_HEADER_NAMES = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "x-telegram-bot-api-secret-token",
}


def _redact_headers(headers: dict) -> dict:
    return {
        key: "***redacted***" if key.lower() in _SENSITIVE_HEADER_NAMES else value
        for key, value in headers.items()
    }


def _redact(value):
    """Recursively masks dict values whose key looks like a token/secret."""
    if isinstance(value, dict):
        return {
            key: "***redacted***" if _SENSITIVE_KEY.search(key) else _redact(val)
            for key, val in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _json_attr(value) -> str:
    return json.dumps(_redact(value), default=str)[:_ATTR_VALUE_LIMIT]


def _botocore_request_hook(span, service_name, operation_name, api_params) -> None:
    span.set_attribute("aws.request.params", _json_attr(api_params))


def _botocore_response_hook(span, service_name, operation_name, result) -> None:
    span.set_attribute("aws.response.result", _json_attr(result))


def _httpx_request_hook(span, request) -> None:
    method, url, headers, stream, extensions = request
    # TelegramClient puts the bot token in the URL path (/bot<token>/sendMessage) --
    # the instrumentation records the raw URL by default, which would otherwise leak
    # the token into every span attribute (console + saved log files).
    redacted_url = _TELEGRAM_BOT_TOKEN_IN_URL.sub("/bot***redacted***/", str(url))
    span.set_attribute("http.url", redacted_url)
    span.set_attribute("url.full", redacted_url)
    if headers is not None:
        span.set_attribute(
            "http.request.headers", _json_attr(_redact_headers(dict(headers.items())))
        )


def _httpx_response_hook(span, request, response) -> None:
    status_code, headers, stream, extensions = response
    if headers is not None:
        span.set_attribute(
            "http.response.headers", _json_attr(_redact_headers(dict(headers.items())))
        )


def setup_console_telemetry() -> None:
    # Runs before handler.py's own logging.basicConfig(), which is a no-op once
    # the root logger already has a handler — so set the plain console handler
    # and level here, otherwise INFO logs get silently dropped everywhere.
    logging.basicConfig(level=logging.INFO)

    trace.set_tracer_provider(TracerProvider())
    trace.get_tracer_provider().add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

    metrics_api.set_meter_provider(
        MeterProvider(
            metric_readers=[
                PeriodicExportingMetricReader(
                    ConsoleMetricExporter(), export_interval_millis=5000
                )
            ]
        )
    )

    logger_provider = LoggerProvider()
    logger_provider.add_log_record_processor(SimpleLogRecordProcessor(ConsoleLogExporter()))
    set_logger_provider(logger_provider)
    logging.getLogger().addHandler(LoggingHandler(logger_provider=logger_provider))

    LoggingInstrumentor().instrument(set_logging_format=True)
    BotocoreInstrumentor().instrument(
        request_hook=_botocore_request_hook, response_hook=_botocore_response_hook
    )
    HTTPXClientInstrumentor().instrument(
        request_hook=_httpx_request_hook, response_hook=_httpx_response_hook
    )
