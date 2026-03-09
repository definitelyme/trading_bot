import logging
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)

@dataclass
class RiskManager:
    max_portfolio_pct: float = 0.05
    drawdown_24h_limit: float = 0.10
    drawdown_7d_limit: float = 0.20
    min_confidence: float = 0.55
    kelly_fraction: float = 0.25

    _drawdown_24h: float = field(default=0.0, init=False)
    _drawdown_7d: float = field(default=0.0, init=False)
    _circuit_breaker_active: bool = field(default=False, init=False)

    def calculate_position_size(
        self,
        portfolio_value: float,
        confidence: float,
        atr_pct: float,
    ) -> float:
        """
        Quarter-Kelly position sizing adjusted for ATR volatility.
        Returns 0.0 if confidence below minimum threshold.
        """
        if confidence < self.min_confidence:
            return 0.0

        if self._circuit_breaker_active:
            logger.warning("Circuit breaker active — position size forced to 0")
            return 0.0

        # Fractional Kelly: f* = (confidence - (1 - confidence)) * kelly_fraction
        edge = confidence - (1.0 - confidence)
        kelly_bet = max(0.0, edge * self.kelly_fraction)

        # ATR adjustment: reduce size when volatility is high
        # Target 1% portfolio risk per trade; atr_pct is current volatility
        volatility_scalar = min(1.0, 0.02 / max(atr_pct, 0.001))

        raw_size = portfolio_value * kelly_bet * volatility_scalar
        capped_size = min(raw_size, portfolio_value * self.max_portfolio_pct)

        return round(capped_size, 2)

    def record_drawdown(
        self,
        amount: float,
        portfolio_value: float,
        window: Literal["24h", "7d"],
    ) -> None:
        """Record a loss amount and check circuit breakers."""
        drawdown_pct = amount / portfolio_value

        if window == "24h":
            self._drawdown_24h += drawdown_pct
            if self._drawdown_24h >= self.drawdown_24h_limit:
                self._circuit_breaker_active = True
                logger.critical(
                    f"CIRCUIT BREAKER: 24h drawdown {self._drawdown_24h:.1%} "
                    f"exceeded limit {self.drawdown_24h_limit:.1%}"
                )
        elif window == "7d":
            self._drawdown_7d += drawdown_pct
            if self._drawdown_7d >= self.drawdown_7d_limit:
                self._circuit_breaker_active = True
                logger.critical(
                    f"CIRCUIT BREAKER: 7d drawdown {self._drawdown_7d:.1%} "
                    f"exceeded limit {self.drawdown_7d_limit:.1%}"
                )

    def is_circuit_breaker_active(self) -> bool:
        return self._circuit_breaker_active

    def reset_circuit_breaker(self) -> None:
        """Manual reset — requires operator confirmation."""
        self._circuit_breaker_active = False
        self._drawdown_24h = 0.0
        self._drawdown_7d = 0.0
        logger.info("Circuit breaker manually reset")
