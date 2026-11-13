"""Per-model token prices (USD per 1M tokens) and cost calculation from ``response.usage``.

Source: claude-api skill model table, cached 2026-11-03. Haiku 5.5 price applies to
prompts up to 100K tokens, which every request in this project stays under.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PER_MILLION = 1_000_000


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_write: float
    cache_read: float


PRICES: dict[str, Price] = {
    "claude-fable-5-2": Price(input=8.00, output=40.00, cache_write=10.00, cache_read=0.20),
    "claude-opus-5-5": Price(input=4.00, output=20.00, cache_write=5.00, cache_read=0.20),
    "claude-sonnet-5-5": Price(input=2.00, output=10.00, cache_write=2.50, cache_read=0.10),
    "claude-haiku-5-5": Price(input=0.10, output=0.50, cache_write=0.125, cache_read=0.01),
}


def cost_usd(model: str, usage: Any) -> float:
    """Dollar cost of one response. ``usage`` is a ``response.usage`` object or a dict.

    Output tokens include thinking tokens, which are billed as output.
    """
    if model not in PRICES:
        raise KeyError(f"no price for model {model!r}")
    price = PRICES[model]

    def tokens(name: str) -> int:
        value = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
        return int(value or 0)

    total = (
        tokens("input_tokens") * price.input
        + tokens("output_tokens") * price.output
        + tokens("cache_creation_input_tokens") * price.cache_write
        + tokens("cache_read_input_tokens") * price.cache_read
    )
    return total / PER_MILLION
