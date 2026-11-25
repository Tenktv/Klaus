"""Boersenkalender (Handelstage, Feiertage, verkuerzte Tage, Handelszeiten) auf Basis der Bibliothek `exchange_calendars`.

Kalender: NYSE, NASDAQ, XETRA, LSE, TSE sowie CRYPTO (24/7, jeder Tag ein Handelstag). Zeiten werden in UTC und in der Boersenzeit angegeben.
Grenzen: exchange_calendars deckt nur einen begrenzten Zeitraum ab (ca. 20 Jahre zurueck bis ca. 1 Jahr voraus); ausserhalb -> CalendarError.
Aussergewoehnliche Schliessungen (Trauertage, Stoerungen) sind nur enthalten, soweit die Bibliothek sie kennt."""
from __future__ import annotations

from datetime import time

import pandas as pd

try:
    import exchange_calendars as xcals
except ImportError:   # pragma: no cover
    xcals = None

CODES = {"NYSE": "XNYS", "NASDAQ": "XNAS", "XETRA": "XETR", "LSE": "XLON", "TSE": "XTKS", "CRYPTO": None}


class CalendarError(ValueError):
    pass


def _d(x) -> pd.Timestamp:
    t = pd.Timestamp(x)
    return (t.tz_localize(None) if t.tz is not None else t).normalize()


class MarketCalendar:
    def __init__(self, name: str = "NYSE"):
        name = name.upper()
        if name not in CODES:
            raise CalendarError(f"Unbekannter Kalender {name!r}; moeglich: {', '.join(CODES)}.")
        self.name = name
        self.code = CODES[name]
        if self.code is None:
            self._cal, self.timezone = None, "UTC"
        else:
            if xcals is None:
                raise CalendarError("Paket exchange_calendars fehlt (pip install exchange_calendars).")
            self._cal = xcals.get_calendar(self.code)
            self.timezone = str(self._cal.tz)

    def _pruefe(self, d: pd.Timestamp) -> None:
        if self._cal is not None and (d < self._cal.first_session or d > self._cal.last_session):
            raise CalendarError(f"{self.name}: {d.date()} liegt ausserhalb des Kalenderbereichs {self._cal.first_session.date()} bis {self._cal.last_session.date()}.")

    def is_session(self, day) -> bool:
        d = _d(day)
        if self._cal is None:
            return True
        self._pruefe(d)
        return bool(self._cal.is_session(d))

    def sessions(self, start, end) -> pd.DatetimeIndex:
        s, e = _d(start), _d(end)
        if self._cal is None:
            return pd.date_range(s, e, freq="D")
        self._pruefe(s), self._pruefe(e)
        return pd.DatetimeIndex(self._cal.sessions_in_range(s, e)).tz_localize(None)

    def hours(self, day) -> tuple[pd.Timestamp, pd.Timestamp]:
        """(Open, Close) als UTC-Zeitstempel; verkuerzte Tage liefern das fruehere Close."""
        d = _d(day)
        if self._cal is None:
            return d.tz_localize("UTC"), (d + pd.Timedelta(days=1)).tz_localize("UTC")
        if not self.is_session(d):
            raise CalendarError(f"{self.name}: {d.date()} ist kein Handelstag.")
        return self._cal.session_open(d), self._cal.session_close(d)

    def local_hours(self, day) -> tuple[time, time]:
        o, c = self.hours(day)
        return o.tz_convert(self.timezone).time(), c.tz_convert(self.timezone).time()

    def is_early_close(self, day) -> bool:
        d = _d(day)
        return self._cal is not None and self.is_session(d) and d in self._cal.early_closes

    def next_session(self, day) -> pd.Timestamp:
        d = _d(day) + pd.Timedelta(days=1)
        for _ in range(15):
            if self.is_session(d):
                return d
            d += pd.Timedelta(days=1)
        raise CalendarError("Kein Handelstag in den naechsten 15 Tagen gefunden.")

    def previous_session(self, day) -> pd.Timestamp:
        d = _d(day) - pd.Timedelta(days=1)
        for _ in range(15):
            if self.is_session(d):
                return d
            d -= pd.Timedelta(days=1)
        raise CalendarError("Kein Handelstag in den letzten 15 Tagen gefunden.")

    def holidays(self, start, end) -> list[pd.Timestamp]:
        """Wochentage (Mo-Fr) im Zeitraum, an denen NICHT gehandelt wird."""
        if self._cal is None:
            return []
        alle = pd.bdate_range(_d(start), _d(end))
        ses = set(self.sessions(start, end))
        return [d for d in alle if d not in ses]

    def sessions_between(self, a, b) -> int:
        """Anzahl Handelstage nach a bis einschliesslich b (0 wenn gleicher Tag)."""
        a, b = _d(a), _d(b)
        return 0 if b <= a else len(self.sessions(a + pd.Timedelta(days=1), b))
