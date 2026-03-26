"""
wrapper.py — Centralised logging setup for the ERP Agent stack.

Usage:
    from wrapper import get_logger
    logger = get_logger(__name__)
    logger.info("something happened")

Also exposes:
    @log_call          — sync decorator: logs entry + exit/error for any function
    @log_async_call    — async version of the same
    @log_async_exceptions — legacy pass-through (kept for compatibility)
"""
import functools
import logging
import os
import sys
import time
from pathlib import Path

# ── Log file path ──────────────────────────────────────────────────────────
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "agent.log"

# ── Formatter ──────────────────────────────────────────────────────────────
LOG_FORMAT = "%(asctime)s  %(levelname)-8s  [%(name)s]  %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ── Root handler (set up once) ─────────────────────────────────────────────
def _configure_root_logger():
    root = logging.getLogger("erp")
    if root.handlers:           # already configured — don't add twice
        return
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # Console — INFO and above
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    # File — DEBUG and above (full trace)
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

_configure_root_logger()


def get_logger(name: str) -> logging.Logger:
    """
    Return a child logger under the 'erp' namespace.
    e.g. get_logger("agent.service") → logger named 'erp.agent.service'
    """
    return logging.getLogger(f"erp.{name}")


# ── Decorators ─────────────────────────────────────────────────────────────

def log_call(func):
    """
    Sync decorator.  Logs:
      → ENTER with args summary
      ← EXIT  with elapsed time
      ✗ ERROR with exception message (then re-raises)
    """
    logger = get_logger(func.__module__)

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        label = func.__qualname__
        logger.debug("→ %s called", label)
        t0 = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            elapsed = (time.perf_counter() - t0) * 1000
            logger.debug("← %s done in %.0f ms", label, elapsed)
            return result
        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            logger.error("✗ %s failed after %.0f ms — %s: %s",
                         label, elapsed, type(exc).__name__, exc)
            raise
    return wrapper


def log_async_call(func):
    """Async version of log_call."""
    logger = get_logger(func.__module__)

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        label = func.__qualname__
        logger.debug("→ %s called", label)
        t0 = time.perf_counter()
        try:
            result = await func(*args, **kwargs)
            elapsed = (time.perf_counter() - t0) * 1000
            logger.debug("← %s done in %.0f ms", label, elapsed)
            return result
        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            logger.error("✗ %s failed after %.0f ms — %s: %s",
                         label, elapsed, type(exc).__name__, exc)
            raise
    return wrapper


# Legacy — kept so existing imports don't break
def log_async_exceptions(func):
    """Legacy pass-through: logs unhandled async exceptions then re-raises."""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            get_logger(func.__module__).error(
                "Async exception in %s: %s", func.__name__, e
            )
            raise
    return wrapper
