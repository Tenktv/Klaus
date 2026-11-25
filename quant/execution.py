"""Gemeinsame Ausfuehrungslogik fuer Backtest-Engine UND Paper-Broker (eine Implementierung von Orderkosten, Sizing, Risikopruefung, Buchung).

Preis- und Kostenmodell: Kauf zahlt ref*(1+slippage), Verkauf erhaelt ref*(1-slippage); Gebuehr = menge*preis*fee_rate je Orderseite."""
from __future__ import annotations

import math

from .portfolio import InsufficientCash, Order, Portfolio
from .risk import RiskManager


def fill_price(side: str, ref_price: float, slippage_rate: float) -> float:
    return ref_price * (1 + slippage_rate) if side == "buy" else ref_price * (1 - slippage_rate)


def commission(qty: float, price: float, fee_rate: float) -> float:
    return qty * price * fee_rate


def size_market_buy(pf: Portfolio, risk: RiskManager, symbol: str, price: float, marks: dict, peak: float, fee_rate: float,
                    target_pct: float, fractional: bool) -> float:
    """Stueckzahl fuer ein Zielgewicht, vorab durch die Risikogrenzen begrenzt (die endgueltige Pruefung macht execute_buy)."""
    ziel = min(target_pct * pf.equity(marks), risk.max_buy_value(pf, symbol, marks, peak))
    qty = ziel / (price * (1 + fee_rate))
    return qty if fractional else float(math.floor(qty + 1e-12))


def execute_buy(pf: Portfolio, risk: RiskManager, o: Order, qty: float, price: float, ref_price: float, fee_rate: float,
                marks: dict, peak: float, when) -> bool:
    """Prueft (Risk Manager) und bucht einen Kauf; setzt Status/Preise der Order. True = ausgefuehrt."""
    o.exec_date, o.ref_open, o.quantity = when, ref_price, qty
    if qty <= 0:
        o.status, o.reason = "rejected", "Ordergroesse 0 (Risikogrenzen, Cash oder Kurs zu hoch)."
        return False
    fee = commission(qty, price, fee_rate)
    dec = risk.check_buy(pf, o.symbol, qty, price, fee, marks, peak)
    if not dec.approved:
        o.status, o.reason = "rejected", " ".join(dec.reasons)
        return False
    try:
        pf.buy(o.symbol, qty, price, fee, when, qty * (price - ref_price))
    except InsufficientCash as e:
        o.status, o.reason = "rejected", str(e)
        return False
    o.exec_price, o.fee, o.slippage_cost, o.status = price, fee, qty * (price - ref_price), "filled"
    return True


def execute_sell(pf: Portfolio, o: Order, qty: float, price: float, ref_price: float, fee_rate: float, when) -> bool:
    o.exec_date, o.ref_open = when, ref_price
    p = pf.positions.get(o.symbol)
    if p is None or qty <= 0:
        o.status, o.reason = "rejected", "Keine Position zum Verkaufen (Long-only)."
        return False
    qty = min(qty, p.quantity)
    fee = commission(qty, price, fee_rate)
    pf.sell(o.symbol, qty, price, fee, when, qty * (ref_price - price))
    o.quantity, o.exec_price, o.fee, o.slippage_cost, o.status = qty, price, fee, qty * (ref_price - price), "filled"
    return True
