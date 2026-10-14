"""Opt-in Premium-Textmodelle mit lokalen Reservierungen. Kein Ersatz fuer Anbieter-Kreditlimits."""
import datetime as dt
import json
import math
import sqlite3
import uuid
from contextlib import contextmanager
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parent.parent / 'data'
KONFIG = BASE / 'ki_modelle.json'
DB = BASE / 'ki_kosten.sqlite'


class BudgetFehler(RuntimeError):
    pass


def konfig():
    try:
        d = json.loads(KONFIG.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {'aktiv': False, 'tageslimit_usd': 0, 'monatslimit_usd': 0, 'modelle': []}
    except (ValueError, OSError):
        raise BudgetFehler('Premium-Konfiguration kann nicht gelesen werden.') from None
    if not isinstance(d, dict) or type(d.get('aktiv')) is not bool:
        raise BudgetFehler('Ungueltige Premium-Konfiguration.')
    if not isinstance(d.get('modelle', []), list):
        raise BudgetFehler('Premium-Modellliste ist ungueltig.')
    return d


def _betrag(wert):
    try:
        zahl = Decimal(str(wert))
        if not zahl.is_finite() or zahl < 0:
            raise ValueError()
        return int((zahl * 1_000_000).to_integral_value(rounding=ROUND_CEILING))
    except Exception:
        raise BudgetFehler('Ungueltiger Preis oder Kostenrahmen.') from None


def _datum():
    return dt.datetime.now(ZoneInfo('Europe/Berlin')).strftime('%Y-%m-%d')


def modelle(anbieter):
    try:
        d = konfig()
    except (BudgetFehler, OSError, ValueError):
        return []
    return [m['modell'] for m in d.get('modelle', []) if isinstance(m, dict)
            and m.get('anbieter') == anbieter and isinstance(m.get('modell'), str)] if d['aktiv'] else []


@contextmanager
def _db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB, timeout=15)
    try:
        c.execute('CREATE TABLE IF NOT EXISTS kosten (id TEXT PRIMARY KEY, tag TEXT, anbieter TEXT, modell TEXT, betrag INTEGER, zustand TEXT)')
        with c:
            yield c
    finally:
        c.close()


def reservieren(anbieter, modell, nachrichten, tools=None, bild=False):
    d = konfig()
    if not d['aktiv'] or bild:
        raise BudgetFehler('Premium ist aus oder dieser Bildaufruf ist nicht budgetiert.')
    if any(m.get('content') is not None and not isinstance(m.get('content'), str) for m in nachrichten):
        raise BudgetFehler('Premium-Kostenrahmen unterstuetzt hier nur reine Texte.')
    eintrag = next((m for m in d.get('modelle', []) if isinstance(m, dict) and m.get('anbieter') == anbieter and m.get('modell') == modell), None)
    if not eintrag:
        raise BudgetFehler('Premium-Modell nicht ausdruecklich konfiguriert.')
    maximum = eintrag.get('max_ausgabe_tokens', 1024)
    if type(maximum) is not int or not 1 <= maximum <= 8192:
        raise BudgetFehler('Ausgabelimit muss 1 bis 8192 Token sein.')
    # Bytes statt grober Wort-Schaetzung: konservative Reservierung fuer reine Texte/Werkzeuge.
    eingabe = len(json.dumps([nachrichten, tools], ensure_ascii=False).encode('utf-8')) + 512
    preis_in = _betrag(eintrag.get('eingabe_usd_million'))
    preis_out = _betrag(eintrag.get('ausgabe_usd_million'))
    if preis_in == preis_out == 0:
        raise BudgetFehler('Premium braucht ausdrueckliche Preise.')
    betrag = math.ceil((eingabe * preis_in + maximum * preis_out) / 1_000_000)
    taglimit, monatlimit = _betrag(d.get('tageslimit_usd')), _betrag(d.get('monatslimit_usd'))
    tag, ident = _datum(), uuid.uuid4().hex
    with _db() as c:
        c.execute('BEGIN IMMEDIATE')
        tag_sum = c.execute('SELECT coalesce(sum(betrag),0) FROM kosten WHERE tag=?', (tag,)).fetchone()[0]
        monat_sum = c.execute('SELECT coalesce(sum(betrag),0) FROM kosten WHERE substr(tag,1,7)=?', (tag[:7],)).fetchone()[0]
        if not taglimit or not monatlimit or tag_sum + betrag > taglimit or monat_sum + betrag > monatlimit:
            raise BudgetFehler('Premium-Kostenrahmen erreicht; kein kostenpflichtiger Aufruf.')
        c.execute('INSERT INTO kosten VALUES(?,?,?,?,?,?)', (ident, tag, anbieter, modell, betrag, 'reserviert'))
    return {'id': ident, 'max_tokens': maximum, 'preis_in': preis_in, 'preis_out': preis_out}


def abrechnen(ticket, usage):
    if not isinstance(usage, dict):
        return  # Bei unbekanntem Ergebnis bleibt die volle Reservierung bestehen.
    if usage.get('cost') is not None:
        betrag = _betrag(usage['cost'])
        zustand = 'gemeldet'
    elif all(type(usage.get(k)) is int and usage[k] >= 0 for k in ('prompt_tokens', 'completion_tokens')):
        betrag = math.ceil((usage['prompt_tokens'] * ticket['preis_in'] + usage['completion_tokens'] * ticket['preis_out']) / 1_000_000)
        zustand = 'geschaetzt'
    else:
        return
    with _db() as c:
        c.execute('UPDATE kosten SET betrag=?,zustand=? WHERE id=? AND zustand=?', (betrag, zustand, ticket['id'], 'reserviert'))


def status():
    d = konfig()
    tag = _datum()
    aus = {'premium_aktiv': d['aktiv'], 'tag_usd': 0, 'monat_usd': 0,
           'tag_reserviert': 0, 'monat_reserviert': 0,
           'tageslimit_usd': d.get('tageslimit_usd', 0), 'monatslimit_usd': d.get('monatslimit_usd', 0)}
    if DB.exists():
        with _db() as c:
            for feld, query, wert in [('tag', 'tag=?', tag), ('monat', 'substr(tag,1,7)=?', tag[:7])]:
                aus[feld + '_usd'] = c.execute('SELECT coalesce(sum(betrag),0) FROM kosten WHERE ' + query, (wert,)).fetchone()[0] / 1_000_000
                aus[feld + '_reserviert'] = c.execute("SELECT coalesce(sum(betrag),0) FROM kosten WHERE zustand='reserviert' AND " + query, (wert,)).fetchone()[0] / 1_000_000
    return aus


def status_text():
    try:
        s = status()
    except Exception:
        return 'KI-Kostenstatus nicht verfuegbar. Premium-Konfiguration und Datenbank pruefen.'
    return (f"Premium: {'an' if s['premium_aktiv'] else 'aus'}\n"
            f"Lokaler Kostenrahmen inkl. Reservierungen: heute {s['tag_usd']:.4f}/{s['tageslimit_usd']} USD, "
            f"Monat {s['monat_usd']:.4f}/{s['monatslimit_usd']} USD.\n"
            'Gilt fuer konfigurierte Premium-Textmodelle dieser Installation, kein Anbieter-Rechnungsstand.')
