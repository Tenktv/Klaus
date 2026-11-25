"""Paper-Broker: rein VIRTUELLE Orders, Positionen und Kontostand auf Basis der quant-Engine.

SICHERHEIT: kein Netzwerk, kein Broker-Code, keine Schluessel, keine Verbindung zu den Live-Broker-Modulen in src/ oder zum Live-Papierhandel.
Portfolio (portfolio.py), Risiko (risk.py), Kosten/Buchung (execution.py) und Kennzahlen (metrics.py) sind dieselben Module wie im Backtest.

Zeitmodell (Tagesdaten): Orders, die vor process_day(d) eingereicht wurden, koennen frueestens an der Kerze d ausgefuehrt werden (nie an der Kerze,
vor der sie eingereicht wurden). Die Kerze gibt nur her, was in ihrer Spanne (Open/High/Low) liegt:
- Market: Open +/- Slippage.
- Limit Kauf L: Open <= L -> Fill zum Open (+Slippage, hoechstens L); sonst Low < L -> Fill zu L (ohne Slippage); sonst NICHT ausgefuehrt.
  Limit Verkauf analog (High > L). Beruehrung allein (Low == L) fuehrt standardmaessig nicht zum Fill (limit_requires_trade_through=True).
- Stop Verkauf S: Open <= S -> Fill zum Open - Slippage (Gap); sonst Low <= S -> Fill zu S - Slippage. Stop Kauf analog (High >= S).
- time_in_force "day": verfaellt am Ende der ersten Kerze, an der sie haette ausgefuehrt werden koennen; "gtc": bleibt bis Fill/Storno.
Modellannahmen, keine Garantie fuer reale Ausfuehrung (Teilfuellungen, Liquiditaet und Orderbuch fehlen)."""
from __future__ import annotations

import json
import math
import os
import shutil
from dataclasses import asdict
from datetime import date as Date

import numpy as np
import pandas as pd

from .calendar import MarketCalendar
from .config import BacktestConfig, RiskConfig
from .execution import execute_buy, execute_sell, fill_price, size_market_buy
from .metrics import compute_metrics
from .portfolio import Order, Portfolio, Position, Trade
from .risk import RiskManager

STATE_VERSION = 1
ORDER_TYPES = ("market", "limit", "stop")


class PaperError(Exception):
    pass


class PaperOrderError(PaperError):
    """Ungueltige Order (falsche Parameter) - wird nicht angenommen."""


class PaperStateError(PaperError):
    """Gespeicherter Zustand fehlt, ist kaputt oder inkonsistent."""


def _iso(v):
    return v.isoformat() if isinstance(v, Date) else v


def _date(v):
    return Date.fromisoformat(v) if isinstance(v, str) else v


class PaperBroker:
    def __init__(self, config: BacktestConfig | None = None, risk: RiskConfig | None = None, calendar: MarketCalendar | None = None,
                 state_path=None, journal_path=None, stale_sessions: int = 3, limit_requires_trade_through: bool = True):
        self.config = config or BacktestConfig()
        self.risk_config = risk or RiskConfig()
        self.risk = RiskManager(self.risk_config)
        self.calendar = calendar
        self.pf = Portfolio(self.config.initial_cash)
        self.orders: list[Order] = []
        self.events: list[dict] = []
        self.last_bars: dict[str, dict] = {}
        self.last_day: Date | None = None
        self.peak = self.config.initial_cash
        self.next_id = 1
        self.stale_sessions = stale_sessions
        self.limit_requires_trade_through = limit_requires_trade_through
        self.state_path = os.fspath(state_path) if state_path else None
        self.journal_path = os.fspath(journal_path) if journal_path else None
        self.extra: dict = {}
        self._target: dict[int, float] = {}   # order id -> Zielgewicht (Market-Kauf ohne feste Stueckzahl)

    # --- Protokoll -------------------------------------------------------------------------------------------
    def _event(self, typ: str, level: str = "info", **kw) -> dict:
        e = {"seq": len(self.events) + 1, "type": typ, "level": level, **{k: _iso(v) for k, v in kw.items()}}
        self.events.append(e)
        if self.journal_path:
            with open(self.journal_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        return e

    @property
    def errors(self) -> list[dict]:
        return [e for e in self.events if e["level"] == "error"]

    # --- Orders ----------------------------------------------------------------------------------------------
    def open_orders(self, symbol: str | None = None) -> list[Order]:
        return [o for o in self.orders if o.status == "open" and (symbol is None or o.symbol == symbol)]

    def _stale(self, symbol: str) -> bool:
        lb = self.last_bars.get(symbol)
        if lb is None or self.last_day is None:
            return False
        if self.calendar is not None:
            return self.calendar.sessions_between(lb["date"], self.last_day) >= self.stale_sessions
        return int(np.busday_count(lb["date"], self.last_day)) >= self.stale_sessions   # ohne Kalender: Mo-Fr-Naeherung

    def submit(self, symbol: str, side: str, qty: float | None = None, order_type: str = "market", limit_price: float | None = None,
               stop_price: float | None = None, time_in_force: str = "gtc", target_pct: float | None = None, strategy: str = "") -> Order:
        side, order_type = str(side).lower(), str(order_type).lower()
        fehler = None
        if not symbol or not isinstance(symbol, str):
            fehler = "Symbol fehlt."
        elif side not in ("buy", "sell"):
            fehler = "side muss buy oder sell sein."
        elif order_type not in ORDER_TYPES:
            fehler = f"order_type muss {', '.join(ORDER_TYPES)} sein."
        elif time_in_force not in ("day", "gtc"):
            fehler = "time_in_force muss day oder gtc sein."
        elif qty is None and not (target_pct and side == "buy" and order_type == "market"):
            fehler = "Menge fehlt (nur Market-Kauf darf ein Zielgewicht statt Menge haben)."
        elif qty is not None and (not isinstance(qty, (int, float)) or not math.isfinite(qty) or qty <= 0):
            fehler = "Menge muss eine positive Zahl sein."
        elif qty is not None and not self.config.allow_fractional and float(qty) != int(qty):
            fehler = "Nur ganze Stuecke erlaubt (allow_fractional=False)."
        elif order_type == "limit" and not (isinstance(limit_price, (int, float)) and math.isfinite(limit_price) and limit_price > 0):
            fehler = "Limit-Order braucht limit_price > 0."
        elif order_type == "stop" and not (isinstance(stop_price, (int, float)) and math.isfinite(stop_price) and stop_price > 0):
            fehler = "Stop-Order braucht stop_price > 0."
        elif target_pct is not None and not 0 < target_pct <= 1:
            fehler = "target_pct muss in (0, 1] liegen."
        if fehler:
            self._event("order_invalid", "error", symbol=str(symbol), side=side, order_type=order_type, reason=fehler)
            raise PaperOrderError(fehler)
        o = Order(self.next_id, symbol, side, self.last_day or Date.min, strategy, None if qty is None else float(qty), "open",
                  order_type=order_type, limit_price=limit_price, stop_price=stop_price, time_in_force=time_in_force)
        self.next_id += 1
        self.orders.append(o)
        if target_pct:
            self._target[o.id] = float(target_pct)
        grund = None
        if side == "sell":
            reserviert = sum(x.quantity or 0 for x in self.open_orders(symbol) if x.side == "sell" and x is not o)
            have = self.pf.positions[symbol].quantity if symbol in self.pf.positions else 0.0
            if qty is None or qty > have - reserviert + 1e-9:
                grund = f"Verkauf von {qty} {symbol} nicht moeglich: Long-only, verfuegbar {max(0.0, have - reserviert)}."
        elif self._stale(symbol):
            grund = f"Marktdaten fuer {symbol} veraltet (letzte Kerze {self.last_bars[symbol]['date']}): keine neuen Kaeufe."
        if grund:
            o.status, o.reason = "rejected", grund
            self._event("order_rejected", "warn", id=o.id, symbol=symbol, reason=grund)
            return o
        self._event("order_submitted", id=o.id, symbol=symbol, side=side, order_type=order_type, qty=o.quantity, limit=limit_price, stop=stop_price, tif=time_in_force)
        return o

    def cancel(self, order_id: int) -> bool:
        for o in self.open_orders():
            if o.id == order_id:
                o.status, o.reason = "cancelled", "Vom Nutzer storniert."
                self._event("order_cancelled", id=o.id, symbol=o.symbol)
                return True
        return False

    # --- Kerzen ----------------------------------------------------------------------------------------------
    @staticmethod
    def _bar_fehler(b) -> str | None:
        try:
            o, h, l, c = (float(b[k]) for k in ("open", "high", "low", "close"))
        except (KeyError, TypeError, ValueError):
            return "Kerze unvollstaendig."
        if not all(math.isfinite(v) and v > 0 for v in (o, h, l, c)):
            return "Preise fehlen oder sind <= 0."
        if h < l or not l - 1e-9 <= o <= h + 1e-9 or not l - 1e-9 <= c <= h + 1e-9:
            return "Widerspruechliche Kerze (High/Low/Open/Close)."
        return None

    def _versuch(self, o: Order, b: dict):
        """-> (ref_preis, fill_preis) oder None, wenn die Kerze die Order nicht hergibt."""
        s = self.config.slippage_rate
        op, hi, lo = b["open"], b["high"], b["low"]
        strikt = self.limit_requires_trade_through
        if o.order_type == "market":
            return op, fill_price(o.side, op, s)
        if o.order_type == "limit":
            L = o.limit_price
            if o.side == "buy":
                if op <= L:
                    return op, min(fill_price("buy", op, s), L)
                if (lo < L) if strikt else (lo <= L):
                    return L, L
            else:
                if op >= L:
                    return op, max(fill_price("sell", op, s), L)
                if (hi > L) if strikt else (hi >= L):
                    return L, L
            return None
        S = o.stop_price   # stop
        if o.side == "sell":
            if op <= S:
                return op, fill_price("sell", op, s)
            if lo <= S:
                return S, fill_price("sell", S, s)
        else:
            if op >= S:
                return op, fill_price("buy", op, s)
            if hi >= S:
                return S, fill_price("buy", S, s)
        return None

    def process_day(self, day, bars: dict[str, dict]) -> list[Order]:
        """Verarbeitet einen Handelstag. bars: {symbol: {open, high, low, close[, volume]}}. Rueckgabe: an diesem Tag abgeschlossene Orders."""
        day = pd.Timestamp(day).date()
        if self.last_day is not None and day <= self.last_day:
            self._event("day_ignored", "warn", date=day, reason="Datum nicht neuer als der letzte verarbeitete Tag (doppelte/verspaetete Lieferung).")
            return []
        if self.calendar is not None and not self.calendar.is_session(day):
            self._event("non_session_day", "error", date=day, reason=f"{day} ist kein Handelstag im Kalender {self.calendar.name}; Daten verworfen.")
            return []
        gueltig: dict[str, dict] = {}
        for s, b in sorted(bars.items()):
            f = self._bar_fehler(b)
            if f:
                self._event("bad_bar", "error", date=day, symbol=s, reason=f)
                continue
            gueltig[s] = {"date": day, **{k: float(b[k]) for k in ("open", "high", "low", "close")}, "volume": float(b.get("volume", 0) or 0)}
            lb = self.last_bars.get(s)
            if lb is not None and self.calendar is not None:
                verpasst = self.calendar.sessions_between(lb["date"], day) - 1
                if verpasst > 0:
                    self._event("data_gap", "warn", date=day, symbol=s, missed_sessions=verpasst)
        closes = {s: b["close"] for s, b in self.last_bars.items()}
        opens = {s: b["open"] for s, b in gueltig.items()}
        marks = {**closes, **opens}
        erledigt: list[Order] = []
        faellig = sorted((o for o in self.open_orders() if o.symbol in gueltig), key=lambda o: (o.side != "sell", o.symbol, o.id))
        for o in faellig:
            b = gueltig[o.symbol]
            o.bars_open += 1
            t = self._versuch(o, b)
            if t is None:
                if o.time_in_force == "day":
                    o.status, o.reason = "expired", "Tagesorder nicht ausgefuehrt (Preis nicht erreicht)."
                    self._event("order_expired", id=o.id, symbol=o.symbol, reason=o.reason)
                    erledigt.append(o)
                continue
            ref, px = t
            fee_r = self.config.fee_rate
            if o.side == "sell":
                ok = execute_sell(self.pf, o, o.quantity, px, ref, fee_r, day)
            else:
                qty = o.quantity
                if qty is None:
                    qty = size_market_buy(self.pf, self.risk, o.symbol, px, marks, self.peak, fee_r, self._target.get(o.id, self.config.position_size_pct), self.config.allow_fractional)
                ok = execute_buy(self.pf, self.risk, o, qty, px, ref, fee_r, marks, self.peak, day)
            self._event("order_filled" if ok else "order_rejected", "info" if ok else "warn", id=o.id, symbol=o.symbol, side=o.side, qty=o.quantity,
                        price=o.exec_price, fee=o.fee, reason=o.reason)
            erledigt.append(o)
        for s, b in gueltig.items():
            self.last_bars[s] = b
        self.pf.mark({s: b["close"] for s, b in self.last_bars.items()})
        self.last_day = day
        row = self.pf.record(day)
        self.peak = max(self.peak, row["equity"])
        if self.state_path:
            self.save()
        return erledigt

    # --- Corporate Actions -----------------------------------------------------------------------------------
    def on_dividend(self, symbol: str, per_share: float, day) -> float:
        betrag = self.pf.apply_dividend(symbol, per_share, _date(pd.Timestamp(day).date()))
        self._event("dividend", symbol=symbol, per_share=per_share, amount=betrag, date=_date(pd.Timestamp(day).date()))
        return betrag

    def on_split(self, symbol: str, ratio: float, day) -> None:
        self.pf.apply_split(symbol, ratio, _date(pd.Timestamp(day).date()))
        self._event("split", symbol=symbol, ratio=ratio, date=_date(pd.Timestamp(day).date()))

    # --- Berichte --------------------------------------------------------------------------------------------
    def equity_frame(self) -> pd.DataFrame:
        df = pd.DataFrame(self.pf.equity_curve)
        if df.empty:
            return df
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date")

    def performance(self) -> dict | None:
        df = self.equity_frame()
        return compute_metrics(df, self.pf, self.config.risk_free_rate, self.config.periods_per_year) if len(df) else None

    def snapshot(self) -> dict:
        return {"cash": self.pf.cash, "equity": self.pf.equity(), "invested": self.pf.invested(), "positions": self.pf.snapshot(),
                "open_orders": [asdict(o) for o in self.open_orders()], "last_day": self.last_day}

    # --- Speichern / Wiederherstellen -------------------------------------------------------------------------
    def to_state(self) -> dict:
        pf = self.pf
        conv = lambda d: {k: _iso(v) for k, v in d.items()}  # noqa: E731
        return {"version": STATE_VERSION, "config": asdict(self.config), "risk": asdict(self.risk_config), "next_id": self.next_id,
                "last_day": _iso(self.last_day), "peak": self.peak, "extra": self.extra,
                "target": {str(k): v for k, v in self._target.items()},
                "last_bars": {s: conv(b) for s, b in self.last_bars.items()},
                "portfolio": {"initial_cash": pf.initial_cash, "cash": pf.cash, "realized_pnl": pf.realized_pnl, "dividends_total": pf.dividends_total,
                              "fees_total": pf.fees_total, "slippage_total": pf.slippage_total,
                              "positions": [conv(asdict(p)) for p in pf.positions.values()],
                              "trades": [conv(asdict(t)) for t in pf.trades], "dividend_log": [conv(d) for d in pf.dividend_log],
                              "split_log": [conv(d) for d in pf.split_log], "equity_curve": [conv(r) for r in pf.equity_curve]},
                "orders": [conv(asdict(o)) for o in self.orders], "events": self.events}

    def save(self, path=None) -> None:
        """Atomar: erst .tmp schreiben (fsync), vorherigen Stand als .bak sichern, dann ersetzen."""
        path = os.fspath(path or self.state_path or "")
        if not path:
            raise PaperError("Kein state_path angegeben.")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.to_state(), f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        if os.path.exists(path):
            shutil.copyfile(path, path + ".bak")
        os.replace(tmp, path)

    @classmethod
    def from_state(cls, st: dict, calendar: MarketCalendar | None = None, **kw) -> "PaperBroker":
        try:
            if st.get("version") != STATE_VERSION:
                raise PaperStateError(f"Unbekannte Zustandsversion {st.get('version')!r}.")
            b = cls(BacktestConfig(**st["config"]), RiskConfig(**st["risk"]), calendar, **kw)
            p = st["portfolio"]
            pf = Portfolio(p["initial_cash"])
            pf.cash, pf.realized_pnl, pf.dividends_total = float(p["cash"]), float(p["realized_pnl"]), float(p["dividends_total"])
            pf.fees_total, pf.slippage_total = float(p["fees_total"]), float(p["slippage_total"])
            for x in p["positions"]:
                x["entry_date"] = _date(x["entry_date"])
                pf.positions[x["symbol"]] = Position(**x)
            for x in p["trades"]:
                x["entry_date"], x["exit_date"] = _date(x["entry_date"]), _date(x["exit_date"])
                pf.trades.append(Trade(**x))
            for key in ("dividend_log", "split_log", "equity_curve"):
                rows = []
                for r in p[key]:
                    r["date"] = _date(r["date"])
                    rows.append(r)
                setattr(pf, key, rows)
            b.pf = pf
            for x in st["orders"]:
                for k in ("signal_date", "exec_date"):
                    x[k] = _date(x[k]) if x.get(k) else None
                b.orders.append(Order(**x))
            b.events = list(st["events"])
            b.last_bars = {s: {**v, "date": _date(v["date"])} for s, v in st["last_bars"].items()}
            b.last_day = _date(st["last_day"]) if st["last_day"] else None
            b.peak, b.next_id, b.extra = float(st["peak"]), int(st["next_id"]), st.get("extra", {})
            b._target = {int(k): v for k, v in st.get("target", {}).items()}
        except PaperStateError:
            raise
        except (KeyError, TypeError, ValueError) as e:
            raise PaperStateError(f"Zustand unlesbar ({type(e).__name__}: {e}).")
        b._pruefen()
        return b

    def _pruefen(self) -> None:
        pf = self.pf
        if pf.cash < -1e-6:
            raise PaperStateError("Zustand inkonsistent: negatives Cash.")
        soll = pf.initial_cash + pf.realized_pnl + pf.unrealized_pnl + pf.dividends_total
        if abs(pf.equity() - soll) > 1e-6 * max(1.0, abs(soll)):
            raise PaperStateError(f"Zustand inkonsistent: Equity {pf.equity():.4f} != Start + P/L + Dividenden {soll:.4f}.")

    @classmethod
    def load(cls, path, calendar: MarketCalendar | None = None, **kw) -> "PaperBroker":
        """Laedt den Zustand; ist die Hauptdatei kaputt, wird die letzte Sicherung (.bak) versucht (und protokolliert)."""
        path = os.fspath(path)
        fehler = []
        for kandidat, ist_bak in ((path, False), (path + ".bak", True)):
            try:
                with open(kandidat, "r", encoding="utf-8") as f:
                    b = cls.from_state(json.load(f), calendar, state_path=path, **kw)
                if ist_bak:
                    b._event("restored_from_backup", "warn", reason="Hauptdatei unbrauchbar: " + "; ".join(fehler))
                return b
            except (OSError, ValueError, PaperStateError) as e:
                fehler.append(f"{os.path.basename(kandidat)}: {e}")
        raise PaperStateError("Paper-Zustand nicht wiederherstellbar: " + "; ".join(fehler))


class PaperTrader:
    """Treibt eine Strategie auf dem Paper-Broker: Signal nach Kerzenschluss -> Market-Order (Zielgewicht) fuer die naechste Kerze.
    Verhalten identisch zum Backtest (gleiche Regeln, gleiche Module) - wird per Test gegen die BacktestEngine geprueft."""

    def __init__(self, broker: PaperBroker, strategy):
        import copy
        self.broker, self.strategy_proto = broker, strategy
        self.strategies: dict[str, object] = {}
        self.histories: dict[str, pd.DataFrame] = {}
        for s, rows in broker.extra.get("histories", {}).items():   # nach Neustart wiederherstellen
            self.histories[s] = pd.DataFrame(rows).assign(date=lambda d: pd.to_datetime(d["date"])).set_index("date")
        self._copy = copy.deepcopy

    def _strategie(self, s):
        if s not in self.strategies:
            self.strategies[s] = self._copy(self.strategy_proto)
            self.strategies[s].initialize()
        return self.strategies[s]

    def step(self, day, bars: dict[str, dict]) -> dict:
        b = self.broker
        erledigt = b.process_day(day, bars)
        d = pd.Timestamp(day).normalize()
        if b.last_day != d.date():   # Tag wurde verworfen (Duplikat, Feiertag, ...)
            return {"filled": erledigt, "submitted": []}
        neu = []
        for s in sorted(bars):
            lb = b.last_bars.get(s)
            if lb is None or lb["date"] != d.date():   # ungueltige Kerze
                continue
            row = pd.DataFrame([{k: lb[k] for k in ("open", "high", "low", "close", "volume")}], index=pd.DatetimeIndex([d], name="date"))
            self.histories[s] = pd.concat([self.histories[s], row]) if s in self.histories else row
            st = self._strategie(s)
            sig = st.update(self.histories[s])
            if math.isnan(sig):
                continue
            has, offen = s in b.pf.positions, b.open_orders(s)
            if sig >= 0.5 and not has and not offen:
                neu.append(b.submit(s, "buy", target_pct=b.config.position_size_pct, strategy=st.name))
            elif sig < 0.5 and has and not offen:
                neu.append(b.submit(s, "sell", b.pf.positions[s].quantity, strategy=st.name))
        b.extra["histories"] = {s: [{"date": str(i.date()), **{k: float(r[k]) for k in ("open", "high", "low", "close", "volume")}} for i, r in h.iterrows()]
                                for s, h in self.histories.items()}
        if b.state_path:
            b.save()
        return {"filled": erledigt, "submitted": neu}
