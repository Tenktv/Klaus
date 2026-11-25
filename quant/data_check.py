"""Pruefung von Marktdaten (Konsistenz, Vollstaendigkeit, Ausreisser, Adjusted Close, Dividenden, Splits) und Quellen-Verifikation.

WICHTIG zur Aussagekraft: "ok" heisst nur: interne Konsistenzpruefungen bestanden. Es beweist NICHT, dass die Daten mit der Wirklichkeit
uebereinstimmen. Dafuer gibt es compare_frames (Abgleich zweier unabhaengiger Quellen). Kann eine Quelle nicht erreicht werden (z. B. kein
Netz), ist das Ergebnis "not_verified" - niemals "ok"."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .calendar import MarketCalendar
from .corporate_actions import CorporateActions


@dataclass
class Issue:
    severity: str          # error | warn
    code: str
    message: str
    dates: list = field(default_factory=list)


@dataclass
class DataCheckReport:
    symbol: str
    issues: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def status(self) -> str:
        return "errors" if any(i.severity == "error" for i in self.issues) else "warnings" if self.issues else "ok"

    def codes(self) -> list[str]:
        return [i.code for i in self.issues]

    def add(self, severity, code, message, dates=None):
        self.issues.append(Issue(severity, code, message, [str(pd.Timestamp(d).date()) for d in (list(dates) if dates is not None else [])][:10]))


def check_prices(df: pd.DataFrame, symbol: str = "?", calendar: MarketCalendar | None = None, actions: CorporateActions | None = None,
                 outlier_return: float = 0.25, max_missing_share: float = 0.02, flat_run: int = 5) -> DataCheckReport:
    rep = DataCheckReport(symbol)
    d = df.copy()
    d.columns = [str(c).lower() for c in d.columns]
    rep.stats["rows"] = len(d)
    if len(d) == 0:
        rep.add("error", "empty", "Keine Daten.")
        return rep
    rep.stats["first"], rep.stats["last"] = str(d.index[0].date()), str(d.index[-1].date())
    if d.index.has_duplicates:
        rep.add("error", "duplicate_timestamps", f"{int(d.index.duplicated().sum())} doppelte Zeitstempel.", d.index[d.index.duplicated()])
    if not d.index.is_monotonic_increasing:
        rep.add("error", "unsorted", "Zeitstempel nicht aufsteigend.")
    nan = d[["open", "high", "low", "close"]].isna().any(axis=1)
    if nan.any():
        rep.add("error", "missing_prices", f"{int(nan.sum())} Zeilen mit fehlenden Preisen.", d.index[nan])
    if "volume" in d and len(d) >= 20 and (d["volume"] == 0).mean() > 0.05:
        rep.add("warn", "zero_volume", f"{(d['volume'] == 0).mean():.0%} der Tage ohne Volumen.")
    # --- Kalender ---
    if calendar is not None and len(d) > 1:
        erw = calendar.sessions(d.index[0], d.index[-1])
        fehlt = erw.difference(d.index)
        extra = d.index.difference(erw)
        rep.stats["expected_sessions"], rep.stats["missing_sessions"] = len(erw), len(fehlt)
        if len(fehlt):
            rep.add("error" if len(fehlt) / len(erw) > max_missing_share else "warn", "missing_sessions", f"{len(fehlt)} von {len(erw)} Handelstagen fehlen.", fehlt)
        if len(extra):
            rep.add("error", "non_session_rows", f"{len(extra)} Zeilen an Tagen ohne Handel (Wochenende/Feiertag).", extra)
    # --- Ausreisser ---
    c = d["close"].astype(float)
    ret = c.pct_change()
    splits = actions.splits if actions is not None else pd.Series(dtype=float)
    erklaert = set()
    for ex, ratio in splits.items():
        for t in d.index[(d.index >= ex - pd.Timedelta(days=3)) & (d.index <= ex + pd.Timedelta(days=3))]:
            if abs(ret.get(t, 0) - (1 / ratio - 1)) < 0.05:
                erklaert.add(t)
    gross = ret[(ret.abs() > outlier_return) & ~ret.index.isin(erklaert)]
    if len(gross):
        rep.add("warn", "outlier_return", f"{len(gross)} Tagesrenditen > {outlier_return:.0%} (ohne Split erklaert).", gross.index)
    spanne = (d["high"] / d["low"] - 1)
    if (spanne > 0.5).any():
        rep.add("warn", "wide_range", "Tage mit High/Low-Spanne > 50 %.", spanne.index[spanne > 0.5])
    flat = (c.diff() == 0).astype(int)
    lauf = flat.groupby((flat == 0).cumsum()).cumsum()
    if len(lauf) and lauf.max() >= flat_run:
        rep.add("warn", "flat_prices", f"{int(lauf.max())} Tage in Folge identischer Schlusskurs (stale?).", lauf.index[lauf >= flat_run])
    # --- Adjusted Close ---
    if "adj_close" in d:
        r = (d["adj_close"] / d["close"]).astype(float)
        if (r > 1 + 1e-6).any():
            rep.add("warn", "adj_above_close", "adj_close liegt ueber close (ungewoehnlich).", r.index[r > 1 + 1e-6])
        spruenge = r.pct_change().abs()
        gross_s = spruenge[spruenge > 1e-4]
        if actions is not None and len(gross_s):
            div_tage = list(actions.dividends.index) + list(actions.splits.index)
            ohne = [t for t in gross_s.index if not any(abs((t - e).days) <= 3 for e in div_tage)]
            if ohne:
                rep.add("warn", "adj_jump_without_action", f"{len(ohne)} Spruenge im Verhaeltnis adj/close ohne Dividende/Split.", ohne)
        if len(r) > 3 and r.iloc[-1] < r.iloc[0] - 1e-6 and r.is_monotonic_increasing is False and (r.diff().dropna() < -1e-4).any():
            rep.add("warn", "adj_ratio_not_monotonic", "adj/close sinkt zeitweise (bei reinen Dividenden steigt das Verhaeltnis zum Ende hin).", r.index[r.diff() < -1e-4])
    # --- Dividenden / Splits ---
    if actions is not None:
        for ex, v in actions.dividends.items():
            t = d.index[d.index.searchsorted(ex)] if d.index.searchsorted(ex) < len(d) else None
            if t is not None and v / float(c.loc[t]) > 0.2:
                rep.add("warn", "dividend_implausible", f"Dividende {v} am {ex.date()} > 20 % des Kurses.", [ex])
            if calendar is not None and not calendar.is_session(ex):
                rep.add("warn", "dividend_non_session", f"Dividenden-Ex-Datum {ex.date()} ist kein Handelstag.", [ex])
        for ex, ratio in actions.splits.items():
            if not 1 / 20 <= ratio <= 20:
                rep.add("warn", "split_implausible", f"Split-Verhaeltnis {ratio} am {ex.date()} ungewoehnlich.", [ex])
            i = d.index.searchsorted(ex)
            if 0 < i < len(d):
                sprung = float(c.iloc[i] / c.iloc[i - 1])
                angepasst = abs(sprung - 1) < 0.15
                if actions.prices_split_adjusted and abs(sprung - 1 / ratio) < 0.1 * abs(1 / ratio):
                    rep.add("warn", "split_not_adjusted", f"Preise sollen splitbereinigt sein, zeigen aber am {ex.date()} den Sprung {sprung:.2f}.", [ex])
                if not actions.prices_split_adjusted and angepasst and abs(ratio - 1) > 0.3:
                    rep.add("warn", "split_without_jump", f"Rohpreise zeigen am {ex.date()} keinen Split-Sprung (erwartet {1 / ratio:.2f}).", [ex])
    return rep


def compare_frames(a: pd.DataFrame, b: pd.DataFrame, tol: float = 0.005) -> dict:
    """Abgleich zweier unabhaengiger Quellen auf den gemeinsamen Tagen (Schlusskurs, relative Abweichung)."""
    gem = a.index.intersection(b.index)
    if len(gem) == 0:
        return {"common_days": 0, "status": "not_verified", "reason": "Keine gemeinsamen Tage."}
    diff = ((a.loc[gem, "close"] - b.loc[gem, "close"]).abs() / b.loc[gem, "close"])
    schlecht = diff[diff > tol]
    return {"common_days": len(gem), "max_rel_diff": float(diff.max()), "mismatches": len(schlecht),
            "mismatch_dates": [str(t.date()) for t in schlecht.index[:10]], "status": "ok" if not len(schlecht) else "mismatch"}


def verify_source(source, symbols, start=None, end=None, calendar: MarketCalendar | None = None, **kw) -> dict:
    """Holt jedes Symbol aus der Quelle und prueft es. Nicht erreichbare Quelle -> not_verified (mit Grund), nie 'ok'."""
    out = {"source": getattr(source, "name", "?"), "symbols": {}, "note": ("'ok' bedeutet: interne Konsistenzpruefungen bestanden - "
                                                                          "kein Beweis fuer Uebereinstimmung mit der Wirklichkeit.")}
    for s in symbols:
        try:
            md = source.fetch(s, start, end)
        except Exception as e:   # Netzwerk, Format, fehlendes Paket ...
            out["symbols"][s] = {"status": "not_verified", "reason": f"{type(e).__name__}: {e}"}
            continue
        rep = check_prices(md.prices, s, calendar, md.actions, **kw)
        out["symbols"][s] = {"status": rep.status, "stats": rep.stats, "issues": [i.__dict__ for i in rep.issues], "validation": md.report.warnings}
    stati = {v["status"] for v in out["symbols"].values()}
    out["overall"] = "not_verified" if "not_verified" in stati else "errors" if "errors" in stati else "warnings" if "warnings" in stati else "ok"
    return out
