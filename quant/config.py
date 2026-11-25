"""Konfiguration: Backtest, Risiko, Maerkte. Alle Werte sind Testannahmen, keine Anlageempfehlung."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BacktestConfig:
    initial_cash: float = 100_000.0
    fee_rate: float = 0.0001            # 0,01 % je Orderseite (vom Ordervolumen)
    slippage_rate: float = 0.0002       # 0,02 % je Orderseite (Kauf teurer, Verkauf billiger)
    allow_fractional: bool = False      # Aktien/ETFs: ganze Stuecke
    position_size_pct: float = 0.10     # Ziel-Gewicht je Position bei einem Kaufsignal (Anteil am Gesamtwert)
    periods_per_year: int = 252         # Tagesdaten
    risk_free_rate: float = 0.0         # jaehrlich, fuer Sharpe/Sortino
    benchmark: str | None = None        # Symbol im Datensatz; Kaufen+Halten ohne Kosten

    def __post_init__(self):
        if self.initial_cash <= 0:
            raise ValueError("initial_cash muss > 0 sein.")
        for n in ("fee_rate", "slippage_rate"):
            if not 0 <= getattr(self, n) < 0.5:
                raise ValueError(f"{n} muss zwischen 0 und 0,5 liegen.")
        if not 0 < self.position_size_pct <= 1:
            raise ValueError("position_size_pct muss in (0, 1] liegen.")


@dataclass(frozen=True)
class RiskConfig:
    """None = Grenze aus. Der Risk Manager ist unabhaengig von Strategie und KI und kann Orders nur ablehnen/begrenzen."""
    max_position_pct: float | None = None        # max. Anteil einer Position am Gesamtwert
    min_cash_pct: float | None = None            # Mindest-Cash-Reserve
    max_exposure_pct: float | None = None        # max. Gesamtinvestition
    max_risk_per_position_pct: float | None = None   # max. Verlust je Position bei Stopp-Abstand `stop_loss_pct` (ohne Stopp: Totalverlust angenommen)
    stop_loss_pct: float | None = None           # angenommener Stopp-Abstand fuer die Risikorechnung (kein automatischer Stopp!)
    max_drawdown_pct: float | None = None        # ab diesem Portfolio-Drawdown keine neuen Kaeufe mehr
    max_open_positions: int | None = None

    @classmethod
    def beispiel_test(cls) -> "RiskConfig":
        """Testkonfiguration aus der Aufgabenstellung: 10 % je Position, 20 % Cash, 80 % Investition. KEINE Anlageempfehlung."""
        return cls(max_position_pct=0.10, min_cash_pct=0.20, max_exposure_pct=0.80)


@dataclass(frozen=True)
class MarketConfig:
    name: str
    asset_class: str                     # equity | etf | crypto | forex
    trading_days: str = "weekdays"       # weekdays | all (24/7)
    timezone: str = "America/New_York"
    currency: str = "USD"
    fee_rate: float | None = None        # None = BacktestConfig.fee_rate
    slippage_rate: float | None = None
    allow_fractional: bool | None = None
    enabled: bool = True                 # Krypto/Forex sind vorbereitet, aber gesperrt bis zur Validierung
    note: str = ""


MARKETS: dict[str, MarketConfig] = {
    "equity": MarketConfig("equity", "equity", note="US-Aktien, Handelstage Mo-Fr (kein Feiertagskalender)."),
    "etf": MarketConfig("etf", "etf", note="US-ETFs wie Aktien."),
    "crypto": MarketConfig("crypto", "crypto", trading_days="all", timezone="UTC", allow_fractional=True, enabled=False,
                           note="Vorbereitet, noch nicht validiert (24/7, andere Gebuehren)."),
    "forex": MarketConfig("forex", "forex", timezone="UTC", allow_fractional=True, enabled=False,
                          note="Vorbereitet, noch nicht validiert (Spreads/Swaps fehlen)."),
}
