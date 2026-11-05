#!/usr/bin/env python3
"""Atualiza cartões SVG do perfil com dados da API oficial do GitHub.

Executado pelo GitHub Actions; não coleta dados de repositórios privados
nem usa serviços externos para renderizar as imagens. Python stdlib apenas.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from html import escape
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

LOGIN = "SrHenriqueBR"
BASE = "https://api.github.com"
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "assets"
LANG_COLORS = ("#7aa2f7", "#bb9af7", "#9ece6a", "#e0af68", "#7dcfff", "#f7768e")
GRAPHQL = """
query($user: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $user) {
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      contributionCalendar { totalContributions }
    }
  }
}
"""


def request_json(url: str, *, token: str, payload: dict | None = None) -> dict | list:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "SrHenriqueBR-profile-cards",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def public_repos(token: str) -> list[dict]:
    repos: list[dict] = []
    for page in range(1, 6):  # max. 500 public repos; fail rather than silently truncate
        url = f"{BASE}/users/{LOGIN}/repos?" + urllib.parse.urlencode({
            "type": "owner", "sort": "full_name", "per_page": 100, "page": page
        })
        data = request_json(url, token=token)
        if not isinstance(data, list):
            raise ValueError("Resposta inválida da API de repositórios")
        repos.extend(repo for repo in data if not repo.get("private", False))
        if len(data) < 100:
            return repos
    raise ValueError("Mais de 500 repositórios: adicione paginação antes de publicar métricas")


def language_totals(repos: list[dict], token: str) -> Counter:
    languages: Counter = Counter()
    for repo in repos:
        # Linguagens medem bytes de código GitHub Linguist, não proficiência.
        if repo.get("fork") or repo.get("name") == LOGIN or repo.get("archived"):
            continue
        url = repo.get("languages_url")
        if not isinstance(url, str) or not url.startswith(BASE + "/repos/"):
            continue
        data = request_json(url, token=token)
        if not isinstance(data, dict):
            continue
        for name, count in data.items():
            if isinstance(name, str) and isinstance(count, int) and count > 0:
                languages[name] += count
    return languages


def contributions(token: str, now: datetime) -> tuple[int | None, int | None]:
    end = now.astimezone(timezone.utc)
    begin = end - timedelta(days=365)
    fields = {
        "user": LOGIN,
        "from": begin.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "to": end.isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
    try:
        response = request_json(
            f"{BASE}/graphql", token=token,
            payload={"query": GRAPHQL, "variables": fields}
        )
        if response.get("errors"):
            raise ValueError("GraphQL indisponível")
        info = response["data"]["user"]["contributionsCollection"]
        commits = info["totalCommitContributions"]
        contributions_count = info["contributionCalendar"]["totalContributions"]
        if not isinstance(commits, int) or not isinstance(contributions_count, int):
            raise ValueError("Contagens inválidas")
        return commits, contributions_count
    except (KeyError, TypeError, ValueError, urllib.error.URLError):
        # Busca pública como alternativa, caso GraphQL não esteja acessível.
        # Não interprete falhas de rede ou permissão como 'zero commits'.
        start_date = begin.date().isoformat()
        query = f"author:{LOGIN} committer-date:>={start_date}"
        url = f"{BASE}/search/commits?" + urllib.parse.urlencode({
            "q": query, "per_page": 1
        })
        try:
            response = request_json(url, token=token)
            count = response.get("total_count")
            return (count if isinstance(count, int) else None), None
        except (TypeError, ValueError, urllib.error.URLError):
            return None, None


def svg_shell(width: int, height: int, title: str, updated: str, content: str) -> str:
    title = escape(title)
    updated = escape(updated)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"
 viewBox="0 0 {width} {height}" role="img" aria-label="{title}">
 <title>{title}</title>
 <rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="17"
       fill="#161a2a" stroke="#37415c" stroke-width="1.5"/>
 <path d="M22 54H{width - 22}" stroke="#333b56" stroke-width="1"/>
 <text x="22" y="34" font-family="Segoe UI,Arial,sans-serif" font-size="17"
       font-weight="700" fill="#c0caf5">{title}</text>
 <text x="{width - 22}" y="34" font-family="Segoe UI,Arial,sans-serif"
       font-size="10" text-anchor="end" fill="#8b96b8">{updated}</text>
 {content}
 </svg>
"""


def stats_svg(*, commit_count: int | None, total_contributions: int | None,
              repo_count: int, stars: int, updated: str) -> str:
    primary = str(commit_count) if commit_count is not None else "—"
    count_note = "Commits públicos · últimos 12 meses"
    secondary = str(total_contributions) if total_contributions is not None else "—"
    content = f"""
 <text x="22" y="116" fill="#7aa2f7" font-family="Segoe UI,Arial,sans-serif"
       font-size="52" font-weight="800">{escape(primary)}</text>
 <text x="22" y="141" fill="#a6accd" font-family="Segoe UI,Arial,sans-serif"
       font-size="11">{escape(count_note)}</text>
 <text x="270" y="94" fill="#bb9af7" font-family="Segoe UI,Arial,sans-serif"
       font-size="25" font-weight="700">{repo_count}</text>
 <text x="270" y="114" fill="#a6accd" font-family="Segoe UI,Arial,sans-serif"
       font-size="11">Repositórios públicos</text>
 <text x="400" y="94" fill="#9ece6a" font-family="Segoe UI,Arial,sans-serif"
       font-size="25" font-weight="700">{stars}</text>
 <text x="400" y="114" fill="#a6accd" font-family="Segoe UI,Arial,sans-serif"
       font-size="11">Stars recebidas</text>
 <path d="M22 159H488" stroke="#333b56" stroke-width="1"/>
 <text x="22" y="185" fill="#c0caf5" font-family="Segoe UI,Arial,sans-serif"
       font-size="12">Contribuições no período</text>
 <text x="210" y="185" fill="#bb9af7" font-family="Segoe UI,Arial,sans-serif"
       font-size="15" font-weight="700">{escape(secondary)}</text>
 <text x="22" y="203" fill="#7f8ba9" font-family="Segoe UI,Arial,sans-serif"
       font-size="10">Fonte: API oficial do GitHub · “—” significa dado indisponível</text>
"""
    return svg_shell(510, 218, "Atividade no GitHub", updated, content)


def languages_svg(languages: Counter, updated: str) -> str:
    lines = ['<text x="22" y="72" fill="#8b96b8" font-family="Segoe UI,Arial,sans-serif" '
             'font-size="10">Bytes de código em repositórios públicos próprios</text>']
    selected = languages.most_common(5)
    total = sum(languages.values())
    if total == 0:
        lines.append('<text x="22" y="136" fill="#c0caf5" font-family="Segoe UI,Arial,sans-serif"'
                     ' font-size="13">Linguagens ainda não disponíveis.</text>')
    else:
        for i, (name, size) in enumerate(selected):
            y = 99 + 24 * i
            ratio = size / total
            # Bar widths are normalized to the largest language for readability.
            width = max(2, round(236 * size / selected[0][1]))
            color = LANG_COLORS[i]
            lines.append(
                f'<text x="22" y="{y}" fill="#c0caf5" font-size="12" '
                f'font-family="Segoe UI,Arial,sans-serif">{escape(name)}</text>'
                f'<rect x="150" y="{y-11}" width="236" height="11" rx="5.5" fill="#303950"/>'
                f'<rect x="150" y="{y-11}" width="{width}" height="11" rx="5.5" fill="{color}"/>'
                f'<text x="477" y="{y}" text-anchor="end" fill="#a6accd" font-size="12" '
                f'font-family="Segoe UI,Arial,sans-serif">{ratio:.1%}</text>'
            )
    return svg_shell(510, 218, "Linguagens dos projetos", updated, "\n".join(lines))


def main() -> None:
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        raise SystemExit("GH_TOKEN ausente: execute no GitHub Actions com GITHUB_TOKEN")
    now = datetime.now(timezone.utc)
    repos = public_repos(token)
    languages = language_totals(repos, token)
    commit_count, contributions_count = contributions(token, now)
    # Não usar 0 como fallback quando a API não respondeu.
    stamp = now.strftime("%d/%m/%Y")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "github-stats.svg").write_text(
        stats_svg(commit_count=commit_count,
                  total_contributions=contributions_count,
                  repo_count=len(repos),
                  stars=sum(max(0, int(r.get("stargazers_count", 0))) for r in repos),
                  updated=stamp), encoding="utf-8"
    )
    (OUTPUT / "top-languages.svg").write_text(
        languages_svg(languages, stamp), encoding="utf-8"
    )
    print(f"Cartões atualizados: {len(repos)} repositórios públicos, "
          f"{len(languages)} linguagens detectadas.")


if __name__ == "__main__":
    main()
