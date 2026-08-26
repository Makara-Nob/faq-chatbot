"""
Central logging configuration.

WHY THIS FILE EXISTS
--------------------
Python's `logging` is meant to be configured ONCE, as early as possible, for
the whole process. If lots of modules each call `logging.basicConfig(...)`,
only the first one wins and the rest are silently ignored - and under a real
server (uvicorn/gunicorn) the server configures logging first, so your format
never applies at all. So we describe the entire logging setup in one dictionary
and hand it to `logging.config.dictConfig()`. That is the standard, predictable
way to configure logging in a Python app.

    JAVA: this file is your logback.xml / log4j2.xml.

TWO OUTPUT SHAPES
-----------------
- human-readable (dev/staging): one tidy line you can read with your eyes.
      2026-08-26T06:46:42Z INFO     [faq-api] request_id=... GET /health -> 200
- JSON (production): one JSON object per line, so log tooling can index and
  search every field (request_id, status, latency_ms, ...).
      {"timestamp": "...", "level": "INFO", "logger": "faq-api", "message": ...}

Which one you get is decided by Settings.log_as_json (JSON in prod by default).

WHERE LOGS GO
-------------
Everything is written to STDOUT and nothing else. In a container the platform
(Docker, Kubernetes, ECS, ...) collects stdout and ships it to your log store.
This is the standard "12-factor app" approach and means we never have to manage
log files or rotation inside the app.
"""

import logging
import logging.config
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Imported only for type hints - avoids a real import cycle at runtime.
    from app.core.config import Settings


# ISO-8601 timestamp. Because we force UTC below, the trailing "Z" (meaning
# "Zulu"/UTC) is accurate. Logging in UTC is a must once you run in more than
# one region - otherwise you can't line up events across machines.
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

# The %(...)s placeholders are LogRecord attributes filled in by the logging
# module. For the JSON formatter this same string just tells python-json-logger
# WHICH fields to include; we rename them to nicer keys below.
_CONSOLE_FORMAT = "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"
_JSON_FIELDS = "%(asctime)s %(levelname)s %(name)s %(message)s"


def setup_logging(settings: "Settings") -> None:
    """
    Configure logging for the whole process. Call this ONCE, at startup,
    before anything logs.
    """
    # Make EVERY formatter render timestamps in UTC rather than the machine's
    # local time zone. `converter` is a hook the stdlib formatter calls to turn
    # an epoch time into a time-struct; `time.gmtime` == UTC.
    logging.Formatter.converter = time.gmtime

    level = settings.log_level  # already validated + upper-cased in config.py
    formatter = "json" if settings.log_as_json else "console"

    config = {
        "version": 1,
        # Keep loggers created before this call (e.g. uvicorn's) alive instead
        # of silencing them.
        "disable_existing_loggers": False,
        "formatters": {
            "console": {
                "format": _CONSOLE_FORMAT,
                "datefmt": _DATE_FORMAT,
            },
            "json": {
                # "()" means "build this formatter with the given factory".
                "()": "pythonjsonlogger.json.JsonFormatter",
                "format": _JSON_FIELDS,
                "datefmt": _DATE_FORMAT,
                # Give the default attribute names friendlier JSON keys.
                "rename_fields": {
                    "asctime": "timestamp",
                    "levelname": "level",
                    "name": "logger",
                },
            },
        },
        "handlers": {
            # A handler is "where do log records go". One stdout stream for all.
            "stdout": {
                "class": "logging.StreamHandler",
                "formatter": formatter,
                "stream": "ext://sys.stdout",
            },
        },
        # The root logger is the parent of every logger; our app loggers
        # inherit its handler + level.
        "root": {
            "level": level,
            "handlers": ["stdout"],
        },
        "loggers": {
            # Re-point uvicorn's own loggers at OUR handler so its lines share
            # the same format (JSON in prod) instead of uvicorn's default.
            "uvicorn": {"level": level, "handlers": ["stdout"], "propagate": False},
            "uvicorn.error": {
                "level": level,
                "handlers": ["stdout"],
                "propagate": False,
            },
            # uvicorn.access logs one line per request already. OUR middleware
            # logs a richer access line (with request_id + latency), so we mute
            # uvicorn's version to WARNING to avoid two access logs per request.
            "uvicorn.access": {
                "level": "WARNING",
                "handlers": ["stdout"],
                "propagate": False,
            },
        },
    }

    logging.config.dictConfig(config)
