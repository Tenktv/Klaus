// Markt-Analyse (Holo-Pop-up "markt") + Papier-Depot-Widget. Daten aus markt.py. Nur Analyse, keine Anlageberatung.

POPUP_GROESSE.markt = [0.5, 0.74];
POPUP_DAUER.markt = 300;
POPUP_TITEL.markt = "MARKT-ANALYSE";
if (typeof ZWEIT_ARTEN !== "undefined") ZWEIT_ARTEN.add("markt");   // gross -> wenn moeglich auf Bildschirm 2

const zahlDE = (z, n = 2) => (z ?? 0).toLocaleString("de-DE", { minimumFractionDigits: n, maximumFractionDigits: n });

POPUP_ARTEN.markt = function (box) {
  box.classList.add("p-markt");
  box.innerHTML = `<div class="mk-kopf"><div><b class="mk-name"></b><small class="mk-sym"></small></div>
      <div class="mk-preis"><b></b><span></span></div></div>
    <div class="mk-haupt"><div class="mk-charts"><canvas class="mk-kurs"></canvas><canvas class="mk-rsi"></canvas>
      <div class="mk-legende"><i style="--f:#fff"></i>KURS <i style="--f:var(--bernstein)"></i>SMA 20 <i style="--f:#6cb4ff"></i>SMA 50 <i style="--f:var(--eye)"></i>RSI 14</div></div>
      <aside class="mk-seite"><div class="mk-chips"></div><div class="lbl">Nachrichtenlage</div><div class="mk-stimmung"><i></i></div>
        <div class="mk-stimmung-text"></div><div class="mk-news"></div></aside></div>
    <div class="mk-fuss"></div>`;
  const q = (s) => box.querySelector(s);
  let d = null;

  function linie(ctx, werte, x, y, farbe, breite = 1.3) {
    ctx.strokeStyle = farbe; ctx.lineWidth = breite; ctx.beginPath();
    let an = false;
    werte.forEach((v, i) => { if (v == null) { an = false; return; } an ? ctx.lineTo(x(i), y(v)) : ctx.moveTo(x(i), y(v)); an = true; });
    ctx.stroke();
  }

  function zeichnen() {
    if (!d) return;
    const rgb = getComputedStyle(document.documentElement).getPropertyValue("--rgb").trim();
    const amber = getComputedStyle(document.documentElement).getPropertyValue("--bernstein").trim() || "#ffb300";
    for (const [sel, art] of [[".mk-kurs", "kurs"], [".mk-rsi", "rsi"]]) {
      const cv = q(sel), ctx = cv.getContext("2d"), dpr = Math.min(1.5, devicePixelRatio || 1), w = cv.clientWidth, h = cv.clientHeight;
      if (!w || !h) continue;
      cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      const n = d.kurse.length, x = (i) => 6 + (i / (n - 1)) * (w - 52);
      if (art === "kurs") {
        const alle = [...d.kurse, ...d.verlauf_sma20.filter((v) => v != null), ...d.verlauf_sma50.filter((v) => v != null)];
        const lo = Math.min(...alle), hi = Math.max(...alle), y = (v) => 10 + (1 - (v - lo) / (hi - lo || 1)) * (h - 26);
        ctx.strokeStyle = `rgba(${rgb},.08)`; ctx.lineWidth = 1; ctx.font = "10px 'JetBrains Mono', monospace"; ctx.fillStyle = "rgba(220,210,205,.6)";
        for (let k = 0; k <= 4; k++) {   // Raster + Preis-Achse rechts
          const v = lo + ((hi - lo) * k) / 4, yy = y(v);
          ctx.beginPath(); ctx.moveTo(6, yy); ctx.lineTo(w - 46, yy); ctx.stroke();
          ctx.fillText(zahlDE(v, v > 1000 ? 0 : 2), w - 42, yy + 3);
        }
        const gut = d.kurse[n - 1] >= d.kurse[0], f = gut ? "60,245,155" : "255,61,90";
        const g = ctx.createLinearGradient(0, 0, 0, h);
        g.addColorStop(0, `rgba(${f},.22)`); g.addColorStop(1, `rgba(${f},0)`);
        ctx.fillStyle = g; ctx.beginPath(); ctx.moveTo(x(0), h - 16);
        d.kurse.forEach((v, i) => ctx.lineTo(x(i), y(v))); ctx.lineTo(x(n - 1), h - 16); ctx.fill();
        linie(ctx, d.verlauf_sma50, x, y, "#6cb4ff", 1.1);
        linie(ctx, d.verlauf_sma20, x, y, amber, 1.1);
        linie(ctx, d.kurse, x, y, "#fff", 1.6);
        ctx.fillStyle = `rgb(${f})`; ctx.beginPath(); ctx.arc(x(n - 1), y(d.kurse[n - 1]), 3.5, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = "rgba(220,210,205,.55)";   // Monate unten
        let mon = "";
        d.tage.forEach((t, i) => { const m = t.slice(5, 7); if (m !== mon) { mon = m; ctx.fillText(new Date(t).toLocaleDateString("de-DE", { month: "short" }).toUpperCase(), x(i), h - 3); } });
      } else {
        const y = (v) => 4 + (1 - v / 100) * (h - 8);
        ctx.fillStyle = `rgba(${rgb},.06)`; ctx.fillRect(6, y(70), w - 52, y(30) - y(70));
        ctx.strokeStyle = `rgba(${rgb},.25)`; ctx.setLineDash([3, 4]);
        for (const g of [30, 70]) { ctx.beginPath(); ctx.moveTo(6, y(g)); ctx.lineTo(w - 46, y(g)); ctx.stroke(); }
        ctx.setLineDash([]);
        const eye = getComputedStyle(document.body).getPropertyValue("--eye").trim() || `rgb(${rgb})`;
        linie(ctx, d.verlauf_rsi, x, y, eye, 1.3);
        ctx.fillStyle = "rgba(220,210,205,.6)"; ctx.font = "10px 'JetBrains Mono', monospace";
        ctx.fillText("70", w - 42, y(70) + 3); ctx.fillText("30", w - 42, y(30) + 3);
      }
    }
  }
  new ResizeObserver(zeichnen).observe(q(".mk-charts"));

  return {
    update(neu) {
      if (!neu.kurse) return;
      d = neu;
      q(".mk-name").textContent = d.name;
      q(".mk-sym").textContent = d.symbol;
      q(".mk-preis b").textContent = `${zahlDE(d.preis, d.preis > 1000 ? 0 : 2)} ${d.waehrung}`;
      q(".mk-preis span").textContent = `${d.tag >= 0 ? "▲" : "▼"} ${zahlDE(Math.abs(d.tag))} %`;
      q(".mk-preis span").className = d.tag >= 0 ? "plus" : "minus";
      const chip = (name, wert, klasse = "") => `<div class="mk-chip ${klasse}"><span>${name}</span><b>${wert}</b></div>`;
      q(".mk-chips").innerHTML = chip("Trend", d.trend.toUpperCase(), d.trend === "aufwärts" ? "plus" : d.trend === "abwärts" ? "minus" : "")
        + chip("RSI 14", `${d.rsi ?? "–"} · ${d.rsi_zone}`, d.rsi_zone === "überkauft" ? "warn" : d.rsi_zone === "überverkauft" ? "warn" : "")
        + chip("1 Monat", d.veraenderung_1m == null ? "–" : `${d.veraenderung_1m >= 0 ? "+" : ""}${zahlDE(d.veraenderung_1m)} %`, (d.veraenderung_1m ?? 0) >= 0 ? "plus" : "minus")
        + chip("MACD", d.macd_kreuz ? `${d.macd_kreuz.toUpperCase()}ES KREUZ` : (d.macd > d.macd_signal ? "ÜBER SIGNAL" : "UNTER SIGNAL"));
      const s = d.stimmung || { wert: 0, text: "" };
      q(".mk-stimmung i").style.left = `${((s.wert + 1) / 2) * 100}%`;
      q(".mk-stimmung-text").textContent = `${s.text}${s.quelle && s.quelle !== "-" ? ` (${s.quelle})` : ""}`;
      const news = q(".mk-news");
      news.innerHTML = "";
      for (const m of (d.meldungen || []).slice(0, 6)) {
        const z = el("button", "mk-meldung");
        z.append(el("span", "", m.titel), el("small", "", m.alter ? `VOR ${m.alter.toUpperCase()}` : ""));
        z.onclick = () => webOeffnen(m.link);
        news.append(z);
      }
      q(".mk-fuss").textContent = `${d.hinweis || "Nur Analyse, keine Anlageberatung."} · DATEN: YAHOO FINANCE, GOOGLE NEWS · 6 MONATE, TAGESKURSE`;
      setTimeout(zeichnen, 30);
    },
  };
};

// ------------------------------------------------------------------ Papier-Depot (Widget)
if (typeof TYPEN !== "undefined") {
  TYPEN.depot = {
    titel: "Papier-Depot", info: "Spielgeld-Depot zum Üben – keine echten Orders", w: 4, h: 9, minW: 3, minH: 4,
    bauen(c) {
      c.extra.textContent = "SPIELGELD";
      c.abo("depot", "", 300, (d) => {
        if (d.fehler) { c.inhalt.innerHTML = '<div class="leer">DEPOT NICHT LESBAR</div>'; return; }
        c.inhalt.innerHTML = `<div class="dp-kopf"><div><span class="lbl">Depotwert</span><b>${zahlDE(d.wert, 0)} €</b></div>
          <div class="${d.gv_proz >= 0 ? "plus" : "minus"}">${d.gv_proz >= 0 ? "▲" : "▼"} ${zahlDE(Math.abs(d.gv_proz))} %</div>
          <div><span class="lbl">Bargeld</span><b>${zahlDE(d.bargeld, 0)} €</b></div></div>`;
        for (const p of d.positionen || []) {
          const z = el("div", "dp-pos");
          z.append(el("b", "", p.symbol), el("span", "", `${zahlDE(p.wert_eur, 0)} €`),
                   el("small", p.gv_proz >= 0 ? "plus" : "minus", `${p.gv_proz >= 0 ? "+" : ""}${zahlDE(p.gv_proz)} %`));
          c.inhalt.append(z);
        }
        if (!(d.positionen || []).length) c.inhalt.append(el("div", "leer", "NOCH LEER · „KLAUS, KAUF FÜR 1000 EURO NVIDIA IM PAPIERDEPOT“"));
      });
    },
  };
}
