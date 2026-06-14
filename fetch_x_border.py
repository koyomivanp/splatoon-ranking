"""sendou.ink から Xマッチ TOP500 ボーダー（最下位付近の X パワー）を取得する。"""

from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT_PATH = ROOT / "x_borders.json"

SENDOU_BASE = "https://sendou.ink/xsearch"
USER_AGENT = "splatoon-ranking-bot/1.0 (+https://splatoon-ranking.netlify.app/)"

# sendou.ink 内部コード → 表示名
MODES = {
    "SZ": "ガチエリア",
    "TC": "ガチヤグラ",
    "RM": "ガチホコ",
    "CB": "ガチアサリ",
}

ROW_RE = re.compile(
    r'data-testid="placement-row-(\d+)"[^>]*href="([^"]+)"[^>]*>.*?'
    r'<div>([0-9]+\.[0-9])</div></a>',
    re.S,
)


def jst_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=9)))


def fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=45) as resp:
        return resp.read().decode("utf-8", "replace")


def parse_placements(html: str) -> list[dict]:
    rows = []
    for rank, href, xp in ROW_RE.findall(html):
        r = int(rank)
        if r < 1:
            continue
        rows.append({"rank": r, "x_power": float(xp), "player_url": f"https://sendou.ink{href}"})
    rows.sort(key=lambda x: x["rank"])
    return rows


def border_from_rows(rows: list[dict]) -> dict | None:
    if not rows:
        return None
    top = rows[0]
    last = rows[-1]
    # 500位が無いシーズン初めは最下位ランクをボーダー目安に
    target_rank = 500 if any(r["rank"] == 500 for r in rows) else last["rank"]
    border_row = next((r for r in rows if r["rank"] == target_rank), last)
    return {
        "top1_x_power": top["x_power"],
        "top1_rank": top["rank"],
        "border_rank": border_row["rank"],
        "border_x_power": border_row["x_power"],
        "listed_count": len(rows),
    }


def fetch_mode(year: int, month: int, mode: str, region: str = "JP") -> dict:
    url = f"{SENDOU_BASE}?month={month}&year={year}&mode={mode}&region={region}"
    html = fetch_html(url)
    rows = parse_placements(html)
    stats = border_from_rows(rows)
    return {
        "mode": mode,
        "label": MODES[mode],
        "region": region,
        "source_url": url,
        "stats": stats,
    }


def load_ranking_season() -> tuple[int | None, int, int]:
    path = ROOT / "ranking.json"
    if not path.exists():
        now = jst_now()
        return None, now.year, now.month
    data = json.loads(path.read_text(encoding="utf-8"))
    season = data.get("season")
    updated = data.get("updated_at", "")
    try:
        dt = datetime.fromisoformat(updated.replace("Z", "+00:00")).astimezone(timezone(timedelta(hours=9)))
    except ValueError:
        dt = jst_now()
    return season, dt.year, dt.month


def main() -> None:
    season, year, month = load_ranking_season()
    rules = []
    for code in MODES:
        try:
            rules.append(fetch_mode(year, month, code))
            print(f"  {MODES[code]}: border {rules[-1]['stats']['border_x_power']} (rank {rules[-1]['stats']['border_rank']})")
        except Exception as e:
            print(f"  ! {MODES[code]}: {e}")
            rules.append({"mode": code, "label": MODES[code], "error": str(e)})

    payload = {
        "updated_at": jst_now().isoformat(),
        "season": season,
        "year": year,
        "month": month,
        "region": "JP",
        "source": "sendou.ink",
        "source_note": "Xマッチ TOP500 掲載データ。500位未満の場合は掲載最下位を目安ボーダーとして表示。",
        "rules": rules,
    }
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"→ {OUT_PATH}")


if __name__ == "__main__":
    main()
