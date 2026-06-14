"""
スプラログ (spla3sokuhou.games) から武器名を含む記事を収集し、
Gemini で playstyle.json 用の独自解説を生成する。

※ 記事本文の丸写しはせず、タイトル＋抜粋を材料に再構成する。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RANKING_PATH = ROOT / "ranking.json"
PLAYSTYLE_PATH = ROOT / "playstyle.json"
CACHE_PATH = ROOT / "spla_log_cache.json"
ENV_PATH = ROOT / ".env"

SITE = "https://spla3sokuhou.games"
USER_AGENT = "splatoon-ranking-bot/1.0"

# まとめサイト上の略称 → stat.ink 表記
ALIASES = {
    "52ガロン": ".52ガロン",
    "52": ".52ガロン",
    "ホッブラ": "ホットブラスター",
    "クラブラ": "クラッシュブラスター",
    "リールD": "L3リールガンD",
    "L3D": "L3リールガンD",
    "N-ZAP": "N-ZAP85",
    "バレル": "バレルスピナー",
    "クアッド": "クアッドホッパーブラック",
    "ダイナモ": "ダイナモローラー",
    "スプラローラ": "スプラローラー",
    "モップリン": "モップリン",
    "ジム": "ジムワイパー",
    "リッター": "リッター4K",
    "ボトル": "ボトルガイザー",
    "プライム": "プライムシューター",
    "スパッタリー": "スパッタリー・ヒュー",
    "ロングブラ": "ロングブラスター",
    "トライ": "トライストリンガー",
    "燈": "トライストリンガー燈",
    "L3": "L3リールガンD",
    "箔": "L3リールガン箔",
}

PROMPT = """あなたはスプラトゥーン3の武器解説ライターです。
以下は掲示板まとめ記事の「タイトルと抜粋」です。本文をそのまま写さず、
勝率データと合わせて武器ページ用の独自解説を書いてください。

【武器】{weapon}
【勝率データ】{stat_line}
【サブウェポン（これだけ書く）】{sub}
【スペシャル（これだけ書く）】{special}

【参考になった世間の声（要約材料・丸写し禁止）】
{snippets}

【文体】
- 口語でウィット少々OK。まとめサイト口調（「悲報」「〇〇さん」）は使わない
- pros/cons 各2〜4個、playstyle 2〜4文
- サブ/スペは上記の2つだけ言及すること（他武器のギア名は禁止）
- 出典・URL・掲示板レス番号は書かない

JSONのみ出力:
{{"weapon":"{weapon}","pros":["..."],"cons":["..."],"playstyle":"...","reputation_note":"コミュニティでの評判を1文で（任意）"}}
"""


def load_env() -> None:
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_top_weapons(n: int = 20) -> list[dict]:
    data = json.loads(RANKING_PATH.read_text(encoding="utf-8"))
    mode = next(iter(data["modes"].values()))
    return mode["rules"]["overall"][:n]


def load_ranked_weapons(min_rank: int = 1) -> list[dict]:
    """Xマッチ総合ランキング順。min_rank=21 なら21位以降。"""
    data = json.loads(RANKING_PATH.read_text(encoding="utf-8"))
    mode = next(iter(data["modes"].values()))
    overall = mode["rules"]["overall"]
    if min_rank > 1:
        overall = overall[min_rank - 1:]
    return overall


def pending_weapons(min_rank: int, existing: dict, force: bool) -> list[dict]:
    ranked = load_ranked_weapons(min_rank)
    if force:
        return ranked
    have = existing.get("weapons", {})
    return [w for w in ranked if w["weapon"] not in have]


def lookup_weapon_meta(name: str) -> dict | None:
    data = json.loads(RANKING_PATH.read_text(encoding="utf-8"))
    mode = next(iter(data["modes"].values()))
    for lst in mode["rules"].values():
        for row in lst:
            if row["weapon"] == name:
                return row
    return None


# 他武器のサブ/スペが紛れ込むのを検出（Gemini 生成後チェック用）
_KIT_WORDS = [
    "アメフラシ", "エナジースタンド", "ジェットパック", "カニタンク", "ナイスダマ",
    "ウルトラショット", "メガホンレーザー5.1ch", "グレートバリア", "サメライド",
    "デコイチラシ", "ウルトラハンコ", "ウルトラチャクチ", "トリプルトルネード",
    "ホップソナー", "スミナガシ", "テイサツエイム", "マルチミサイル",
    "トーピード", "ポイズンミスト", "カーリングボム", "スプラッシュボム",
    "キューバンボム", "ロボットボム", "スプリンクラー", "ラインマーカー",
    "ジャンプビーコン", "タンサンボム", "クイックボム", "ポイントセンサー",
]


def validate_kit_text(weapon: str, meta: dict, entry: dict) -> list[str]:
    sub, sp = meta.get("sub") or "", meta.get("special") or ""
    if not sub and not sp:
        return []
    text = " ".join(entry.get("pros", []) + entry.get("cons", []) + [entry.get("playstyle", "")])
    warnings = []
    for word in _KIT_WORDS:
        if word in text and word not in (sub, sp):
            warnings.append(f"「{word}」は {weapon} のキットにない（正: {sub} / {sp}）")
    return warnings


def weapons_by_names(names: list[str]) -> list[dict]:
    out: list[dict] = []
    for name in names:
        meta = lookup_weapon_meta(name)
        if meta:
            out.append(meta)
        else:
            out.append({
                "weapon": name,
                "win_rate": None,
                "samples": None,
                "category": "シューター" if "リール" in name else "ストリンガー",
            })
    return out


def search_articles(query: str, max_pages: int = 2) -> list[dict]:
    """WordPress 検索結果から記事リンクとタイトルを拾う。"""
    found: list[dict] = []
    seen: set[str] = set()
    bookmark_re = re.compile(r'rel="bookmark" href="(https://spla3sokuhou\.games/[^"]+)"', re.I)
    headline_re = re.compile(r'itemprop="headline"[^>]*>([^<]+)', re.I)
    for page in range(1, max_pages + 1):
        q = urllib.parse.urlencode({"s": query, "paged": page})
        url = f"{SITE}/?{q}"
        html = fetch(url)
        for m in bookmark_re.finditer(html):
            link = m.group(1)
            if link in seen or "/page/" in link or "/category/" in link:
                continue
            chunk = html[m.start():m.start() + 1500]
            hm = headline_re.search(chunk)
            title = re.sub(r"\s+", " ", hm.group(1)).strip() if hm else link
            seen.add(link)
            found.append({"url": link, "title": title, "query": query})
        if "次のページ" not in html and "next" not in html.lower():
            break
        time.sleep(0.8)
    return found


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace")


def article_snippet(url: str) -> str:
    html = fetch(url)
    title_m = re.search(r"<title>([^<]+)</title>", html, re.I)
    title = title_m.group(1).split("|")[0].strip() if title_m else url
    # 本文冒頭（まとめサイトは entry-content）
    body_m = re.search(r'class="entry-content[^"]*"[^>]*>(.*?)</div>', html, re.S | re.I)
    body = re.sub(r"<[^>]+>", " ", body_m.group(1)) if body_m else ""
    body = re.sub(r"\s+", " ", body).strip()[:600]
    return f"・{title}\n  {body}"


def collect_for_weapon(weapon: str) -> list[dict]:
    queries = {weapon}
    for nick, full in ALIASES.items():
        if full == weapon:
            queries.add(nick)
    articles: list[dict] = []
    seen: set[str] = set()
    for q in queries:
        for art in search_articles(q, max_pages=1):
            if art["url"] in seen:
                continue
            seen.add(art["url"])
            articles.append(art)
        time.sleep(0.6)
    return articles[:8]


def gemini_summarize(weapon: str, meta: dict, snippets: str, model: str, max_retries: int = 4) -> dict:
    import google.generativeai as genai

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY が .env にありません")
    genai.configure(api_key=api_key)
    model_obj = genai.GenerativeModel(model)
    stat = (
        f"シーズン勝率 {meta.get('win_rate')}% / {meta.get('category')} / "
        f"サブ={meta.get('sub')} / スペ={meta.get('special')}"
    )
    prompt = PROMPT.format(
        weapon=weapon,
        stat_line=stat,
        sub=meta.get("sub") or "不明",
        special=meta.get("special") or "不明",
        snippets=snippets or "（関連記事なし）",
    )

    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = model_obj.generate_content(prompt)
            text = resp.text.strip()
            m = re.search(r"\{[\s\S]*\}", text)
            return json.loads(m.group(0) if m else text)
        except Exception as e:
            last_err = e
            msg = str(e)
            if ("429" in msg or "quota" in msg.lower()) and attempt < max_retries - 1:
                wait = 13.0
                rm = re.search(r"retry in ([0-9.]+)s", msg, re.I)
                if rm:
                    wait = float(rm.group(1)) + 1.0
                print(f"  quota - {wait:.0f}秒待って再試行 ({attempt + 1}/{max_retries})")
                time.sleep(wait)
                continue
            raise
    raise last_err  # type: ignore[misc]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=20, help="TOP N 武器（--auto 未使用時）")
    parser.add_argument("--names", nargs="*", help="指定武器名のみ処理（stat.ink表記）")
    parser.add_argument(
        "--auto",
        action="store_true",
        help="ランキング順に playstyle 未登録の武器だけ処理（CI向け）",
    )
    parser.add_argument(
        "--min-rank",
        type=int,
        default=1,
        help="--auto 時: この順位以降だけ対象（21 なら TOP21 以降）",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="既存も上書き")
    parser.add_argument("--model", default=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"))
    parser.add_argument(
        "--max-api", type=int, default=4,
        help="1回の実行で Gemini を叩く最大件数（無料枠は約5回/分）",
    )
    parser.add_argument(
        "--sleep", type=float, default=13.0,
        help="Gemini 呼び出し間隔（秒）。無料枠なら 13 以上推奨",
    )
    args = parser.parse_args()
    load_env()

    playstyle = json.loads(PLAYSTYLE_PATH.read_text(encoding="utf-8")) if PLAYSTYLE_PATH.exists() else {"weapons": {}}
    playstyle.setdefault("weapons", {})

    if args.names:
        weapons = weapons_by_names(args.names)
    elif args.auto:
        weapons = pending_weapons(args.min_rank, playstyle, args.force)
        if not weapons:
            print("auto: 未登録の武器はありません（完了）")
            return
        print(f"auto: 未登録 {len(weapons)} 件（次: {weapons[0]['weapon']}）")
    else:
        weapons = load_top_weapons(args.limit)

    cache = json.loads(CACHE_PATH.read_text(encoding="utf-8")) if CACHE_PATH.exists() else {"articles": {}}
    api_used = 0

    for i, meta in enumerate(weapons, 1):
        name = meta["weapon"]
        if name in playstyle["weapons"] and not args.force:
            print(f"[{i}/{len(weapons)}] skip (exists): {name}")
            continue
        if not args.dry_run and api_used >= args.max_api:
            print(f"[{i}/{len(weapons)}] stop: --max-api {args.max_api} に達したので終了（続きはあとで）")
            break
        print(f"[{i}/{len(weapons)}] collect: {name}")
        arts = collect_for_weapon(name)
        cache.setdefault("articles", {})[name] = arts
        CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        snippet_lines = []
        for art in arts[:5]:
            try:
                snippet_lines.append(article_snippet(art["url"]))
                time.sleep(0.7)
            except Exception as e:
                snippet_lines.append(f"・{art['title']} （取得失敗: {e}）")
        snippets = "\n".join(snippet_lines)
        if args.dry_run:
            print(f"  articles={len(arts)} snippets_len={len(snippets)}")
            continue

        try:
            result = gemini_summarize(name, meta, snippets, args.model)
            entry = {
                "pros": result.get("pros", []),
                "cons": result.get("cons", []),
                "playstyle": result.get("playstyle", ""),
            }
            if result.get("reputation_note"):
                entry["reputation"] = result["reputation_note"]
            warns = validate_kit_text(name, meta, entry)
            for w in warns:
                print(f"  ! kit warning: {w}")
            playstyle["weapons"][name] = entry
            PLAYSTYLE_PATH.write_text(json.dumps(playstyle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"  -> saved {name}")
            api_used += 1
            if api_used < args.max_api:
                time.sleep(args.sleep)
        except Exception as e:
            print(f"  ! Gemini error: {e}")

    if api_used:
        print(f"Gemini API 使用: {api_used} 回")
    if args.auto and not args.dry_run:
        left = len(pending_weapons(args.min_rank, playstyle, args.force))
        print(f"auto: 残り {left} 件")
    print("done")


if __name__ == "__main__":
    main()
