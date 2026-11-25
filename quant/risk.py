"""Risk Manager: unabhaengig von Strategie und KI. Kann Kaeufe nur begrenzen oder ablehnen - nie erweitern. Verkaeufe sind immer erlaubt.

Alle Prozentwerte beziehen sich auf den Gesamtwert (Equity) vor der Order, bewertet mit den uebergebenen Marken."""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import RiskConfig
from .portfolio import Portfolio

TOL = 1e-9


@dataclass
class RiskDecision:
    approved: bool
    reasons: list = field(default_factory=list)


class RiskManager:
    def __init__(self, config: RiskConfig | None = None):
        self.config = config or RiskConfig()

    # --- Vorab-Begrenzung der Ordergroesse (damit normale Signale nicht dauernd abgelehnt werden) ---------------
    def max_buy_value(self, pf: Portfolio, symbol: str, marks: dict[str, float], peak_equity: float | None = None) -> float:
        """Groesstes Ordervolumen (ohne Gebuehren), das alle Grenzen noch einhaelt. 0 = kein Kauf moeglich."""
        c = self.config
        eq = pf.equity(marks)
        grenzen = [pf.cash]
        if c.max_position_pct is not None:
            bestehend = pf.positions[symbol].quantity * marks.get(symbol, pf.positions[symbol].last_price) if symbol in pf.positions else 0.0
            grenzen.append(c.max_position_pct * eq - bestehend)
        if c.min_cash_pct is not None:
            grenzen.append(pf.cash - c.min_cash_pct * eq)
        if c.max_exposure_pct is not None:
            grenzen.append(c.max_exposure_pct * eq - pf.invested(marks))
        if c.max_risk_per_position_pct is not None:
            stopp = c.stop_loss_pct or 1.0
            bestehend = pf.positions[symbol].quantity * marks.get(symbol, pf.positions[symbol].last_price) if symbol in pf.positions else 0.0
            grenzen.append(c.max_risk_per_position_pct * eq / stopp - bestehend)
        return max(0.0, min(grenzen))

    # --- Endgueltige Pruefung ----------------------------------------------------------------------------------
    def check_buy(self, pf: Portfolio, symbol: str, qty: float, price: float, fee: float, marks: dict[str, float], peak_equity: float | None = None) -> RiskDecision:
        c, gruende = self.config, []
        eq = pf.equity(marks)
        wert = qty * price
        bestehend = pf.positions[symbol].quantity * marks.get(symbol, pf.positions[symbol].last_price) if symbol in pf.positions else 0.0
        if qty <= 0 or price <= 0:
            gruende.append("Ungueltige Ordergroesse.")
        if wert + fee > pf.cash + TOL:
            gruende.append(f"Nicht genug Cash ({pf.cash:.2f} < {wert + fee:.2f}).")
        if eq <= 0:
            gruende.append("Kein Kapital.")
        else:
            if c.max_position_pct is not None and (bestehend + wert) / eq > c.max_position_pct + TOL:
                gruende.append(f"Positionsgroesse {(bestehend + wert) / eq:.1%} > {c.max_position_pct:.1%}.")
            if c.min_cash_pct is not None and (pf.cash - wert - fee) / eq < c.min_cash_pct - TOL:
                gruende.append(f"Cash-Reserve {(pf.cash - wert - fee) / eq:.1%} < {c.min_cash_pct:.1%}.")
            if c.max_exposure_pct is not None and (pf.invested(marks) + wert) / eq > c.max_exposure_pct + TOL:
                gruende.append(f"Gesamtinvestition {(pf.invested(marks) + wert) / eq:.1%} > {c.max_exposure_pct:.1%}.")
            if c.max_risk_per_position_pct is not None and (bestehend + wert) * (c.stop_loss_pct or 1.0) / eq > c.max_risk_per_position_pct + TOL:
                gruende.append(f"Risiko je Position {(bestehend + wert) * (c.stop_loss_pct or 1.0) / eq:.2%} > {c.max_risk_per_position_pct:.2%}.")
        if c.max_open_positions is not None and symbol not in pf.positions and len(pf.positions) + 1 > c.max_open_positions:
            gruende.append(f"Mehr als {c.max_open_positions} offene Positionen.")
        if c.max_drawdown_pct is not None and peak_equity and eq > 0:
            dd = 1 - eq / peak_equity
            if dd >= c.max_drawdown_pct - TOL:
                gruende.append(f"Drawdown {dd:.1%} >= Limit {c.max_drawdown_pct:.1%}: keine neuen Kaeufe.")
        return RiskDecision(not gruende, gruende)
