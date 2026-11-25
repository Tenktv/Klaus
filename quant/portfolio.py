"""Portfolio, Positionen, Orders, Trades. Long-only; Cash kann nie negativ werden.

Buchhaltung: Kauf: cash -= menge*preis + gebuehr. Verkauf: cash += menge*preis - gebuehr.
Realisierter P/L (netto) = (verkaufspreis - einstand)*menge - verkaufsgebuehr - anteilige Einstiegsgebuehren.
Unrealisiert = menge*(kurs - einstand) - noch nicht realisierte Einstiegsgebuehren.
Identitaet (wird getestet): equity = initial_cash + realisiert + unrealisiert + dividenden."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

EPS = 1e-9


class PortfolioError(Exception):
    pass


class InsufficientCash(PortfolioError):
    pass


@dataclass
class Order:
    id: int
    symbol: str
    side: str                       # buy | sell
    signal_date: date               # Kerze, auf deren Schluss das Signal beruht
    strategy: str = ""
    quantity: float | None = None   # None = wird bei der Ausfuehrung bestimmt
    status: str = "pending"         # pending | filled | rejected | expired
    exec_date: date | None = None
    ref_open: float | None = None   # Open der Ausfuehrungskerze (roh)
    exec_price: float | None = None  # inkl. Slippage
    fee: float = 0.0
    slippage_cost: float = 0.0
    reason: str = ""
    order_type: str = "market"        # market | limit | stop (Paper-Broker; der Backtest nutzt market)
    limit_price: float | None = None
    stop_price: float | None = None
    time_in_force: str = "gtc"        # day | gtc
    bars_open: int = 0


@dataclass
class Position:
    symbol: str
    quantity: float
    avg_entry_price: float
    entry_date: date
    last_price: float
    fees_paid: float = 0.0          # noch nicht realisierte Einstiegsgebuehren
    slippage_cost: float = 0.0      # Slippage der Einstiege (informativ; steckt schon im Einstandskurs)
    realized_pnl: float = 0.0       # bereits realisierter Teil (bei Teilverkaeufen)

    @property
    def market_value(self) -> float:
        return self.quantity * self.last_price

    @property
    def cost_basis(self) -> float:
        return self.quantity * self.avg_entry_price

    @property
    def unrealized_pnl(self) -> float:
        return self.quantity * (self.last_price - self.avg_entry_price) - self.fees_paid


@dataclass
class Trade:
    symbol: str
    entry_date: date
    exit_date: date
    quantity: float
    entry_price: float
    exit_price: float
    pnl: float                      # netto inkl. Gebuehren
    fees: float
    holding_days: int

    @property
    def return_pct(self) -> float:
        basis = self.quantity * self.entry_price
        return self.pnl / basis if basis else 0.0


class Portfolio:
    def __init__(self, initial_cash: float):
        if initial_cash <= 0:
            raise PortfolioError("Startkapital muss > 0 sein.")
        self.initial_cash = float(initial_cash)
        self.cash = float(initial_cash)
        self.positions: dict[str, Position] = {}
        self.realized_pnl = 0.0
        self.dividends_total = 0.0
        self.fees_total = 0.0
        self.slippage_total = 0.0
        self.trades: list[Trade] = []
        self.dividend_log: list[dict] = []
        self.split_log: list[dict] = []
        self.equity_curve: list[dict] = []

    # --- Bewertung -------------------------------------------------------------------------------------------
    def mark(self, prices: dict[str, float]) -> None:
        for s, p in self.positions.items():
            if s in prices:
                p.last_price = float(prices[s])

    def invested(self, marks: dict[str, float] | None = None) -> float:
        return sum(p.quantity * (marks or {}).get(s, p.last_price) for s, p in self.positions.items())

    def equity(self, marks: dict[str, float] | None = None) -> float:
        return self.cash + self.invested(marks)

    @property
    def unrealized_pnl(self) -> float:
        return sum(p.unrealized_pnl for p in self.positions.values())

    # --- Ausfuehrung -----------------------------------------------------------------------------------------
    def buy(self, symbol: str, qty: float, price: float, fee: float, when: date, slippage_cost: float = 0.0) -> None:
        if qty <= 0 or price <= 0 or fee < 0:
            raise PortfolioError("Ungueltiger Kauf.")
        kosten = qty * price + fee
        if kosten > self.cash + EPS:
            raise InsufficientCash(f"Cash {self.cash:.2f} reicht nicht fuer {kosten:.2f}.")
        self.cash -= kosten
        self.fees_total += fee
        self.slippage_total += slippage_cost
        p = self.positions.get(symbol)
        if p is None:
            self.positions[symbol] = Position(symbol, qty, price, when, price, fees_paid=fee, slippage_cost=slippage_cost)
        else:
            gesamt = p.quantity + qty
            p.avg_entry_price = (p.avg_entry_price * p.quantity + price * qty) / gesamt
            p.quantity, p.last_price = gesamt, price
            p.fees_paid += fee
            p.slippage_cost += slippage_cost

    def sell(self, symbol: str, qty: float, price: float, fee: float, when: date, slippage_cost: float = 0.0) -> Trade:
        p = self.positions.get(symbol)
        if p is None or qty <= 0 or qty > p.quantity + EPS:
            raise PortfolioError(f"Verkauf von {qty} {symbol} nicht moeglich (Long-only, keine Leerverkaeufe).")
        qty = min(qty, p.quantity)
        anteil = qty / p.quantity
        einstiegsgebuehr = p.fees_paid * anteil
        pnl = (price - p.avg_entry_price) * qty - fee - einstiegsgebuehr
        self.cash += qty * price - fee
        self.fees_total += fee
        self.slippage_total += slippage_cost
        self.realized_pnl += pnl
        p.realized_pnl += pnl
        p.fees_paid -= einstiegsgebuehr
        trade = Trade(symbol, p.entry_date, when, qty, p.avg_entry_price, price, pnl, fee + einstiegsgebuehr, (when - p.entry_date).days)
        self.trades.append(trade)
        p.quantity -= qty
        p.last_price = price
        if p.quantity <= EPS:
            del self.positions[symbol]
        return trade

    # --- Corporate Actions -----------------------------------------------------------------------------------
    def apply_split(self, symbol: str, ratio: float, when: date) -> None:
        """Stuecke * ratio, Einstand / ratio: Gesamtwert und P/L bleiben unveraendert."""
        p = self.positions.get(symbol)
        if p is None:
            return
        wert_vorher = p.market_value
        p.quantity *= ratio
        p.avg_entry_price /= ratio
        p.last_price /= ratio
        self.split_log.append({"date": when, "symbol": symbol, "ratio": ratio, "value_before": wert_vorher, "value_after": p.market_value})

    def apply_dividend(self, symbol: str, per_share: float, when: date) -> float:
        p = self.positions.get(symbol)
        if p is None:
            return 0.0
        betrag = p.quantity * per_share
        self.cash += betrag
        self.dividends_total += betrag
        self.dividend_log.append({"date": when, "symbol": symbol, "per_share": per_share, "quantity": p.quantity, "amount": betrag})
        return betrag

    # --- Berichte --------------------------------------------------------------------------------------------
    def record(self, when: date) -> dict:
        inv = self.invested()
        eq = self.cash + inv
        row = {"date": when, "cash": self.cash, "invested": inv, "equity": eq, "open_positions": len(self.positions),
               "realized_pnl": self.realized_pnl, "unrealized_pnl": self.unrealized_pnl, "dividends": self.dividends_total, "fees": self.fees_total}
        self.equity_curve.append(row)
        return row

    def snapshot(self) -> list[dict]:
        return [{"symbol": p.symbol, "quantity": p.quantity, "avg_entry_price": p.avg_entry_price, "entry_date": p.entry_date,
                 "last_price": p.last_price, "market_value": p.market_value, "unrealized_pnl": p.unrealized_pnl,
                 "realized_pnl": p.realized_pnl, "fees": p.fees_paid, "slippage": p.slippage_cost} for p in self.positions.values()]
