#!/usr/bin/env python3
"""Inject PyPI and VS Code Marketplace download counts into pin SVGs."""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

USER_AGENT = "githubreadme-pin-downloads (https://github.com/alberto-rota)"
PYPISTATS = "https://pypistats.org/api/packages"
MARKETPLACE_QUERY = (
    "https://marketplace.visualstudio.com/_apis/public/gallery/extensionquery"
    "?api-version=7.1-preview.1"
)
OPEN_VSX = "https://open-vsx.org/api/{publisher}/{name}"
DOWNLOAD_PATH = (
    "M2.75 14A1.75 1.75 0 011 12.25v-2.5a.75.75 0 011.5 0v2.5c0 .138.112.25.25.25"
    "h10.5a.25.25 0 00.25-.25v-2.5a.75.75 0 011.5 0v2.5A1.75 1.75 0 0113.25 14H2.75z"
    "M7.25 7.689V2a.75.75 0 011.5 0v5.689l1.97-1.969a.75.75 0 111.06 1.06l-3.25 3.25"
    "a.75.75 0 01-1.06 0L4.22 6.78a.75.75 0 111.06-1.06l1.97 1.969z"
)

ROOT = Path(__file__).resolve().parents[1]
# (svg path, source, package or publisher.extension id)
PINS = [
    (ROOT / "profile/pin-ground-control.svg", "pypi", "ground-control-tui"),
    (ROOT / "profile/pin-sekrt.svg", "pypi", "sekrt"),
    (ROOT / "profile/pin-mlcp.svg", "pypi", "mlcp"),
    (ROOT / "profile/pin-dasshboard-tui.svg", "pypi", "dasshboard"),
    (ROOT / "profile/pin-dasshboard.svg", "vscode", "AlbertoRota.dasshboard"),
]

STAR_GROUP_RE = re.compile(
    r'(<g transform="translate\((?P<x>-?[0-9.]+),\s*0\)">'
    r'<g transform="translate\(0,\s*0\)">\s*'
    r"<svg\b[^>]*>\s*<path[^/]*/>\s*</svg>\s*"
    r"</g><g transform=\"translate\(20,\s*0\)\">"
    r'<text data-testid="stargazers" class="gray">(?P<label>[^<]+)</text>'
    r"</g></g>)",
    re.DOTALL,
)
DOWNLOADS_GROUP_RE = re.compile(
    r'<g transform="translate\([^)]+\)" data-testid="(?:pypi-downloads|pin-downloads)">'
    r".*?</g></g>\s*",
    re.DOTALL,
)


def format_compact(count: int) -> str:
    """1540 -> 1.5k, 25000 -> 25k, 1000000 -> 1M."""
    n = int(count)
    if n < 1_000:
        return str(n)
    if n < 1_000_000:
        value, suffix = n / 1_000, "k"
    elif n < 1_000_000_000:
        value, suffix = n / 1_000_000, "M"
    else:
        value, suffix = n / 1_000_000_000, "B"
    rendered = f"{value:.1f}".rstrip("0").rstrip(".")
    return f"{rendered}{suffix}"


def fetch_json(
    url: str,
    data: bytes | None = None,
    extra_headers: dict[str, str] | None = None,
) -> dict:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    request = urllib.request.Request(
        url, data=data, headers=headers, method="POST" if data is not None else "GET"
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode())


def fetch_pypi_downloads(package: str) -> int:
    encoded = urllib.parse.quote(package, safe="-_.")
    overall = fetch_json(f"{PYPISTATS}/{encoded}/overall")
    total = sum(
        int(row.get("downloads") or 0)
        for row in overall.get("data") or []
        if row.get("category") == "with_mirrors"
    )
    if total == 0:
        recent = fetch_json(f"{PYPISTATS}/{encoded}/recent")
        total = int((recent.get("data") or {}).get("last_month") or 0)
    return total


def _marketplace_downloads(extension_id: str) -> int:
    body = json.dumps(
        {
            "filters": [
                {
                    "criteria": [{"filterType": 7, "value": extension_id}],
                    "pageNumber": 1,
                    "pageSize": 1,
                }
            ],
            "flags": 914,
        }
    ).encode()
    payload = fetch_json(
        MARKETPLACE_QUERY,
        data=body,
        extra_headers={
            "Content-Type": "application/json",
            "Accept": "application/json;api-version=7.1-preview.1",
        },
    )
    extensions = ((payload.get("results") or [{}])[0].get("extensions")) or []
    if not extensions:
        raise ValueError(f"marketplace: {extension_id} not found")
    stats = {
        row["statisticName"]: row.get("value") or 0
        for row in extensions[0].get("statistics") or []
    }
    if stats.get("downloadCount"):
        return int(stats["downloadCount"])
    return int(stats.get("install") or 0) + int(stats.get("updateCount") or 0)


def _open_vsx_downloads(extension_id: str) -> int:
    publisher, name = extension_id.split(".", 1)
    payload = fetch_json(OPEN_VSX.format(publisher=publisher, name=name))
    return int(payload.get("downloadCount") or 0)


def fetch_vscode_downloads(extension_id: str) -> int:
    """Marketplace + Open VSX download counts (Cursor/Windsurf use Open VSX)."""
    total = 0
    errors: list[str] = []
    for fetcher in (_marketplace_downloads, _open_vsx_downloads):
        try:
            total += fetcher(extension_id)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, KeyError) as exc:
            errors.append(f"{fetcher.__name__}: {exc}")
    if total == 0 and errors:
        raise ValueError("; ".join(errors))
    return total


def fetch_downloads(source: str, ident: str) -> int:
    if source == "pypi":
        return fetch_pypi_downloads(ident)
    if source == "vscode":
        return fetch_vscode_downloads(ident)
    raise ValueError(f"unknown source {source}")


def downloads_markup(x: float, label: str) -> str:
    return (
        f'<g transform="translate({x}, 0)" data-testid="pin-downloads">'
        '<g transform="translate(0, 0)">\n'
        "      <svg\n"
        '        class="icon"\n'
        '        y="-12"\n'
        '        viewBox="0 0 16 16"\n'
        '        version="1.1"\n'
        '        width="16"\n'
        '        height="16"\n'
        "      >\n"
        f'        <path fill-rule="evenodd" d="{DOWNLOAD_PATH}"/>\n'
        "      </svg>\n"
        '    </g><g transform="translate(20, 0)">'
        f'<text data-testid="pin-downloads" class="gray">{label}</text>'
        "</g></g>"
    )


def inject(svg: str, label: str) -> str:
    svg = DOWNLOADS_GROUP_RE.sub("", svg)
    match = STAR_GROUP_RE.search(svg)
    if not match:
        raise ValueError("stargazers group not found")
    stars_x = float(match.group("x"))
    stars_label = match.group("label")
    downloads_x = stars_x + 20 + 7.2 * len(stars_label) + 16
    inserted = match.group(1) + downloads_markup(downloads_x, label)
    return svg[: match.start()] + inserted + svg[match.end() :]


def process_pin(path: Path, source: str, ident: str) -> tuple[str, int]:
    count = fetch_downloads(source, ident)
    label = format_compact(count)
    path.write_text(inject(path.read_text(), label))
    return label, count


def main() -> int:
    for path, source, ident in PINS:
        name = path.name
        try:
            if not path.is_file():
                raise FileNotFoundError(path)
            label, count = process_pin(path, source, ident)
            print(f"{name}: {source}:{ident} -> {label} ({count})")
        except Exception as exc:  # noqa: BLE001 — keep CI commits moving
            print(f"{name}: {source}:{ident} failed: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
