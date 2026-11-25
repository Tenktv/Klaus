"""Market Data Engine: Validierung, Normalisierung, Quellen (CSV/JSON/DataFrame/Yahoo), lokaler Cache.

Datenmodell (Tagesdaten): DatetimeIndex (ohne Zeitzone, Mitternacht), Spalten open, high, low, close (ROH, handelbar), volume.
Optional adj_close - wird nur zur Analyse mitgefuehrt und NIE zur Ausfuehrung benutzt. Eingaben gelten als unzuverlaessig."""
from __future__ import annotations

import hashlib
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .config import MARKETS, MarketConfig
from .corporate_actions import CorporateActions

OHLC = ["open", "high", "low", "close"]


class DataError(ValueError):
    """Daten unbrauchbar (nicht stillschweigend reparieren)."""


@dataclass
class ValidationReport:
    symbol: str
    rows_in: int = 0
    rows_out: int = 0
    duplicates_removed: int = 0
    nan_rows_removed: int = 0
    gaps: list = field(default_factory=list)      # (von, bis, kalendertage) - auffaellige Luecken
    warnings: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.gaps and not self.warnings


def validate_ohlcv(df: pd.DataFrame, symbol: str = "?", market: MarketConfig | None = None, max_gap_days: int = 5) -> tuple[pd.DataFrame, ValidationReport]:
    """Prueft und normalisiert. Wirft DataError bei unbrauchbaren Daten (ungueltige Preise, widerspruechliche Duplikate).
    Behebt (und meldet): Sortierung, identische Duplikate, Zeilen mit fehlenden Preisen. Meldet grosse Luecken."""
    if df is None or len(df) == 0:
        raise DataError(f"{symbol}: keine Daten.")
    rep = ValidationReport(symbol, rows_in=len(df))
    d = df.copy()
    d.columns = [str(c).strip().lower().replace(" ", "_") for c in d.columns]
    fehlt = [c for c in OHLC if c not in d.columns]
    if fehlt:
        raise DataError(f"{symbol}: Spalten fehlen: {', '.join(fehlt)}.")
    if "volume" not in d.columns:
        d["volume"] = 0.0
        rep.warnings.append("Keine Volumen-Spalte, mit 0 gefuellt.")
    keep = OHLC + ["volume"] + (["adj_close"] if "adj_close" in d.columns else [])
    d = d[keep].apply(pd.to_numeric, errors="coerce")
    try:
        idx = pd.to_datetime(d.index)
    except (ValueError, TypeError) as e:
        raise DataError(f"{symbol}: Zeitstempel nicht lesbar ({e}).")
    if idx.tz is not None:   # Zeitzone des Marktes, dann Kalendertag
        idx = idx.tz_convert(market.timezone if market else "UTC").tz_localize(None)
    d.index = idx.normalize()
    d.index.name = "date"
    if d.index.hasnans:
        raise DataError(f"{symbol}: ungueltige Zeitstempel.")
    d = d.sort_index(kind="stable")
    dup = d.index.duplicated(keep=False)
    if dup.any():
        for t, g in d[dup].groupby(level=0):
            if len(g.drop_duplicates()) > 1:
                raise DataError(f"{symbol}: widerspruechliche Duplikate am {t.date()} (Intraday-Daten werden nicht unterstuetzt).")
        n = int(d.index.duplicated(keep="first").sum())
        d = d[~d.index.duplicated(keep="first")]
        rep.duplicates_removed = n
        rep.warnings.append(f"{n} doppelte Zeitstempel entfernt.")
    nan = d[OHLC].isna().any(axis=1)
    if nan.any():
        rep.nan_rows_removed = int(nan.sum())
        rep.warnings.append(f"{rep.nan_rows_removed} Zeilen mit fehlenden Preisen entfernt: " + ", ".join(str(t.date()) for t in d.index[nan][:5]))
        d = d[~nan]
    if len(d) == 0:
        raise DataError(f"{symbol}: nach der Bereinigung keine Daten.")
    d["volume"] = d["volume"].fillna(0.0)
    if (d[OHLC] <= 0).any().any():
        raise DataError(f"{symbol}: Preise <= 0.")
    if (d["volume"] < 0).any():
        raise DataError(f"{symbol}: negatives Volumen.")
    schlecht = (d["high"] < d["low"]) | (d["open"] > d["high"] + 1e-9) | (d["open"] < d["low"] - 1e-9) | (d["close"] > d["high"] + 1e-9) | (d["close"] < d["low"] - 1e-9)
    if schlecht.any():
        raise DataError(f"{symbol}: widerspruechliche Kerzen (High/Low/Open/Close) am {d.index[schlecht][0].date()}.")
    tage = d.index.to_series().diff().dt.days.dropna()
    for t, n in tage[tage > max_gap_days].items():
        rep.gaps.append((str((t - pd.Timedelta(days=int(n))).date()), str(t.date()), int(n)))
    if rep.gaps:
        rep.warnings.append(f"{len(rep.gaps)} Luecken > {max_gap_days} Tage.")
    rep.rows_out = len(d)
    return d, rep


def from_dataframe(df: pd.DataFrame, symbol: str = "?", market: MarketConfig | None = None, **kw):
    return validate_ohlcv(df, symbol, market, **kw)


def load_csv(path, symbol: str = "?", market: MarketConfig | None = None, **kw):
    """CSV mit Spalten Date,Open,High,Low,Close[,Adj Close][,Volume]."""
    try:
        df = pd.read_csv(path)
    except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError) as e:
        raise DataError(f"{symbol}: CSV nicht lesbar ({e}).")
    first = df.columns[0]
    spalte = next((c for c in df.columns if str(c).strip().lower() in ("date", "datum", "timestamp", "time")), first)
    return validate_ohlcv(df.set_index(spalte), symbol, market, **kw)


def load_json(text_or_records, symbol: str = "?", market: MarketConfig | None = None, **kw):
    """JSON-Liste von Objekten [{date, open, high, low, close, volume}, ...] (Text oder bereits geparst)."""
    try:
        recs = json.loads(text_or_records) if isinstance(text_or_records, (str, bytes)) else text_or_records
        df = pd.DataFrame(recs)
    except (ValueError, TypeError) as e:
        raise DataError(f"{symbol}: JSON nicht lesbar ({e}).")
    spalte = next((c for c in df.columns if str(c).lower() in ("date", "datum", "timestamp", "time")), None)
    if spalte is None:
        raise DataError(f"{symbol}: JSON ohne Datumsfeld.")
    return validate_ohlcv(df.set_index(spalte), symbol, market, **kw)


@dataclass
class MarketData:
    symbol: str
    prices: pd.DataFrame
    actions: CorporateActions
    source: str
    report: ValidationReport


class MarketDataSource(ABC):
    name = "abstrakt"

    @abstractmethod
    def fetch(self, symbol: str, start: str | None = None, end: str | None = None) -> MarketData: ...


class CsvDirSource(MarketDataSource):
    """Ordner mit {SYMBOL}.csv (+ optional {SYMBOL}_actions.json mit {"dividends": {datum: betrag}, "splits": {datum: ratio}})."""
    name = "csv"

    def __init__(self, ordner, market: MarketConfig | None = None):
        self.ordner, self.market = Path(ordner), market

    def fetch(self, symbol, start=None, end=None):
        sicher = "".join(c for c in symbol if c.isalnum() or c in "-_.")   # kein Pfad-Trick ueber den Symbolnamen
        if sicher != symbol or not symbol:
            raise DataError(f"Ungueltiges Symbol: {symbol!r}")
        df, rep = load_csv(self.ordner / f"{symbol}.csv", symbol, self.market)
        akt = self.ordner / f"{symbol}_actions.json"
        actions = CorporateActions.from_dict(json.loads(akt.read_text(encoding="utf-8"))) if akt.exists() else CorporateActions()
        return MarketData(symbol, _zuschneiden(df, start, end), actions, self.name, rep)


class YahooSource(MarketDataSource):
    """Yahoo Finance ueber das Paket yfinance (optional installiert). Rohe OHLC (auto_adjust=False) + Dividenden + Splits.
    Hinweis: Yahoos "rohe" Kurse sind bereits SPLIT-bereinigt (nicht dividendenbereinigt) -> prices_split_adjusted=True.
    Inoffizielle Quelle: keine Garantie fuer Vollstaendigkeit/Korrektheit; Daten werden wie jede Eingabe validiert."""
    name = "yahoo"

    def __init__(self, market: MarketConfig | None = None):
        self.market = market

    def fetch(self, symbol, start=None, end=None):
        try:
            import yfinance as yf
        except ImportError:
            raise DataError("yfinance ist nicht installiert (pip install yfinance).")
        try:
            h = yf.Ticker(symbol).history(start=start, end=end, auto_adjust=False, actions=True)
        except Exception as e:   # Netzwerk, Ratenlimit, ... -> ehrlich melden
            raise DataError(f"{symbol}: Yahoo-Abruf fehlgeschlagen ({type(e).__name__}: {e}).")
        if h is None or len(h) == 0:
            raise DataError(f"{symbol}: Yahoo lieferte keine Daten.")
        h = h.rename(columns={"Adj Close": "adj_close"})
        div = h["Dividends"][h["Dividends"] > 0] if "Dividends" in h else pd.Series(dtype=float)
        spl = h["Stock Splits"][h["Stock Splits"] > 0] if "Stock Splits" in h else pd.Series(dtype=float)
        df, rep = validate_ohlcv(h[[c for c in h.columns if c.lower() in OHLC + ["volume", "adj_close"]]], symbol, self.market)
        return MarketData(symbol, df, CorporateActions(div, spl, prices_split_adjusted=True), self.name, rep)


class CachedSource(MarketDataSource):
    """Lokaler Cache (CSV + JSON) um eine andere Quelle. Gleiche Anfrage -> Datei, solange sie juenger als max_age_h ist."""

    def __init__(self, quelle: MarketDataSource, ordner, max_age_h: float = 24.0):
        self.quelle, self.ordner, self.max_age_h = quelle, Path(ordner), max_age_h
        self.name = f"cache({quelle.name})"

    def _pfad(self, symbol, start, end) -> Path:
        key = hashlib.sha256(f"{self.quelle.name}|{symbol}|{start}|{end}".encode()).hexdigest()[:16]
        return self.ordner / f"{''.join(c for c in symbol if c.isalnum())}_{key}"

    def fetch(self, symbol, start=None, end=None):
        p = self._pfad(symbol, start, end)
        csv, meta = p.with_suffix(".csv"), p.with_suffix(".json")
        if csv.exists() and meta.exists() and time.time() - csv.stat().st_mtime < self.max_age_h * 3600:
            try:
                df, rep = load_csv(csv, symbol)
                m = json.loads(meta.read_text(encoding="utf-8"))
                return MarketData(symbol, df, CorporateActions.from_dict(m["actions"], prices_split_adjusted=m["split_adjusted"]), self.name + ":hit", rep)
            except (DataError, ValueError, KeyError):
                pass   # kaputter Cache -> neu holen
        md = self.quelle.fetch(symbol, start, end)
        self.ordner.mkdir(parents=True, exist_ok=True)
        md.prices.to_csv(csv)
        meta.write_text(json.dumps({"split_adjusted": md.actions.prices_split_adjusted, "source": md.source, "actions": {
            "dividends": {str(k.date()): v for k, v in md.actions.dividends.items()}, "splits": {str(k.date()): v for k, v in md.actions.splits.items()}}}), encoding="utf-8")
        return MarketData(symbol, md.prices, md.actions, self.name + ":miss", md.report)


def _zuschneiden(df: pd.DataFrame, start, end) -> pd.DataFrame:
    if start:
        df = df[df.index >= pd.Timestamp(start)]
    if end:
        df = df[df.index <= pd.Timestamp(end)]
    if len(df) == 0:
        raise DataError("Keine Daten im gewuenschten Zeitraum.")
    return df
