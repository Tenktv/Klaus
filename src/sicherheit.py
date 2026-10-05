"""
Klaus - Sicherheit: Windows Defender statt Eigenbau-Scanner + Waechter mit Basislinie.

    sicherheit.lage()        Defender, Firewall, Bedrohungen, Waechter-Warnungen (fuers Widget, ~3 s)
    sicherheit.scan(art)     "schnell" | "voll" | Pfad - ohne Adminrechte, sonst ueber admin.py (Freigabe + UAC)
    sicherheit.bestaetigen() aktuellen Stand als neue Basislinie uebernehmen ("Klaus, Sicherheit bestaetigen")

Waechter (Vergleich mit data/sicherheit_basis.json): neue Autostart-Eintraege, neue Admin-Konten, neue offene Ports,
unsignierte Programme mit Netzverbindung. Erster Lauf legt die Basislinie an.
"""
from __future__ import annotations

import json
import subprocess

import daten

BASIS = daten.BASE_DIR / "data" / "sicherheit_basis.json"
KEIN_FENSTER = getattr(subprocess, "CREATE_NO_WINDOW", 0)

ABFRAGE = r"""
$ErrorActionPreference = 'SilentlyContinue'
$mp = Get-MpComputerStatus
$fw = Get-NetFirewallProfile | % { @{ name = "$($_.Name)"; an = [bool]$_.Enabled } }
$bedrohung = Get-MpThreatDetection | Sort-Object InitialDetectionTime -Descending | Select-Object -First 5 | % {
  @{ zeit = $_.InitialDetectionTime.ToString('dd.MM.yyyy HH:mm'); name = (Get-MpThreat -ThreatID $_.ThreatID).ThreatName; erledigt = [bool]($_.ActionSuccess) } }
$auto = @(Get-CimInstance Win32_StartupCommand | % { "$($_.Name) | $($_.Command)" })
$auto += @(foreach ($k in 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run','HKLM:\Software\Microsoft\Windows\CurrentVersion\Run') {
  $e = Get-ItemProperty $k; if ($e) { $e.PSObject.Properties | ? { $_.Name -notlike 'PS*' } | % { "$($_.Name) | $($_.Value)" } } })
$auto = @($auto | Sort-Object -Unique)
$admins = Get-LocalGroupMember -SID 'S-1-5-32-544' | % { "$($_.Name)" }
$ports = Get-NetTCPConnection -State Listen | ? { $_.LocalAddress -notin '127.0.0.1','::1' } | % {
  $p = Get-Process -Id $_.OwningProcess; "$($_.LocalPort) $($p.ProcessName)" } | Sort-Object -Unique
$pfade = Get-NetTCPConnection -State Established | ? { $_.RemoteAddress -notin '127.0.0.1','::1' } | % { (Get-Process -Id $_.OwningProcess).Path } |
  ? { $_ } | Sort-Object -Unique | Select-Object -First 40
$unsigniert = $pfade | ? { (Get-AuthenticodeSignature $_).Status -ne 'Valid' }
@{
  defender = @{ an = [bool]$mp.AntivirusEnabled; echtzeit = [bool]$mp.RealTimeProtectionEnabled;
                signatur = if ($mp.AntivirusSignatureLastUpdated) { $mp.AntivirusSignatureLastUpdated.ToString('dd.MM.yyyy HH:mm') } else { '' };
                signatur_alter_h = if ($mp.AntivirusSignatureLastUpdated) { [int]((Get-Date) - $mp.AntivirusSignatureLastUpdated).TotalHours } else { -1 };
                schnellscan_tage = $mp.QuickScanAge; vollscan_tage = $mp.FullScanAge }
  firewall = @($fw); bedrohungen = @($bedrohung); autostart = @($auto); admins = @($admins); ports = @($ports); unsigniert = @($unsigniert)
} | ConvertTo-Json -Depth 4 -Compress
"""


def _ps(skript: str, timeout: float = 90) -> str:
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", skript], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=timeout, creationflags=KEIN_FENSTER)
    return r.stdout.strip()


def _basis() -> dict | None:
    try:
        return json.loads(BASIS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def lage() -> dict:
    roh = json.loads(_ps(ABFRAGE) or "{}")
    basis = _basis()
    if basis is None:  # erster Lauf: so ist der PC jetzt -> das ist "normal"
        basis = {k: roh.get(k, []) for k in ("autostart", "admins", "ports", "unsigniert")}
        BASIS.write_text(json.dumps(basis, ensure_ascii=False, indent=1), encoding="utf-8")
    warnungen = []
    d = roh.get("defender", {})
    if not d.get("an") or not d.get("echtzeit"):
        warnungen.append({"art": "defender", "text": "Defender-Echtzeitschutz ist AUS."})
    if d.get("signatur_alter_h", 0) > 72:
        warnungen.append({"art": "defender", "text": f"Virendefinitionen sind {d['signatur_alter_h'] // 24} Tage alt."})
    if (d.get("vollscan_tage") or 0) > 30:
        warnungen.append({"art": "hinweis", "text": f"Letzter vollständiger Scan vor {d['vollscan_tage']} Tagen."})
    for p in roh.get("firewall", []):
        if not p.get("an"):
            warnungen.append({"art": "firewall", "text": f"Firewall-Profil {p['name']} ist aus."})
    for b in roh.get("bedrohungen", []):
        if not b.get("erledigt"):
            warnungen.append({"art": "bedrohung", "text": f"Bedrohung nicht beseitigt: {b.get('name')} ({b.get('zeit')})"})
    for schluessel, text in (("autostart", "Neuer Autostart-Eintrag"), ("admins", "Neues Admin-Konto"),
                             ("ports", "Neuer offener Port"), ("unsigniert", "Unsigniertes Programm mit Netzverbindung")):
        for neu in sorted(set(roh.get(schluessel, [])) - set(basis.get(schluessel, []))):
            warnungen.append({"art": schluessel, "text": f"{text}: {neu[:120]}"})
    return {"defender": d, "firewall": roh.get("firewall", []), "bedrohungen": roh.get("bedrohungen", []),
            "warnungen": warnungen, "zaehler": {k: len(roh.get(k, [])) for k in ("autostart", "admins", "ports", "unsigniert")}}


def bestaetigen(token: str | None) -> str:
    """Neue Basislinie - nur mit Freigabe-Token (sonst koennte ein Angreifer Warnungen einfach wegklicken lassen)."""
    import freigabe

    freigabe.pruefe(token, "sicherheit")
    roh = json.loads(_ps(ABFRAGE) or "{}")
    BASIS.write_text(json.dumps({k: roh.get(k, []) for k in ("autostart", "admins", "ports", "unsigniert")}, ensure_ascii=False, indent=1),
                     encoding="utf-8")
    return "Der aktuelle Stand ist jetzt die neue Basislinie. Neue Änderungen melde ich ab jetzt."


def scan(art: str = "schnell", token: str | None = None) -> str:
    """Erst ohne Adminrechte versuchen; klappt das nicht, ueber admin.py (braucht Token der Art 'admin')."""
    import admin

    if art not in ("schnell", "voll"):
        befehl, admin_name = f"Start-MpScan -ScanType CustomScan -ScanPath '{art}'", "defender_pfad"
    else:
        befehl = "Start-MpScan -ScanType " + ("QuickScan" if art == "schnell" else "FullScan")
        admin_name = "defender_schnellscan" if art == "schnell" else "defender_vollscan"
    if art == "voll":  # dauert Stunden: nicht blockieren
        return admin.ausfuehren(admin_name, token)
    aus = _ps(f"try {{ {befehl}; 'OK' }} catch {{ 'FEHLER ' + $_.Exception.Message }}", timeout=1800)
    if aus.startswith("OK"):
        return "Scan fertig. " + _ergebnis()
    if token:
        return admin.ausfuehren(admin_name, token, pfad=art if admin_name == "defender_pfad" else "") + " " + _ergebnis()
    raise PermissionError("Der Scan braucht Adminrechte.")


def _ergebnis() -> str:
    b = [x for x in lage()["bedrohungen"] if not x.get("erledigt")]
    return f"Achtung: {len(b)} Bedrohung(en) nicht beseitigt." if b else "Keine offenen Bedrohungen."


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    l = lage()
    print("Defender:", l["defender"])
    print("Firewall:", l["firewall"])
    print("Zaehler:", l["zaehler"])
    print("Warnungen:", [w["text"][:90] for w in l["warnungen"]])
