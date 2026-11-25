"""Kommandozeile: Datenquelle pruefen.   python -m quant.verify_data AAPL SPY --start 2020-01-01 --end 2024-12-31 --calendar NYSE

Ohne Netzwerkzugriff meldet das Werkzeug "not_verified" (Exit-Code 2) - es erfindet keine Ergebnisse."""
import argparse
import json
import sys

from .calendar import MarketCalendar
from .data import YahooSource
from .data_check import verify_source


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("symbols", nargs="+")
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--calendar", default="NYSE")
    a = ap.parse_args(argv)
    res = verify_source(YahooSource(), a.symbols, a.start, a.end, MarketCalendar(a.calendar))
    print(json.dumps(res, indent=2, ensure_ascii=False, default=str))
    return {"ok": 0, "warnings": 1, "errors": 1, "not_verified": 2}[res["overall"]]


if __name__ == "__main__":
    sys.exit(main())
