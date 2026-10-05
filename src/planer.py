"""
Klaus - Plaene und eigene Widgets.

Ein Plan = Titel, Ziel und Boxen. Box = {titel, art, eintraege}; art: liste | notiz | zeitplan | zahlen.
  - Im Gespraech fuellt Gemini Live den Plan direkt (Werkzeug plan_zeigen) - es kennt ja den Zusammenhang.
  - Lokal ("Klaus, lass uns ... planen") entwirft ein Gemini-Textmodell (kostenlos) den Plan als JSON, sonst Ollama.
Gespeichert: data/plaene/<slug>.json (zum Wiederoeffnen) + Notiz im Vault (Plaene/<Titel>.md).
"""
from __future__ import annotations

import datetime as dt
import json
import re

import daten
import gehirn

ORDNER = daten.BASE_DIR / "data" / "plaene"
ARTEN = ("liste", "notiz", "zeitplan", "zahlen")

AUFTRAG = """Erstelle einen konkreten, umsetzbaren Plan zum Thema: {thema}
{details}
Antworte NUR mit JSON in genau dieser Form (deutsch, kurz, keine Erklaerung drumherum):
{{"titel": "kurzer Titel", "ziel": "ein Satz",
  "boxen": [{{"titel": "Schritte", "art": "liste", "eintraege": ["...", "..."]}},
            {{"titel": "Zeitplan", "art": "zeitplan", "eintraege": ["Woche 1 | ...", "Woche 2 | ..."]}},
            {{"titel": "Budget", "art": "zahlen", "eintraege": ["Gesamt: 500 €", "..."]}},
            {{"titel": "Risiken", "art": "notiz", "eintraege": ["...", "..."]}}]}}
4 bis 6 Boxen, passend zum Thema (z. B. Ziele, Schritte, Zeitplan, To-dos, Ressourcen, Risiken, Budget, Ideen).
art ist eine von: liste (abhakbare Punkte), notiz (Absaetze), zeitplan ("Zeitpunkt | Aufgabe"), zahlen ("Name: Wert").
Jede Box 3 bis 6 Eintraege. Nichts erfinden, was du nicht weisst - lieber allgemein und ehrlich."""


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9äöüß]+", "-", text.lower()).strip("-")
    return s[:50] or "plan"


def pruefen(plan: dict) -> dict:
    """Plan saeubern: Arten erzwingen, Eintraege als Text, Grenzen einhalten."""
    boxen = []
    for b in (plan.get("boxen") or [])[:8]:
        art = b.get("art") if b.get("art") in ARTEN else "liste"
        eintraege = [str(e.get("text", e) if isinstance(e, dict) else e).strip()[:200] for e in (b.get("eintraege") or [])][:12]
        if b.get("titel") and eintraege:
            boxen.append({"titel": str(b["titel"])[:40], "art": art, "eintraege": eintraege})
    if not boxen:
        raise ValueError("Der Plan hat keine Boxen.")
    return {"titel": str(plan.get("titel") or "Plan")[:60], "ziel": str(plan.get("ziel") or "")[:200], "boxen": boxen,
            "erstellt": plan.get("erstellt") or dt.datetime.now().strftime("%d.%m.%Y %H:%M")}


def entwerfen(thema: str, details: str = "") -> dict:
    """Plan von einem Textmodell entwerfen lassen (Gemini kostenlos, sonst Ollama)."""
    import recherche

    auftrag = AUFTRAG.format(thema=thema, details=f"Details vom Nutzer: {details}" if details else "")
    try:
        text = recherche.gemini(auftrag, "Du bist ein praeziser Projektplaner. Du antwortest nur mit gueltigem JSON.")
    except Exception:
        import llm

        text = llm.frage(auftrag, system="Antworte nur mit gueltigem JSON.")
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("Das Modell hat keinen Plan geliefert.")
    return pruefen(json.loads(m.group(0)))


def speichern(plan: dict) -> str:
    ORDNER.mkdir(parents=True, exist_ok=True)
    name = slug(plan["titel"])
    (ORDNER / f"{name}.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    # Notiz im Vault (lesbar in Obsidian)
    zeilen = [f"---\ntags: [klaus, plan]\n---\n# {plan['titel']}\n\nfür [[Nikola]] · erstellt {plan['erstellt']}\n"]
    if plan.get("ziel"):
        zeilen.append(f"**Ziel:** {plan['ziel']}\n")
    for b in plan["boxen"]:
        zeilen.append(f"## {b['titel']}\n")
        for e in b["eintraege"]:
            zeilen.append(f"- [ ] {e}" if b["art"] == "liste" else f"- {e}")
        zeilen.append("")
    dateiname = re.sub(r'[\\/:*?"<>|]', "", plan["titel"])[:60] or "Plan"
    datei = gehirn.VAULT / "Plaene" / f"{dateiname}.md"
    datei.parent.mkdir(parents=True, exist_ok=True)
    datei.write_text("\n".join(zeilen), encoding="utf-8")
    return name


def laden(titel: str) -> dict | None:
    """Gespeicherten Plan per (Teil-)Titel finden, sonst den neuesten."""
    dateien = sorted(ORDNER.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True) if ORDNER.exists() else []
    such = slug(titel) if titel.strip() else ""
    for p in dateien:
        if not such or such in p.stem:
            return json.loads(p.read_text(encoding="utf-8"))
    return None


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    p = entwerfen(" ".join(sys.argv[1:]) or "Website für eine Bäckerei in Göppingen")
    print(json.dumps(p, ensure_ascii=False, indent=1)[:1500])
