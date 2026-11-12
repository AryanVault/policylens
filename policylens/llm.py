"""Anthropic client factory.

Uses the pay-as-you-go key from ANTHROPIC_API_KEY_PAYG (never ANTHROPIC_API_KEY, which
would change Claude Code's own billing). The key is never logged or written to disk.
"""

from __future__ import annotations

import os

import anthropic

KEY_ENV_VAR = "ANTHROPIC_API_KEY_PAYG"
REQUEST_TIMEOUT_S = 600.0
MAX_RETRIES = 3

# Server-side refusal fallback (recommended for claude-opus-5-5); usage records which model served.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


def make_client() -> anthropic.Anthropic:
    key = os.environ.get(KEY_ENV_VAR)
    if not key:
        raise SystemExit(f"{KEY_ENV_VAR} is not set in this process's environment")
    return anthropic.Anthropic(api_key=key, timeout=REQUEST_TIMEOUT_S, max_retries=MAX_RETRIES)
