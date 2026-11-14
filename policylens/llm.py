"""Anthropic client factory - the only place the project reads an API key.

Live calls (dataset generation, evals, ``python -m policylens --live``) need ANTHROPIC_API_KEY.
Everything else - demo mode, ``run_eval.py --summary-only``, the tests - runs without a key.

To use a key stored under another name for one command only, without exporting it into your
shell (Git Bash):  ANTHROPIC_API_KEY="$MY_OTHER_KEY_VAR" python -m policylens --live --doc doc_001
The key is never logged or written to disk.
"""

from __future__ import annotations

import os

import anthropic

KEY_ENV_VAR = "ANTHROPIC_API_KEY"
# Used only when ANTHROPIC_API_KEY is unset - lets a machine keep a pay-as-you-go key under its own
# name without exporting ANTHROPIC_API_KEY (which other tools, e.g. Claude Code, also read).
FALLBACK_KEY_ENV_VAR = "ANTHROPIC_API_KEY_PAYG"
REQUEST_TIMEOUT_S = 600.0
MAX_RETRIES = 3

# Server-side refusal fallback (recommended for claude-opus-5-5); usage records which model served.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


def make_client() -> anthropic.Anthropic:
    key = os.environ.get(KEY_ENV_VAR) or os.environ.get(FALLBACK_KEY_ENV_VAR)
    if not key:
        raise SystemExit(f"{KEY_ENV_VAR} (or {FALLBACK_KEY_ENV_VAR}) is not set. Live API calls need it; "
                         "to browse saved results without a key run: python -m policylens")
    return anthropic.Anthropic(api_key=key, timeout=REQUEST_TIMEOUT_S, max_retries=MAX_RETRIES)
