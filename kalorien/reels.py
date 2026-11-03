"""Fit-App - Reels: kurze Hochkant-Videos (max. 60 s) im Fitness-Feed.

Ablauf: Upload (roh, gestreamt auf die Platte) -> Warteschlange -> ffmpeg wandelt in H.264/AAC-MP4 (max. 720x1280, ohne Hochskalieren,
faststart) + Vorschaubild -> Reel erscheint. So spielt jedes Geraet es ab - auch wenn das iPhone HEVC/MOV liefert.

Sicherheit (Videos kommen von Fremden):
  * nur echte MP4/MOV (ftyp) oder WebM/Matroska (EBML) - Dateikopf wird geprueft, nicht der Name
  * ffmpeg darf NUR lokale Dateien lesen (-protocol_whitelist file): keine Playlist-Tricks auf Netz oder fremde Dateien
  * ffmpeg laeuft mit Zeit- und Groessengrenze, mit niedriger Prioritaet, immer nur EIN Auftrag gleichzeitig
  * Rohmaterial wird nach der Umwandlung geloescht; Dateinamen sind Zufall (nicht erratbar)"""
from __future__ import annotations

import json
import os
import queue
import re
import secrets
import shutil
import subprocess
import sys
import threading

from . import db, sozial

MAX_ROH = 250 * 1024 * 1024        # Upload-Grenze (iPhone-Videos sind gross)
MAX_SEKUNDEN = 60
UMWANDELN_MAX_SEK = 600            # laenger darf ffmpeg nicht brauchen
MIN_FREI = 3 * 1024 ** 3           # unter 3 GB freiem Platz nimmt der Server keine Videos mehr an
NAME = re.compile(r"^[0-9a-f]{24}\.mp4$")

_auftraege: "queue.Queue[int]" = queue.Queue()
_worker: threading.Thread | None = None
_sperre = threading.Lock()


class ReelFehler(Exception):
    def __init__(self, status: int, text: str) -> None:
        super().__init__(text)
        self.status, self.text = status, text


def _programm(name: str) -> str | None:
    return shutil.which(os.getenv(f"KALORIEN_{name.upper()}") or name)


def verfuegbar() -> bool:
    return bool(_programm("ffmpeg") and _programm("ffprobe"))


def kopf_pruefen(b: bytes) -> bool:
    """Echtes MP4/MOV (Box 'ftyp' ab Byte 4) oder WebM/Matroska (EBML-Kopf)."""
    return (len(b) >= 12 and b[4:8] == b"ftyp") or b[:4] == b"\x1a\x45\xdf\xa3"


def dateien_loeschen(video: str = "", poster: str = "", roh: str = "") -> None:
    if video and NAME.match(video):
        (db.VIDEOS / video).unlink(missing_ok=True)
    sozial.bild_loeschen(poster)
    if roh and re.fullmatch(r"roh_[0-9a-f]{24}\.bin", roh):
        (db.VIDEOS / roh).unlink(missing_ok=True)


# ------------------------------------------------------------------ Upload
def hochladen(c, z, strom, laenge: int, text: str, limit_tag: int) -> dict:
    """Raw-Upload (Body = Videodatei). strom = Socket-Datei (rfile)."""
    if not verfuegbar():
        raise ReelFehler(503, "Videos sind auf diesem Server nicht eingerichtet (ffmpeg fehlt).")
    if not 1024 < laenge <= MAX_ROH:
        raise ReelFehler(413, f"Das Video ist leer oder größer als {MAX_ROH // 1024 // 1024} MB. Kürze es auf höchstens {MAX_SEKUNDEN} Sekunden.")
    n_heute = c.execute("SELECT COUNT(*) FROM beitrag WHERE nutzer=? AND art='reel' AND erstellt>?", (z["id"], db.jetzt() - 86400)).fetchone()[0]
    if n_heute >= limit_tag:
        raise ReelFehler(429, f"Heute sind {limit_tag} Reels erreicht. Morgen geht's weiter" + (" – oder mit Pro mehr." if limit_tag < 10 else "."))
    if c.execute("SELECT COUNT(*) FROM beitrag WHERE art='reel' AND status='wartet'").fetchone()[0] >= 12:
        raise ReelFehler(503, "Gerade werden viele Videos verarbeitet. Bitte in ein paar Minuten nochmal.")
    db.VIDEOS.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(db.VIDEOS).free < MIN_FREI + laenge:
        raise ReelFehler(507, "Der Server hat gerade zu wenig Speicherplatz für Videos.")
    roh = f"roh_{secrets.token_hex(12)}.bin"
    pfad = db.VIDEOS / roh
    rest, erster = laenge, True
    try:
        with open(pfad, "wb") as f:
            while rest > 0:
                stueck = strom.read(min(1 << 20, rest))
                if not stueck:
                    raise ReelFehler(400, "Der Upload ist abgebrochen.")
                if erster:
                    if not kopf_pruefen(stueck):
                        raise ReelFehler(400, "Das ist kein Video (MP4, MOV oder WebM).")
                    erster = False
                f.write(stueck)
                rest -= len(stueck)
    except BaseException:
        pfad.unlink(missing_ok=True)
        raise
    cur = c.execute("INSERT INTO beitrag(nutzer, art, text, bild, erstellt, status, roh) VALUES (?,?,?,?,?,?,?)",
                    (z["id"], "reel", text, "", db.jetzt(), "wartet", roh))
    c.commit()   # erst jetzt darf der Worker den Auftrag sehen
    worker_starten()
    _auftraege.put(cur.lastrowid)
    return {"id": cur.lastrowid, "status": "wartet"}


def status(c, z, rid: int) -> dict:
    r = c.execute("SELECT status FROM beitrag WHERE id=? AND nutzer=? AND art='reel'", (rid, z["id"])).fetchone()
    if not r:
        raise ReelFehler(404, "Reel nicht gefunden.")
    return {"id": rid, "status": r["status"]}


# ------------------------------------------------------------------ Umwandlung
def _lauf(args: list[str], timeout: float) -> subprocess.CompletedProcess:
    pre = ["nice", "-n", "10"] if sys.platform.startswith("linux") and shutil.which("nice") else []   # nur Linux: MSYS-nice verschluckt Anfuehrungszeichen
    return subprocess.run(pre + args, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _pruefen(pfad) -> dict:
    p = _lauf([_programm("ffprobe"), "-v", "error", "-protocol_whitelist", "file", "-select_streams", "v:0",
               "-show_entries", "stream=codec_name,width,height,avg_frame_rate:format=duration", "-of", "json", str(pfad)], 30)
    try:
        d = json.loads(p.stdout or b"{}")
        s = d["streams"][0]
        dauer = float(d["format"]["duration"])
    except (ValueError, KeyError, IndexError):
        raise ReelFehler(400, "Das Video ist nicht lesbar.")
    if dauer <= 0.3:
        raise ReelFehler(400, "Das Video ist zu kurz.")
    try:
        zaehler, nenner = (s.get("avg_frame_rate") or "0/1").split("/")
        fps = float(zaehler) / float(nenner or 1)
    except (ValueError, ZeroDivisionError):
        fps = 30.0
    return {"dauer": dauer, "fps": fps}


def umwandeln(rid: int) -> None:
    c = db.verbinden()
    r = c.execute("SELECT roh, nutzer FROM beitrag WHERE id=? AND art='reel' AND status='wartet'", (rid,)).fetchone()
    if not r:
        c.close()
        return
    roh = db.VIDEOS / r["roh"]
    ziel_name, poster_name = secrets.token_hex(12) + ".mp4", secrets.token_hex(12) + ".jpg"
    ziel, poster = db.VIDEOS / ziel_name, db.BILDER / poster_name
    try:
        info = _pruefen(roh)
        # Hoechstens 720x1280 (Hochkant) bzw. 1280x720 (Quer); nie hochskalieren; gerade Seitenlaengen (H.264)
        skala = "scale='min(iw,if(gt(a,1),1280,720))':'min(ih,if(gt(a,1),720,1280))':force_original_aspect_ratio=decrease:force_divisible_by=2"
        args = [_programm("ffmpeg"), "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-protocol_whitelist", "file", "-i", str(roh),
                "-t", str(MAX_SEKUNDEN), "-map", "0:v:0", "-map", "0:a:0?", "-vf", skala + ",format=yuv420p",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-maxrate", "3500k", "-bufsize", "7000k", "-threads", "2",
                "-c:a", "aac", "-b:a", "96k", "-ac", "2", "-movflags", "+faststart", "-map_metadata", "-1"]   # keine Metadaten (GPS!)
        if info["fps"] > 31:
            args += ["-r", "30"]
        p = _lauf(args + [str(ziel)], UMWANDELN_MAX_SEK)
        if p.returncode != 0 or not ziel.exists() or ziel.stat().st_size < 1000:
            print(f"[Reels] ffmpeg-Fehler {p.returncode}: {(p.stderr or b'')[-1500:].decode('utf-8', 'replace')}", flush=True)
            raise ReelFehler(400, "Das Video konnte nicht umgewandelt werden.")
        db.BILDER.mkdir(parents=True, exist_ok=True)
        for stelle in ("0.4", "0"):
            _lauf([_programm("ffmpeg"), "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-protocol_whitelist", "file", "-ss", stelle,
                   "-i", str(ziel), "-frames:v", "1", "-vf", "scale=540:-2", "-q:v", "5", str(poster)], 60)
            if poster.exists() and poster.stat().st_size > 500:
                break
        c.execute("UPDATE beitrag SET video=?, poster=?, status='fertig', dauer=?, roh='' WHERE id=?",
                  (ziel_name, poster_name if poster.exists() else "", round(min(info["dauer"], MAX_SEKUNDEN), 1), rid))
    except (ReelFehler, subprocess.TimeoutExpired, OSError) as e:
        print(f"[Reels] {rid}: {type(e).__name__}: {e}", flush=True)
        ziel.unlink(missing_ok=True)
        poster.unlink(missing_ok=True)
        c.execute("UPDATE beitrag SET status='fehler', roh='' WHERE id=?", (rid,))
    finally:
        roh.unlink(missing_ok=True)
        c.commit()
        c.close()


def _arbeit() -> None:
    while True:
        rid = _auftraege.get()
        try:
            umwandeln(rid)
        except Exception as e:   # der Worker darf nie sterben
            print(f"[Reels] Worker-Fehler {rid}: {type(e).__name__}: {e}", flush=True)


def worker_starten() -> None:
    global _worker
    with _sperre:
        if _worker and _worker.is_alive():
            return
        _worker = threading.Thread(target=_arbeit, daemon=True, name="reels-worker")
        _worker.start()


def wiederaufnehmen() -> None:
    """Beim Serverstart: haengende Auftraege (Neustart mitten in der Umwandlung) erneut einreihen oder als Fehler markieren."""
    c = db.verbinden()
    try:
        for r in c.execute("SELECT id, roh FROM beitrag WHERE art='reel' AND status='wartet'").fetchall():
            if r["roh"] and (db.VIDEOS / r["roh"]).exists():
                _auftraege.put(r["id"])
            else:
                c.execute("UPDATE beitrag SET status='fehler', roh='' WHERE id=?", (r["id"],))
        c.commit()
    finally:
        c.close()
    if not _auftraege.empty():
        worker_starten()


# ------------------------------------------------------------------ Feed
def feed(c, z, nur_folge: bool, vor: int, von: str) -> list[dict]:
    sql, arg = sozial._SEL + " AND b.video!='' AND b.status='fertig'", [z["id"], z["id"]]
    if nur_folge:
        sql += " AND b.nutzer IN (SELECT ziel FROM folgen WHERE von=?)"
        arg.append(z["id"])
    if von:
        sql += " AND n.name=?"
        arg.append(von)
    if vor > 0:
        sql += " AND b.id<?"
        arg.append(vor)
    weg = sozial._weg(c, z)
    zeilen = c.execute(sql + " ORDER BY b.id DESC LIMIT 40", arg).fetchall()
    return [sozial._beitrag_dict(r, z) for r in zeilen if r["nutzer"] not in weg][:12]


def konto_dateien(c, nutzer: int) -> list[tuple[str, str, str]]:
    return [(r["video"], r["poster"], r["roh"]) for r in c.execute("SELECT video, poster, roh FROM beitrag WHERE nutzer=? AND art='reel'", (nutzer,))]


# ------------------------------------------------------------------ Ausliefern mit Range (Safari spielt ohne Range-Unterstuetzung nichts ab)
def lesen_bereich(name: str, bereich: str | None):
    """-> (Datei, start, ende_inklusive, gesamt, teilweise) oder None. Datei muss vom Aufrufer geschlossen werden."""
    if not NAME.match(name or ""):
        return None
    pfad = db.VIDEOS / name
    try:
        gesamt = pfad.stat().st_size
    except OSError:
        return None
    start, ende, teil = 0, gesamt - 1, False
    m = re.fullmatch(r"bytes=(\d*)-(\d*)", (bereich or "").strip())
    if m and (m.group(1) or m.group(2)):
        if m.group(1):
            start = int(m.group(1))
            ende = int(m.group(2)) if m.group(2) else gesamt - 1
        else:
            start, ende = max(0, gesamt - int(m.group(2))), gesamt - 1
        ende = min(ende, gesamt - 1)
        if start > ende:
            return ("ungueltig", gesamt)
        teil = True
    return open(pfad, "rb"), start, ende, gesamt, teil

