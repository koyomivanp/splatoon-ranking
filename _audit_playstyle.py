"""playstyle.json のサブ/スペ記述が ranking.json と合うか簡易監査"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ranking = json.loads((ROOT / "ranking.json").read_text(encoding="utf-8"))
playstyle = json.loads((ROOT / "playstyle.json").read_text(encoding="utf-8"))

mode = next(iter(ranking["modes"].values()))
overall = {r["weapon"]: r for r in mode["rules"]["overall"]}

SPECIALS = [
    "アメフラシ", "エナジースタンド", "ジェットパック", "カニタンク", "ナイスダマ",
    "ウルトラショット", "メガホンレーザー5.1ch", "グレートバリア", "サメライド",
    "デコイチラシ", "ウルトラハンコ", "ウルトラチャクチ", "トリプルトルネード",
    "スミナガシ", "テイサツエイム", "マルチミサイル",
]
SUBS = [
    "トーピード", "ポイズンミスト", "カーリングボム", "スプラッシュボム",
    "キューバンボム", "ロボットボム", "スプリンクラー", "ラインマーカー",
    "ジャンプビーコン", "タンサンボム", "クイックボム", "ポイントセンサー",
]

print("weapon|sub|special")
for name in playstyle.get("weapons", {}):
    meta = overall.get(name)
    if meta:
        print(f"{name}|{meta.get('sub')}|{meta.get('special')}")
    else:
        print(f"{name}|?|?")

print("\n--- ISSUES ---\n")
issues = []
for name, entry in playstyle.get("weapons", {}).items():
    meta = overall.get(name)
    if not meta:
        issues.append((name, "ranking.json に未登録", [], []))
        continue
    sub, sp = meta.get("sub", ""), meta.get("special", "")
    text = " ".join(entry.get("pros", []) + entry.get("cons", []) + [entry.get("playstyle", "")])
    wrong_sp = [s for s in SPECIALS if s in text and s != sp]
    wrong_sub = [s for s in SUBS if s in text and s != sub]
    if wrong_sp or wrong_sub:
        issues.append((name, f"実: サブ={sub} / スペ={sp}", wrong_sub, wrong_sp))

for row in issues:
    print(f"【{row[0]}】 {row[1]}")
    if row[2]:
        print(f"  誤サブ: {', '.join(row[2])}")
    if row[3]:
        print(f"  誤スペ: {', '.join(row[3])}")
    print()
