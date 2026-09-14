#!/usr/bin/env python3
"""Inject all-time PyPI download counts into github-readme-stats pin SVGs."""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

USER_AGENT = "githubreadme-pypi-pins (https://github.com/alberto-rota)"
API_BASE = "https://pypistats.org/api/packages"
DOWNLOAD_PATH = (
    "M2.75 14A1.75 1.75 0 011 12.25v-2.5a.75.75 0 011.5 0v2.5c0 .138.112.25.25.25"
    "h10.5a.25.25 0 00.25-.25v-2.5a.75.75 0 011.5 0v2.5A1.75 1.75 0 0113.25 14H2.75z"
    "M7.25 7.689V2a.75.75 0 011.5 0v5.689l1.97-1.969a.75.75 0 111.06 1.06l-3.25 3.25"
    "a.75.75 0 01-1.06 0L4.22 6.78a.75.75 0 111.06-1.06l1.97 1.969z"
)

ROOT = Path(__file__).resolve().parents[1]
PINS = {
    ROOT / "profile/pin-ground-control.svg": "ground-control-tui",
    ROOT / "profile/pin-sekrt.svg": "sekrt",
    ROOT / "profile/pin-mlcp.svg": "mlcp",
    ROOT / "profile/pin-dasshboard-tui.svg": "dasshboard",
}

STAR_GROUP_RE = re.compile(
    r'(<g transform="translate\((?P<x>-?[0-9.]+),\s*0\)">'
    r'<g transform="translate\(0,\s*0\)">\s*'
    r"<svg\b[^>]*>\s*<path[^/]*/>\s*</svg>\s*"
    r"</g><g transform=\"translate\(20,\s*0\)\">"
    r'<text data-testid="stargazers" class="gray">(?P<label>[^<]+)</text>'
    r"</g></g>)",
    re.DOTALL,
)
PYPI_GROUP_RE = re.compile(
    r'<g transform="translate\([^)]+\)" data-testid="pypi-downloads">'
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


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode())


def fetch_downloads(package: str) -> int:
    encoded = urllib.parse.quote(package, safe="-_.")
    overall = fetch_json(f"{API_BASE}/{encoded}/overall")
    total = sum(
        int(row.get("downloads") or 0)
        for row in overall.get("data") or []
        if row.get("category") == "with_mirrors"
    )
    if total == 0:
        recent = fetch_json(f"{API_BASE}/{encoded}/recent")
        total = int((recent.get("data") or {}).get("last_month") or 0)
    return total


def downloads_markup(x: float, label: str) -> str:
    return (
        f'<g transform="translate({x}, 0)" data-testid="pypi-downloads">'
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
        f'<text data-testid="pypi-downloads" class="gray">{label}</text>'
        "</g></g>"
    )


def inject(svg: str, label: str) -> str:
    svg = PYPI_GROUP_RE.sub("", svg)
    match = STAR_GROUP_RE.search(svg)
    if not match:
        raise ValueError("stargazers group not found")
    stars_x = float(match.group("x"))
    stars_label = match.group("label")
    downloads_x = stars_x + 20 + 7.2 * len(stars_label) + 16
    inserted = match.group(1) + downloads_markup(downloads_x, label)
    return svg[: match.start()] + inserted + svg[match.end() :]


def process_pin(path: Path, package: str) -> tuple[str, int]:
    count = fetch_downloads(package)
    label = format_compact(count)
    original = path.read_text()
    path.write_text(inject(original, label))
    return label, count


def main() -> int:
    for path, package in PINS.items():
        name = path.name
        try:
            if not path.is_file():
                raise FileNotFoundError(path)
            label, count = process_pin(path, package)
            print(f"{name}: {package} -> {label} ({count})")
        except Exception as exc:  # noqa: BLE001 — keep CI commits moving
            print(f"{name}: {package} failed: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
