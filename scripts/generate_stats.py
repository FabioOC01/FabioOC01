#!/usr/bin/env python3
"""Genera las tarjetas SVG de estadísticas del perfil (modo claro y oscuro).

Solo usa la librería estándar. Lee GITHUB_TOKEN (o GH_TOKEN) y GITHUB_USER del
entorno y escribe los SVG en la carpeta stats/ del repo.
"""
import json
import os
import sys
import urllib.request
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

USER = os.environ.get("GITHUB_USER", "FabioOC01")
# Cuentas adicionales (p. ej. la de empresa) cuyas contribuciones se suman.
# Solo se leen los conteos públicos del calendario: nunca nombres de repos privados.
EXTRA_USERS = [u for u in os.environ.get("GITHUB_EXTRA_USERS", "OrlandoOchoa").split(",") if u.strip()]
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
OUT = Path(__file__).resolve().parent.parent / "stats"

# Lenguajes que no son código propiamente dicho.
IGNORED_LANGS = {"Dockerfile", "Procfile", "Batchfile", "Makefile", "Jupyter Notebook"}
TOP_LANGS = 6

FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans',Helvetica,Arial,sans-serif"

THEMES = {
    "light": {
        "bg": "#ffffff", "border": "#d0d7de", "title": "#1f2328",
        "text": "#1f2328", "muted": "#59636e", "grid": "#e6eaef",
        "accent": "#0969da", "accent_fill": "#0969da", "track": "#eef1f4",
    },
    "dark": {
        "bg": "#0d1117", "border": "#30363d", "title": "#e6edf3",
        "text": "#e6edf3", "muted": "#9198a1", "grid": "#21262d",
        "accent": "#4493f8", "accent_fill": "#4493f8", "track": "#21262d",
    },
}

MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

QUERY = """
query($login: String!) {
  user(login: $login) {
    repositoriesContributedTo(contributionTypes: [COMMIT, PULL_REQUEST, ISSUE]) { totalCount }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name } }
        }
      }
    }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      restrictedContributionsCount
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


def fetch(login):
    if not TOKEN:
        sys.exit("Falta GITHUB_TOKEN o GH_TOKEN en el entorno.")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": login.strip()}}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json",
                 "User-Agent": "profile-stats-script"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if payload.get("errors"):
        sys.exit(f"Error de la API de GitHub: {payload['errors']}")
    return payload["data"]["user"]


def merge(primary, extras):
    """Suma las contribuciones de las cuentas extra en los datos de la principal."""
    cc = primary["contributionsCollection"]
    cc["extraContributions"] = 0
    days = {d["date"]: d for w in cc["contributionCalendar"]["weeks"] for d in w["contributionDays"]}
    for other in extras:
        occ = other["contributionsCollection"]
        cc["extraContributions"] += occ["contributionCalendar"]["totalContributions"]
        cc["contributionCalendar"]["totalContributions"] += occ["contributionCalendar"]["totalContributions"]
        for key in ("totalCommitContributions", "totalPullRequestContributions", "restrictedContributionsCount"):
            cc[key] += occ[key]
        primary["repositoriesContributedTo"]["totalCount"] += other["repositoriesContributedTo"]["totalCount"]
        for w in occ["contributionCalendar"]["weeks"]:
            for d in w["contributionDays"]:
                if d["date"] in days:
                    days[d["date"]]["contributionCount"] += d["contributionCount"]
    return primary


def fmt(n):
    return f"{n:,}".replace(",", " ")


def card(width, height, theme, body, label):
    t = THEMES[theme]
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(label)}">'
        f'<title>{escape(label)}</title>'
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="8" '
        f'fill="{t["bg"]}" stroke="{t["border"]}"/>'
        f'<g font-family="{FONT}">{body}</g></svg>'
    )


def stats_svg(user, theme):
    t = THEMES[theme]
    cc = user["contributionsCollection"]
    total = cc["contributionCalendar"]["totalContributions"]
    stars = sum(r["stargazerCount"] for r in user["repositories"]["nodes"])
    rows = [
        ("Commits públicos", cc["totalCommitContributions"]),
        ("Contribuciones privadas", cc["restrictedContributionsCount"]),
        ("Desde mi cuenta de empresa", cc.get("extraContributions", 0)),
        ("Repos públicos", user["repositories"]["totalCount"]),
        ("Repos de otros con aportes", user["repositoriesContributedTo"]["totalCount"]),
    ]
    if cc["totalPullRequestContributions"]:
        rows.insert(1, ("Pull requests", cc["totalPullRequestContributions"]))
    if stars:
        rows.append(("Estrellas", stars))

    w, row_h, top = 460, 26, 62
    h = max(top + row_h * len(rows) + 14, 180)
    body = [
        f'<text x="24" y="36" font-size="16" font-weight="600" fill="{t["title"]}">Actividad en GitHub</text>',
        f'<text x="24" y="{h / 2 + 14}" font-size="44" font-weight="700" fill="{t["accent"]}">{fmt(total)}</text>',
        f'<text x="24" y="{h / 2 + 38}" font-size="12" fill="{t["muted"]}">contribuciones en el último año</text>',
        f'<line x1="186" y1="{top - 8}" x2="186" y2="{h - 22}" stroke="{t["grid"]}"/>',
    ]
    for i, (label, value) in enumerate(rows):
        y = top + 12 + i * row_h
        body.append(f'<text x="204" y="{y}" font-size="13" fill="{t["muted"]}">{escape(label)}</text>')
        body.append(f'<text x="{w - 24}" y="{y}" font-size="13" font-weight="600" text-anchor="end" '
                    f'fill="{t["text"]}">{fmt(value)}</text>')
    return card(w, h, theme, "".join(body), f"{fmt(total)} contribuciones en el último año")


def languages(user):
    totals = {}
    for repo in user["repositories"]["nodes"]:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            if name not in IGNORED_LANGS:
                totals[name] = totals.get(name, 0) + edge["size"]
    grand = sum(totals.values()) or 1
    top = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:TOP_LANGS]
    return [(name, size / grand * 100) for name, size in top]


def languages_svg(user, theme):
    t = THEMES[theme]
    langs = languages(user)
    w, row_h, top = 360, 26, 58
    h = max(top + row_h * len(langs) + 12, 180)
    label_w, pct_w = 108, 48
    bar_x, bar_w = 24 + label_w, w - 24 - label_w - pct_w - 24
    biggest = langs[0][1] if langs else 1
    body = [f'<text x="24" y="36" font-size="16" font-weight="600" fill="{t["title"]}">Lenguajes más usados</text>']
    for i, (name, pct) in enumerate(langs):
        y = top + i * row_h
        length = max(bar_w * pct / biggest, 4)
        body.append(f'<text x="24" y="{y + 11}" font-size="13" fill="{t["text"]}">{escape(name)}</text>')
        body.append(f'<rect x="{bar_x}" y="{y + 1}" width="{bar_w}" height="12" rx="4" fill="{t["track"]}"/>')
        body.append(f'<rect x="{bar_x}" y="{y + 1}" width="{length:.1f}" height="12" rx="4" fill="{t["accent_fill"]}"/>')
        body.append(f'<text x="{w - 24}" y="{y + 11}" font-size="12" text-anchor="end" '
                    f'fill="{t["muted"]}">{pct:.1f}%</text>')
    return card(w, h, theme, "".join(body), "Lenguajes más usados en repos públicos")


def activity_svg(user, theme):
    t = THEMES[theme]
    weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"]
    points = [(w["contributionDays"][0]["date"], sum(d["contributionCount"] for d in w["contributionDays"]))
              for w in weeks]
    w, h = 820, 220
    left, right, top, bottom = 48, 24, 56, 34
    pw, ph = w - left - right, h - top - bottom
    peak = max((c for _, c in points), default=0)
    # Tope del eje redondeado hacia arriba a un número "limpio".
    # Deja un poco de aire sobre el pico para su etiqueta.
    target = peak * 1.15
    step = next((s for s in (1, 2, 5, 10, 20, 25, 50, 100, 200, 500) if target / s <= 4), 1000)
    ymax = max(int(step * -(-target // step)), step)
    n = len(points)

    def x(i):
        return left + (pw * i / (n - 1) if n > 1 else 0)

    def y(v):
        return top + ph - ph * v / ymax

    body = [f'<text x="24" y="36" font-size="16" font-weight="600" fill="{t["title"]}">'
            f'Contribuciones por semana · último año</text>']
    for v in range(0, ymax + 1, step):
        body.append(f'<line x1="{left}" y1="{y(v):.1f}" x2="{w - right}" y2="{y(v):.1f}" stroke="{t["grid"]}"/>')
        body.append(f'<text x="{left - 8}" y="{y(v) + 4:.1f}" font-size="11" text-anchor="end" '
                    f'fill="{t["muted"]}">{v}</text>')
    last_month = None
    for i, (day, _) in enumerate(points):
        d = date.fromisoformat(day)
        if d.month != last_month and i > 0:
            body.append(f'<text x="{x(i):.1f}" y="{h - 12}" font-size="11" text-anchor="middle" '
                        f'fill="{t["muted"]}">{MONTHS[d.month - 1]}</text>')
        last_month = d.month
    if n:
        line = " ".join(f"{x(i):.1f},{y(c):.1f}" for i, (_, c) in enumerate(points))
        area = f"{x(0):.1f},{y(0):.1f} {line} {x(n - 1):.1f},{y(0):.1f}"
        body.append(f'<polygon points="{area}" fill="{t["accent_fill"]}" fill-opacity="0.15"/>')
        body.append(f'<polyline points="{line}" fill="none" stroke="{t["accent"]}" stroke-width="2" '
                    f'stroke-linejoin="round" stroke-linecap="round"/>')
        pi = max(range(n), key=lambda i: points[i][1])
        body.append(f'<circle cx="{x(pi):.1f}" cy="{y(points[pi][1]):.1f}" r="4" fill="{t["accent"]}" '
                    f'stroke="{t["bg"]}" stroke-width="2"/>')
        anchor = "end" if pi > n * 0.8 else "start"
        dx = -8 if anchor == "end" else 8
        body.append(f'<text x="{x(pi) + dx:.1f}" y="{y(points[pi][1]) - 6:.1f}" font-size="11" '
                    f'text-anchor="{anchor}" fill="{t["text"]}">máx. {points[pi][1]} en una semana</text>')
    return card(w, h, theme, "".join(body), "Contribuciones por semana en el último año")


def main():
    user = merge(fetch(USER), [fetch(u) for u in EXTRA_USERS])
    OUT.mkdir(exist_ok=True)
    for theme in THEMES:
        (OUT / f"stats-{theme}.svg").write_text(stats_svg(user, theme), encoding="utf-8")
        (OUT / f"languages-{theme}.svg").write_text(languages_svg(user, theme), encoding="utf-8")
        (OUT / f"activity-{theme}.svg").write_text(activity_svg(user, theme), encoding="utf-8")
    print(f"Tarjetas generadas en {OUT}")


if __name__ == "__main__":
    main()
