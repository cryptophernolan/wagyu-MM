"""Algorithm abstraction layer for market making quote calculation."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from bot.config import AppConfig


@dataclass
class QuoteContext:
    """All inputs needed by a quoting algorithm."""
    fair_price: Decimal
    inventory: Decimal
    sigma: float  # realized volatility as fraction (e.g. 0.02 = 2%)
    regime: Literal["CALM", "VOLATILE"]
    config: "AppConfig"
    l2_bids: list[tuple[Decimal, Decimal]] = field(default_factory=list)  # (price, size)
    l2_asks: list[tuple[Decimal, Decimal]] = field(default_factory=list)  # (price, size)


@dataclass
class QuoteLevel:
    """A single quote level (one order to place)."""
    price: Decimal
    size: Decimal
    side: Literal["bid", "ask"]


@dataclass
class QuoteSet:
    """Full set of quotes for one cycle."""
    bids: list[QuoteLevel] = field(default_factory=list)
    asks: list[QuoteLevel] = field(default_factory=list)


@runtime_checkable
class QuotingAlgorithm(Protocol):
    """Protocol for all quoting algorithms."""

    @property
    def name(self) -> str:
        """Algorithm name (matches config)."""
        ...

    def compute_quotes(self, ctx: QuoteContext) -> QuoteSet:
        """Compute bid/ask quote levels from context."""
        ...


def get_algorithm(name: str, config: "AppConfig") -> QuotingAlgorithm:
    """Factory — return the configured algorithm instance."""
    from bot.engine.algorithms.avellaneda_stoikov import AvellanedaStoikovAlgorithm
    from bot.engine.algorithms.glft import GLFTAlgorithm
    from bot.engine.algorithms.simple_spread import SimpleSpreadAlgorithm

    algorithms: dict[str, QuotingAlgorithm] = {
        "simple_spread": SimpleSpreadAlgorithm(config),
        "avellaneda_stoikov": AvellanedaStoikovAlgorithm(config),
        "glft": GLFTAlgorithm(config),
    }
    if name not in algorithms:
        raise ValueError(f"Unknown algorithm: {name!r}. Valid: {list(algorithms.keys())}")
    return algorithms[name]
