"""
YouTube 動画を Gemini API で要約し、playstyle.json を更新する。

使い方:
  1. pip install -r requirements-gemini.txt
  2. .env.example を .env にコピーし GEMINI_API_KEY を設定
     https://aistudio.google.com/apikey
  3. video_queue.json に URL を並べる（weapon_hint は任意）
  4. python summarize_videos.py
  5. python build_site.py

※ 要約結果は playstyle.json のみ更新。動画埋め込みはサイトに出しません。

オプション:
  --dry-run     APIを叩かず確認のみ
  --force       既存エントリも上書き
  --url URL     1本だけ処理
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
QUEUE_PATH = ROOT / "video_queue.json"
PLAYSTYLE_PATH = ROOT / "playstyle.json"
RANKING_PATH = ROOT / "ranking.json"
ENV_PATH = ROOT / ".env"

PROMPT = """あなたはスプラトゥーン3の武器解説ライターです。
添付のYouTube動画を視聴・理解し、メインで解説されているブキについて以下を日本語でまとめてください。

【武器名のルール】
- 下記「登録済み武器名リスト」から最も一致する1つを weapon に選ぶ（表記を完全一致させる）
- リストに無い場合は weapon を null にする
- weapon_hint が与えられていれば優先して検討する

【文体】
- ウィットは少し効かせてよいが、事実と推測を混ぜない
- pros/cons は各2〜4個、短い箇条書き
- playstyle は2〜4文
- 動画の出典・チャンネル名・URL は出力に含めない（サイト側で独自解説として載せる）

【出力形式】JSONのみ（```不要）。キー:
{{
  "weapon": "リスト内の武器名 or null",
  "pros": ["..."],
  "cons": ["..."],
  "playstyle": "...",
  "confidence": "high" | "medium" | "low"
}}

登録済み武器名リスト:
{weapon_list}

weapon_hint: {weapon_hint}
"""


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def youtube_watch_url(url: str) -> str:
    url = url.strip()
    if "youtu.be/" in url:
        vid = url.split("youtu.be/", 1)[1].split("?")[0].split("&")[0]
        return f"https://www.youtube.com/watch?v={vid}"
    if "watch?v=" in url:
        parsed = urlparse(url)
        vid = parse_qs(parsed.query).get("v", [""])[0]
        if vid:
            return f"https://www.youtube.com/watch?v={vid}"
    return url


def load_weapon_names() -> list[str]:
    if not RANKING_PATH.exists():
        print("! ranking.json が見つかりません。先に fetch_ranking.py を実行してください。")
        return []
    data = json.loads(RANKING_PATH.read_text(encoding="utf-8"))
    names: set[str] = set()
    for mode in data.get("modes", {}).values():
        for lst in mode.get("rules", {}).values():
            for r in lst:
                w = r.get("weapon")
                if w:
                    names.add(w)
    return sorted(names)


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def extract_json(text: str) -> dict:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        text = m.group(1).strip()
    return json.loads(text)


def summarize(url: str, weapon_hint: str, weapon_names: list[str], model_name: str, api_key: str) -> dict:
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)
    watch = youtube_watch_url(url)
    hint = weapon_hint or "（なし）"
    sample = weapon_names[:200]
    if len(weapon_names) > 200:
        sample.append(f"...他{len(weapon_names)-200}件")
    prompt = PROMPT.format(weapon_list="\n".join(sample), weapon_hint=hint)

    response = model.generate_content(
        [
            {"file_data": {"mime_type": "video/*", "file_uri": watch}},
            prompt,
        ],
        request_options={"timeout": 300},
    )
    return extract_json(response.text)


def merge_playstyle(result: dict, playstyle: dict, force: bool) -> str | None:
    weapon = result.get("weapon")
    if not weapon or weapon == "null":
        return None
    weapons_ps = playstyle.setdefault("weapons", {})
    if weapon in weapons_ps and not force:
        print(f"  skip (既存): {weapon}")
        return weapon
    weapons_ps[weapon] = {
        "pros": result.get("pros") or [],
        "cons": result.get("cons") or [],
        "playstyle": result.get("playstyle") or "",
    }
    print(f"  + playstyle: {weapon}")
    return weapon


def main() -> int:
    parser = argparse.ArgumentParser(description="GeminiでYouTube動画を要約して playstyle.json を更新")
    parser.add_argument("--dry-run", action="store_true", help="APIを叩かない")
    parser.add_argument("--force", action="store_true", help="既存を上書き")
    parser.add_argument("--url", help="1本だけ処理")
    parser.add_argument("--delay", type=float, default=3.0, help="リクエスト間隔(秒)")
    args = parser.parse_args()

    load_env(ENV_PATH)
    api_key = os.environ.get("GEMINI_API_KEY", "")
    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    if not api_key and not args.dry_run:
        print("GEMINI_API_KEY が未設定です。")
        print(f"  1) {ENV_PATH} を作成（.env.example を参考）")
        print("  2) https://aistudio.google.com/apikey でキーを取得")
        return 1

    weapon_names = load_weapon_names()
    if not weapon_names:
        return 1

    queue = load_json(QUEUE_PATH)
    items = queue.get("videos") or []
    if args.url:
        items = [{"url": args.url, "weapon_hint": ""}]

    if not items:
        print("video_queue.json に URL がありません。")
        return 1

    playstyle = load_json(PLAYSTYLE_PATH)
    if "_note" not in playstyle:
        playstyle["_note"] = "Gemini summarize_videos.py で更新（サイトには独自解説として表示）"

    ok = 0
    for i, item in enumerate(items, 1):
        url = item.get("url", "")
        if not url:
            continue
        if item.get("done") and not args.force and not args.url:
            print(f"[{i}] skip (done): {url}")
            continue

        hint = item.get("weapon_hint", "")
        print(f"[{i}/{len(items)}] {youtube_watch_url(url)}")
        if args.dry_run:
            print("  dry-run: APIスキップ")
            continue

        try:
            result = summarize(url, hint, weapon_names, model_name, api_key)
            weapon = merge_playstyle(result, playstyle, args.force)
            if weapon:
                item["done"] = True
                item["weapon"] = weapon
                item["confidence"] = result.get("confidence")
                ok += 1
            else:
                print(f"  ! 武器を特定できませんでした: {result}")
        except Exception as e:
            print(f"  ! エラー: {e}")
            print("    ※ APIキー・モデル名・YouTube URL を確認してください")

        if i < len(items):
            time.sleep(args.delay)

    if not args.dry_run:
        save_json(PLAYSTYLE_PATH, playstyle)
        save_json(QUEUE_PATH, queue)
        print(f"\n完了: {ok} 件を playstyle.json に反映")
        print("次: python build_site.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())
