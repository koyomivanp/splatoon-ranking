"""
スプラ最強武器ランキング - データ取得（スプラトゥーン3）

stat.ink の武器統計ページ (entire/weapons3) から、
モード別・ルール別の勝率/サンプル数/種別/サブ/スペシャルを取得し、
前シーズン比・種別傾向・サブ/スペ別勝率も計算して ranking.json を生成する。

データ出典: stat.ink (https://stat.ink/) CC-BY-4.0
標準ライブラリのみで動作。
"""

import json
import os
import re
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone

BASE = "https://stat.ink/entire/weapons3"

MODES = {
    "xmatch": "Xマッチ",
    "bankara_challenge": "バンカラ",
}
RULES = {
    "area": "ガチエリア",
    "yagura": "ガチヤグラ",
    "hoko": "ガチホコ",
    "asari": "ガチアサリ",
}

# 種別アイコンのフォルダ名 → 日本語
CATEGORY_JP = {
    "Shooters": "シューター",
    "Blasters": "ブラスター",
    "Rollers": "ローラー",
    "Brushes": "フデ",
    "Chargers": "チャージャー",
    "Sloshers": "スロッシャー",
    "Splatlings": "スピナー",
    "Dualies": "マニューバー",
    "Brellas": "シェルター",
    "Stringers": "ストリンガー",
    "Splatanas": "ワイパー",
}

MIN_SAMPLES_RULE = 100
MIN_SAMPLES_OVERALL = 300
MIN_SAMPLES_TREND = 200  # 傾向集計に使う最小サンプル

ROW_RE = re.compile(r'<tr data-key="\d+">(.*?)</tr>', re.S)
SORT_RE = re.compile(r'data-sort-value="([^"]*)"')
IMG_RE = re.compile(r'<img[^>]*src="([^"]+)"')
STAT_HOST = "https://stat.ink"
UA = {"User-Agent": "Mozilla/5.0 (splatoon-ranking-bot/1.0)"}


def abs_url(src: str) -> str:
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("/"):
        return STAT_HOST + src
    return src

_cache: "dict[str, str]" = {}


def fetch(url: str):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as res:
        return res.read().decode("utf-8"), res.geturl()


def detect_season() -> int:
    _, final = fetch(f"{BASE}/xmatch/area")
    m = re.search(r"season=(\d+)", final)
    if not m:
        raise RuntimeError("シーズン番号を検出できませんでした")
    return int(m.group(1))


def parse_page(mode: str, rule: str, season: int) -> "dict[str, dict]":
    url = f"{BASE}/{mode}/{rule}?season={season}&_lang_=ja-JP"
    if url not in _cache:
        try:
            _cache[url], _ = fetch(url)
        except Exception as e:
            print(f"  ! 取得失敗 {mode}/{rule} S{season}: {e}")
            _cache[url] = ""
    out = {}
    for row in ROW_RE.findall(_cache[url]):
        vals = SORT_RE.findall(row)
        if len(vals) < 6:
            continue
        name = vals[0]
        try:
            samples = int(vals[3])
            win_rate = float(vals[5])
        except ValueError:
            continue
        imgs = IMG_RE.findall(row)
        category = "その他"
        image = sub_img = special_img = ""
        if imgs:
            parts = imgs[0].rstrip("/").split("/")
            if len(parts) >= 2:
                category = CATEGORY_JP.get(parts[-2], parts[-2])
            image = abs_url(imgs[0])
            if len(imgs) > 1:
                sub_img = abs_url(imgs[1])
            if len(imgs) > 2:
                special_img = abs_url(imgs[2])
        out[name] = {
            "samples": samples,
            "win_rate": win_rate,
            "category": category,
            "sub": vals[1] if len(vals) > 1 else "",
            "special": vals[2] if len(vals) > 2 else "",
            "image": image,
            "sub_img": sub_img,
            "special_img": special_img,
        }
    return out


def build_mode(mode: str, season: int):
    per_rule = {rule: parse_page(mode, rule, season) for rule in RULES}

    agg = defaultdict(lambda: {"w": 0.0, "n": 0, "meta": None, "best": (None, -1)})
    for rule, data in per_rule.items():
        for name, v in data.items():
            a = agg[name]
            a["w"] += v["win_rate"] * v["samples"]
            a["n"] += v["samples"]
            a["meta"] = v
            if v["samples"] >= MIN_SAMPLES_RULE and v["win_rate"] > a["best"][1]:
                a["best"] = (RULES[rule], v["win_rate"])

    overall = {}
    for name, a in agg.items():
        if a["n"] <= 0:
            continue
        overall[name] = {
            "samples": a["n"],
            "win_rate": a["w"] / a["n"],
            "category": a["meta"]["category"],
            "sub": a["meta"]["sub"],
            "special": a["meta"]["special"],
            "image": a["meta"].get("image", ""),
            "sub_img": a["meta"].get("sub_img", ""),
            "special_img": a["meta"].get("special_img", ""),
            "best_rule": a["best"][0],
        }
    return per_rule, overall


def make_ranking(cur: dict, prev: dict, min_samples: int):
    ranking = []
    for name, v in cur.items():
        if v["samples"] < min_samples:
            continue
        delta = None
        if name in prev:
            delta = round(v["win_rate"] - prev[name]["win_rate"], 2)
        item = {
            "weapon": name,
            "win_rate": round(v["win_rate"], 2),
            "samples": v["samples"],
            "delta": delta,
        }
        for k in ("category", "sub", "special", "best_rule", "image", "sub_img", "special_img"):
            if k in v:
                item[k] = v[k]
        ranking.append(item)
    ranking.sort(key=lambda x: x["win_rate"], reverse=True)
    return ranking


def make_highlights(overall_ranking):
    wd = [r for r in overall_ranking if r["delta"] is not None]
    return {
        "risers": sorted(wd, key=lambda x: x["delta"], reverse=True)[:3],
        "fallers": sorted(wd, key=lambda x: x["delta"])[:3],
        "most_used": sorted(overall_ranking, key=lambda x: x["samples"], reverse=True)[:3],
    }


def make_trends(overall: dict, key: str):
    """overall（name->meta）を key（category/sub/special）で集計し加重平均勝率を返す。"""
    agg = defaultdict(lambda: {"w": 0.0, "n": 0, "count": 0, "top": (None, -1)})
    for name, v in overall.items():
        if v["samples"] < MIN_SAMPLES_TREND:
            continue
        g = v.get(key) or "その他"
        a = agg[g]
        a["w"] += v["win_rate"] * v["samples"]
        a["n"] += v["samples"]
        a["count"] += 1
        if v["win_rate"] > a["top"][1]:
            a["top"] = (name, v["win_rate"])
    out = []
    for g, a in agg.items():
        if a["n"] <= 0:
            continue
        out.append({
            "name": g,
            "avg_win": round(a["w"] / a["n"], 2),
            "count": a["count"],
            "top_weapon": a["top"][0],
            "top_win": round(a["top"][1], 2),
        })
    out.sort(key=lambda x: x["avg_win"], reverse=True)
    return out


def main():
    print("シーズン検出中...")
    season = detect_season()
    prev_season = season - 1
    print(f"最新: S{season} / 前: S{prev_season}")

    modes_out = {}
    highlights = None
    trends = None
    for mode, label in MODES.items():
        print(f"取得中: {label} ...")
        cur_per_rule, cur_overall = build_mode(mode, season)
        _, prev_overall = build_mode(mode, prev_season)
        prev_per_rule = {rule: parse_page(mode, rule, prev_season) for rule in RULES}

        rules_out = {"overall": make_ranking(cur_overall, prev_overall, MIN_SAMPLES_OVERALL)}
        for rule in RULES:
            rules_out[rule] = make_ranking(cur_per_rule[rule], prev_per_rule[rule], MIN_SAMPLES_RULE)
        modes_out[mode] = {"label": label, "rules": rules_out}

        if mode == "xmatch":
            highlights = make_highlights(rules_out["overall"])
            trends = {
                "category": make_trends(cur_overall, "category"),
                "sub": make_trends(cur_overall, "sub"),
                "special": make_trends(cur_overall, "special"),
            }

    out = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "stat.ink",
        "game": "Splatoon 3",
        "season": season,
        "prev_season": prev_season,
        "rule_labels": {"overall": "総合", **RULES},
        "modes": modes_out,
        "highlights": highlights,
        "trends": trends,
        "patch": {},
    }
    with open("ranking.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"\n=== Xマッチ 種別傾向 (S{season}) ===")
    for t in (trends or {}).get("category", []):
        print(f"{t['name']:<8} 平均{t['avg_win']:.2f}%  ({t['count']}種, top:{t['top_weapon']})")
    print("\nranking.json を書き出しました。")


if __name__ == "__main__":
    main()
