"""
スプラ最強武器ランキング - サイト生成

ranking.json を読み込み、静的サイト (dist/index.html) を生成する。
モード切替（Xマッチ/バンカラ）、ルール別タブ、勝率からの自動tier、
前シーズン比（↑↓）、アプデ強化/弱体の強調、注目ハイライトを含む。
標準ライブラリのみで動作。
"""

import html
import json
import os
from datetime import datetime, timezone, timedelta

SITE_URL = "https://splatoon-ranking.netlify.app/"
SITE_NAME = "スプラ最強武器ランキング"
OUT_DIR = "dist"
GOOGLE_SITE_VERIFICATION = "FJrCl2mYIdZN3QdLWKjJ1UNoF-k0AtZzDougkqPzowU"

RULE_ORDER = ["overall", "area", "yagura", "hoko", "asari"]

TIERS = [
    (52.0, "S", "#ff3b6b"),
    (50.5, "A", "#ff8a3d"),
    (49.5, "B", "#ffd23d"),
    (48.0, "C", "#52d273"),
    (0.0, "D", "#5b9cff"),
]


def tier_of(win_rate: float):
    for thr, label, color in TIERS:
        if win_rate >= thr:
            return label, color
    return "D", "#5b9cff"


def jst(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso).astimezone(timezone(timedelta(hours=9)))
    except Exception:
        dt = datetime.now(timezone(timedelta(hours=9)))
    return dt.strftime("%Y年%m月%d日 %H:%M")


def esc(s) -> str:
    return html.escape(str(s))


def google_verify_meta() -> str:
    if not GOOGLE_SITE_VERIFICATION:
        return ""
    return f'<meta name="google-site-verification" content="{esc(GOOGLE_SITE_VERIFICATION)}">\n'


def delta_html(delta):
    if delta is None:
        return '<span class="delta zero">—</span>'
    if delta > 0:
        return f'<span class="delta up">▲ +{delta:.2f}</span>'
    if delta < 0:
        return f'<span class="delta down">▼ {delta:.2f}</span>'
    return '<span class="delta zero">±0</span>'


def weapon_slug(r):
    img = r.get("image") or ""
    base = img.split("/")[-1].split("?")[0]
    if base.endswith(".png"):
        base = base[:-4]
    return base or "weapon"


def weapon_img(r, cls="wimg"):
    src = r.get("image")
    if not src:
        return ""
    return (f'<span class="iplate {cls}">'
            f'<img src="{esc(src)}" alt="{esc(r["weapon"])}" loading="lazy"></span>')


def patch_badge(weapon, patch_weapons):
    t = patch_weapons.get(weapon)
    if t == "buff":
        return '<span class="patch-badge buff">🔼強化</span>'
    if t == "nerf":
        return '<span class="patch-badge nerf">🔽弱体</span>'
    return ""


NOTE_POOLS = {
    "buff": [
        "アプデで強化され、今が乗りどき。",
        "調整で地力アップ。握るなら今かも。",
        "強化パッチで息を吹き返した一本。",
    ],
    "nerf": [
        "ナーフを食らって向かい風…それでも現役。",
        "アプデで火力ダウン、受難のシーズン。",
        "弱体されたが、愛用者は手放さない。",
    ],
    "riser_big": [
        "勝率うなぎ登り、環境を駆け上がる注目株。",
        "急上昇中。今シーズンの台風の目。",
        "数字が物語る大躍進。波に乗っている。",
    ],
    "riser": [
        "じわじわ評価を上げる伸び盛り。",
        "静かに勝率を積み上げる好調キープ。",
        "右肩上がり、これからに期待。",
    ],
    "faller_big": [
        "勝率は急降下、苦しいシーズン。",
        "かつての勢いはどこへやら…。",
        "数字は下降線、立て直しに期待。",
    ],
    "faller": [
        "やや失速気味、ここが踏ん張りどころ。",
        "少し陰りが見える今日この頃。",
    ],
    "S": [
        "言わずと知れた環境トップの暴れん坊。",
        "勝率は折り紙つき、迷ったらコレ。",
        "現環境の主役級、強さは本物。",
    ],
    "A": [
        "クセが少なく安定して勝てる優等生。",
        "堅実に仕事をする頼れる相棒。",
        "派手さはないが勝たせてくれる実力派。",
    ],
    "D": [
        "今は逆風だが、ハマれば一発のロマン砲。",
        "数字は地味でも使い手次第で化ける。",
        "愛がないと握れない玄人向けの一本。",
    ],
    "neutral": [
        "良くも悪くも平均点、腕の見せどころ。",
        "尖りはないが器用にこなす中堅。",
        "数字は普通、あとは愛と練度で。",
    ],
    "popular": [
        "ガチ部屋で見ない日はない人気者。",
        "遭遇率は随一、みんな大好きな定番。",
        "使用者の多さは折り紙つきの流行ブキ。",
    ],
}


def _pick(pool_key, seed):
    pool = NOTE_POOLS[pool_key]
    return pool[seed % len(pool)]


def auto_note(r, tier, patch_weapons, popular=False):
    """事実データからウィットの効いたひとことTIPSを生成する。"""
    seed = sum(ord(c) for c in r["weapon"])
    parts = []

    pt = patch_weapons.get(r["weapon"])
    if pt in ("buff", "nerf"):
        parts.append(_pick(pt, seed))

    d = r.get("delta")
    if d is not None and len(parts) < 2:
        if d >= 1.0:
            parts.append(_pick("riser_big", seed))
        elif d >= 0.3:
            parts.append(_pick("riser", seed))
        elif d <= -1.0:
            parts.append(_pick("faller_big", seed))
        elif d <= -0.3:
            parts.append(_pick("faller", seed))

    if popular and len(parts) < 2:
        parts.append(_pick("popular", seed))

    if len(parts) < 2:
        if tier in ("S", "A", "D"):
            parts.append(_pick(tier, seed))
        else:
            parts.append(_pick("neutral", seed))

    return "".join(parts[:2])


def build_tip(r, tier, patch_weapons, tips, popular=False):
    """ホバー表示：自動の事実データ + 手動メモ。"""
    lines = []
    d = r.get("delta")
    if d is None:
        dtxt = "前期比 —"
    elif d > 0:
        dtxt = f"前期比 ▲+{d:.2f}"
    elif d < 0:
        dtxt = f"前期比 ▼{d:.2f}"
    else:
        dtxt = "前期比 ±0"
    lines.append(f'<b>{esc(r["weapon"])}</b>')
    lines.append(f'<span class="tip-stat">{tier}ランク ・ 勝率{r["win_rate"]:.2f}% ・ {dtxt}</span>')
    meta = []
    if r.get("category"):
        meta.append(f'種別:{esc(r["category"])}')
    if r.get("best_rule"):
        meta.append(f'得意:{esc(r["best_rule"])}')
    if meta:
        lines.append('<span class="tip-meta">' + ' / '.join(meta) + '</span>')
    ss = []
    if r.get("sub"):
        si = f'<img class="ss-icon" src="{esc(r["sub_img"])}" alt="" loading="lazy">' if r.get("sub_img") else ""
        ss.append(f'{si}{esc(r["sub"])}')
    if r.get("special"):
        spi = f'<img class="ss-icon" src="{esc(r["special_img"])}" alt="" loading="lazy">' if r.get("special_img") else ""
        ss.append(f'{spi}{esc(r["special"])}')
    if ss:
        lines.append('<span class="tip-meta ss-line">' + ''.join(f'<span class="ss-item">{x}</span>' for x in ss) + '</span>')
    pt = patch_weapons.get(r["weapon"])
    if pt == "buff":
        lines.append('<span class="tip-patch buff">🔼 最新アプデで強化</span>')
    elif pt == "nerf":
        lines.append('<span class="tip-patch nerf">🔽 最新アプデで弱体</span>')
    note = tips.get(r["weapon"])
    if note:
        lines.append(f'<span class="tip-note">💬 {esc(note)}</span>')
    else:
        lines.append(f'<span class="tip-note auto">📊 {auto_note(r, tier, patch_weapons, popular)}</span>')
    return '<span class="tip">' + ''.join(lines) + '</span>'


def _popular_cutoff(ranking):
    """「かなり人気」と言える使用数のしきい値（上位約12%）を返す。"""
    samples = sorted((r["samples"] for r in ranking), reverse=True)
    if len(samples) < 8:
        return float("inf")  # 母数が少ないときは人気判定しない
    idx = max(0, int(len(samples) * 0.12) - 1)
    return samples[idx]


def render_rows(ranking, patch_weapons, tips):
    rows = []
    pop_cut = _popular_cutoff(ranking)
    for i, r in enumerate(ranking, 1):
        tier, color = tier_of(r["win_rate"])
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, "")
        badge = patch_badge(r["weapon"], patch_weapons)
        popular = r["samples"] >= pop_cut
        tip = build_tip(r, tier, patch_weapons, tips, popular)
        search = esc(" ".join(str(r.get(k, "")) for k in ("weapon", "category", "sub", "special")).lower())
        cat = esc(r.get("category", ""))
        rows.append(f"""
        <tr data-search="{search}" data-cat="{cat}">
          <td class="rank">{medal}<span>{i}</span></td>
          <td class="tier"><span class="tier-badge" style="background:{color}">{tier}</span></td>
          <td class="weapon"><span class="wcell">{weapon_img(r)}<span class="wname"><a class="wlink" href="weapon/{esc(weapon_slug(r))}.html">{esc(r['weapon'])}</a><span class="info-dot">?</span>{tip}</span>{badge}</span></td>
          <td class="wr"><b>{r['win_rate']:.2f}</b>%</td>
          <td class="dlt">{delta_html(r.get('delta'))}</td>
          <td class="samples">{r['samples']:,}</td>
        </tr>""")
    return "".join(rows)


def render_panels(mode_key, rules, rule_labels, patch_weapons, tips, active_mode):
    tabs, panels = [], []
    first = True
    for rk in RULE_ORDER:
        if rk not in rules or not rules[rk]:
            continue
        label = rule_labels.get(rk, rk)
        tabs.append(f'<button class="tab {"active" if first else ""}" data-rule="{rk}">{label}</button>')
        disp = "" if first else 'style="display:none"'
        panels.append(f"""
      <div class="ranking-panel" data-rule="{rk}" {disp}>
        <table class="ranking-table">
          <thead>
            <tr><th>順位</th><th>Tier</th><th>ブキ</th><th>勝率</th><th>前期比</th><th>サンプル</th></tr>
          </thead>
          <tbody>{render_rows(rules[rk], patch_weapons, tips)}</tbody>
        </table>
      </div>""")
        first = False
    mode_disp = "" if mode_key == active_mode else 'style="display:none"'
    return f"""
    <div class="mode-block" data-mode="{mode_key}" {mode_disp}>
      <div class="tabs">{''.join(tabs)}</div>
      {''.join(panels)}
    </div>"""


def _t5_delta(r):
    d = r.get("delta")
    if d is None:
        return ""
    if d > 0:
        return f'<span class="t5-delta up">▲+{d:.2f}</span>'
    if d < 0:
        return f'<span class="t5-delta down">▼{d:.2f}</span>'
    return '<span class="t5-delta zero">±0</span>'


def _t5_img(r, cls):
    img = r.get("image")
    if not img:
        return ""
    return (f'<span class="iplate {cls}"><img src="{esc(img)}" '
            f'alt="{esc(r["weapon"])}" loading="lazy"></span>')


def render_top5(items, patch_weapons):
    if not items:
        return ""
    top = items[0]
    tier, color = tier_of(top["win_rate"])
    badge = patch_badge(top["weapon"], patch_weapons)
    hero = f"""
    <div class="t5-hero">
      <div class="t5-crown">1</div>
      {_t5_img(top, "t5-img-lg")}
      <div class="t5-hero-info">
        <div class="t5-hero-top">
          <span class="t5-no1">No.1</span>
          <span class="t5-tier" style="background:{color}">{tier}</span>
        </div>
        <div class="t5-hero-name">{esc(top['weapon'])}{badge}</div>
        <div class="t5-hero-wr">{top['win_rate']:.2f}<span>%</span> {_t5_delta(top)}</div>
      </div>
    </div>"""

    cards = []
    for i, r in enumerate(items[1:5], 2):
        tier, color = tier_of(r["win_rate"])
        badge = patch_badge(r["weapon"], patch_weapons)
        cards.append(f"""
      <div class="t5-card">
        <div class="t5-rank">{i}</div>
        {_t5_img(r, "t5-img")}
        <span class="t5-tier" style="background:{color}">{tier}</span>
        <div class="t5-name">{esc(r['weapon'])}{badge}</div>
        <div class="t5-wr">{r['win_rate']:.2f}<span>%</span></div>
        {_t5_delta(r)}
      </div>""")
    return f"""
  <section class="top5">
    <h2 class="ink-label">現環境 最強ブキ TOP5 <small>Xマッチ・総合勝率</small></h2>
    {hero}
    <div class="t5-grid">{''.join(cards)}</div>
  </section>"""


def render_usage(items):
    ranked = sorted(items, key=lambda x: x["samples"], reverse=True)[:10]
    if not ranked:
        return ""
    mx = ranked[0]["samples"] or 1
    rows = []
    for i, r in enumerate(ranked, 1):
        pct = r["samples"] / mx * 100
        rows.append(f"""
      <div class="use-row">
        <span class="use-rank">{i}</span>
        {weapon_img(r, cls="use-img")}
        <span class="use-name">{esc(r['weapon'])}</span>
        <span class="use-bar"><span class="use-fill" style="width:{pct:.0f}%"></span></span>
        <span class="use-val">{r['samples']:,}</span>
      </div>""")
    return f"""
  <section class="trend-section">
    <h2 class="ink-label">Xマッチ 使用率ランキング</h2>
    <p class="trend-lead">Xマッチで多く使われているブキ TOP10（高レート帯でよく握られているブキの目安）。</p>
    <div class="use-list">{''.join(rows)}</div>
  </section>"""


def build_weapon_index(data):
    """ブキ名 -> meta(画像等) の辞書。先頭ドット有無のゆらぎも吸収。"""
    index = {}
    for mode in data.get("modes", {}).values():
        for lst in mode.get("rules", {}).values():
            for r in lst:
                index.setdefault(r["weapon"], r)
                index.setdefault(r["weapon"].lstrip(".・"), r)
    return index


def aggregate_toplayers(players):
    agg = {}
    for p in players:
        w = (p.get("weapon") or "").strip()
        if not w:
            continue
        a = agg.setdefault(w, {"weapon": w, "count": 0, "best_xp": 0.0})
        a["count"] += 1
        try:
            a["best_xp"] = max(a["best_xp"], float(p.get("xp") or 0))
        except (TypeError, ValueError):
            pass
    out = list(agg.values())
    out.sort(key=lambda x: (-x["count"], -x["best_xp"]))
    return out


def render_toplayer_table(tp, index):
    players = tp.get("players") or []
    if not players:
        return ""
    rows = []
    for i, p in enumerate(players, 1):
        name = esc(p.get("name", ""))
        try:
            xp = f'{float(p.get("xp")):,.1f}'
        except (TypeError, ValueError):
            xp = esc(str(p.get("xp", "")))
        wname = p.get("weapon", "")
        meta = index.get(wname) or index.get(wname.lstrip(".・"))
        wimg = weapon_img(meta, cls="use-img") if meta else ""
        wlink = (f'<a class="wlink" href="weapon/{esc(weapon_slug(meta))}.html">{esc(wname)}</a>'
                 if meta else esc(wname))
        x = (p.get("x") or "").lstrip("@").strip()
        xcell = f'<a href="https://x.com/{esc(x)}" target="_blank" rel="noopener nofollow">@{esc(x)}</a>' if x else ""
        rows.append(f"""
          <tr>
            <td class="tp-rank">{i}</td>
            <td>{name}</td>
            <td class="tp-xp">{xp}</td>
            <td class="tp-weapon"><span class="wcell">{wimg}<span>{wlink}</span></span></td>
            <td class="tp-x">{xcell}</td>
          </tr>""")
    return f"""
    <details class="tp-details">
      <summary><span class="patch-sum-title">📋 XP4000到達者の一覧（{len(players)}人）</span><span class="patch-sum-toggle">クリックで開閉</span></summary>
      <div class="tp-table-wrap">
        <table class="wp-table tp-table">
          <thead><tr><th>#</th><th>プレイヤー</th><th>XP</th><th>達成ブキ</th><th>X</th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
    </details>"""


def render_toplayers(tp, index):
    if not tp:
        return ""
    if tp.get("players"):
        weapons = aggregate_toplayers(tp["players"])
    else:
        weapons = tp.get("weapons") or []
    if not weapons:
        return ""
    mx = max((w.get("count", 0) for w in weapons), default=1) or 1
    rows = []
    for i, w in enumerate(weapons, 1):
        name = w.get("weapon", "")
        cnt = w.get("count", 0)
        meta = index.get(name) or index.get(name.lstrip(".・"))
        img = ""
        slug = ""
        if meta:
            img = weapon_img(meta, cls="use-img")
            slug = weapon_slug(meta)
        name_html = (f'<a class="wlink" href="weapon/{esc(slug)}.html">{esc(name)}</a>'
                     if slug else esc(name))
        pct = cnt / mx * 100
        rows.append(f"""
      <div class="use-row">
        <span class="use-rank">{i}</span>
        {img}
        <span class="use-name">{name_html}</span>
        <span class="use-bar"><span class="use-fill top" style="width:{pct:.0f}%"></span></span>
        <span class="use-val">{cnt}</span>
      </div>""")
    title = esc(tp.get("title", "超上位勢が使うブキ"))
    subtitle = esc(tp.get("subtitle", ""))
    source = esc(tp.get("source", ""))
    updated = esc(tp.get("updated", ""))
    meta_line = " ／ ".join(x for x in [subtitle, f"出典: {source}" if source else "", f"({updated}時点)" if updated else ""] if x)
    player_table = render_toplayer_table(tp, index)
    return f"""
  <section class="trend-section">
    <h2 class="ink-label">{title}</h2>
    <p class="trend-lead">{meta_line}</p>
    <div class="use-list">{''.join(rows)}</div>
    {player_table}
    <p class="patch-hint">XP4000到達者など超高レート帯の使用ブキ。手動データのため更新は不定期です。</p>
  </section>"""


def render_category_trends(cats):
    if not cats:
        return ""
    mx = max(c["avg_win"] for c in cats)
    mn = min(c["avg_win"] for c in cats)
    span = (mx - mn) or 1
    bars = []
    for c in cats:
        pct = 20 + (c["avg_win"] - mn) / span * 80
        bars.append(f"""
      <div class="cat-row">
        <span class="cat-name">{esc(c['name'])}</span>
        <span class="cat-bar"><span class="cat-fill" style="width:{pct:.0f}%"></span></span>
        <span class="cat-val">{c['avg_win']:.2f}%</span>
        <span class="cat-top">最強: {esc(c['top_weapon'])}</span>
      </div>""")
    return f"""
  <section class="trend-section">
    <h2 class="ink-label">ブキ種別ごとの強さ傾向</h2>
    <p class="trend-lead">Xマッチの平均勝率（サンプル数で加重）。種別の現環境での立ち位置がわかります。</p>
    <div class="cat-list">{''.join(bars)}</div>
  </section>"""


def render_ss_trends(sub, special):
    def col(title, icon, items):
        lis = []
        for r in items[:8]:
            lis.append(f'<li><span class="ss-name">{esc(r["name"])}</span><span class="ss-val">{r["avg_win"]:.2f}%</span></li>')
        return f'<div class="ss-col"><h3>{icon} {title}</h3><ol>{"".join(lis)}</ol></div>'
    if not sub and not special:
        return ""
    return f"""
  <section class="trend-section">
    <h2 class="ink-label">サブ / スペシャル別の勝率</h2>
    <p class="trend-lead">そのサブ・スペシャルを持つブキの平均勝率ランキング（Xマッチ）。</p>
    <div class="ss-grid">
      {col("サブウェポン別", "💣", sub)}
      {col("スペシャル別", "✨", special)}
    </div>
  </section>"""


def render_highlight_card(title, items, kind):
    lis = []
    for r in items:
        d = r.get("delta")
        if kind == "used":
            extra = f'<span class="hl-sub">{r["samples"]:,}件</span>'
        elif d is not None:
            cls = "up" if d > 0 else ("down" if d < 0 else "zero")
            sign = "+" if d is not None and d >= 0 else ""
            extra = f'<span class="hl-sub {cls}">{sign}{d:.2f}pt</span>'
        else:
            extra = ""
        lis.append(f'<li><span class="hl-name">{esc(r["weapon"])}</span>{extra}</li>')
    return f"""
    <div class="hl-card {kind}">
      <h3>{esc(title)}</h3>
      <ol>{''.join(lis)}</ol>
    </div>"""


def render_trending_card(trending, weapon_index):
    if not trending or not trending.get("items"):
        return ""
    title = trending.get("title", "今人気向上中の武器！")
    intro = trending.get("intro", "")
    lis = []
    for item in trending.get("items", []):
        name = item.get("weapon", "")
        tag = item.get("tag", "")
        note = item.get("note", "")
        meta = weapon_index.get(name)
        if meta:
            slug = weapon_slug(meta)
            name_html = (
                f'<a class="hl-name wlink" href="weapon/{esc(slug)}.html">{esc(name)}</a>'
            )
        else:
            name_html = f'<span class="hl-name">{esc(name)}</span>'
        tag_html = f'<span class="hl-sub up">{esc(tag)}</span>' if tag else ""
        note_html = f'<span class="hl-note">{esc(note)}</span>' if note else ""
        lis.append(f'<li><div class="hl-trend-main">{name_html}{tag_html}</div>{note_html}</li>')
    intro_p = f'<p class="hl-intro">{esc(intro)}</p>' if intro else ""
    return f"""
    <div class="hl-card trending">
      <h3>{esc(title)}</h3>
      {intro_p}
      <ol class="hl-trend-list">{''.join(lis)}</ol>
    </div>"""


def build(data: dict) -> str:
    updated = jst(data.get("updated_at", ""))
    season = data.get("season")
    prev_season = data.get("prev_season")
    rule_labels = data.get("rule_labels", {})
    modes = data.get("modes", {})
    patch = data.get("patch", {}) or {}
    patch_weapons = patch.get("weapons", {}) or {}
    hl = data.get("highlights") or {}
    trending = data.get("trending") or {}
    trends = data.get("trends") or {}
    tips = data.get("tips") or {}

    season_label = f"シーズン{season}" if season else ""

    # モード選択 + パネル
    mode_keys = list(modes.keys())
    active_mode = mode_keys[0] if mode_keys else ""
    mode_btns = "".join(
        f'<button class="mode-btn {"active" if k == active_mode else ""}" data-mode="{k}">{esc(modes[k]["label"])}</button>'
        for k in mode_keys
    )
    mode_blocks = "".join(
        render_panels(k, modes[k]["rules"], rule_labels, patch_weapons, tips, active_mode)
        for k in mode_keys
    )

    primary_overall = modes.get(active_mode, {}).get("rules", {}).get("overall", [])
    top5_section = render_top5(primary_overall, patch_weapons)

    # 検索・絞り込みバー（種別ボタンはデータから収集）
    cats = []
    for mk in mode_keys:
        for rk, lst in modes[mk]["rules"].items():
            for r in lst:
                c = r.get("category")
                if c and c not in cats:
                    cats.append(c)
    cat_btns = '<button class="cat-btn active" data-cat="">すべて</button>' + "".join(
        f'<button class="cat-btn" data-cat="{esc(c)}">{esc(c)}</button>' for c in cats
    )
    filter_bar = f"""
    <div class="filter-bar">
      <input type="search" id="searchBox" class="search-box" placeholder="🔍 ブキ名・サブ・スペシャルで検索…" autocomplete="off">
      <div class="cat-btns">{cat_btns}</div>
      <p class="filter-empty" id="filterEmpty" style="display:none">該当するブキが見つかりません。</p>
    </div>"""

    weapon_index = build_weapon_index(data)
    toplayers_section = render_toplayers(data.get("toplayers"), weapon_index)

    trend_sections = toplayers_section + \
        render_usage(primary_overall) + \
        render_category_trends(trends.get("category", [])) + \
        render_ss_trends(trends.get("sub", []), trends.get("special", []))

    # ハイライト
    highlight_cards = ""
    if hl or trending.get("items"):
        cards = []
        if hl:
            cards.extend([
                render_highlight_card("勝率が上がったブキ", hl.get("risers", []), "up"),
                render_highlight_card("勝率が下がったブキ", hl.get("fallers", []), "down"),
                render_highlight_card("よく使われているブキ", hl.get("most_used", []), "used"),
            ])
        if trending.get("items"):
            cards.append(render_trending_card(trending, weapon_index))
        highlight_cards = f"""
  <section class="highlights">
    {''.join(cards)}
  </section>"""

    # アプデ強調セクション
    patch_section = ""
    if patch_weapons:
        items = []
        for w, t in patch_weapons.items():
            cls = "buff" if t == "buff" else "nerf"
            lbl = "🔼強化" if t == "buff" else "🔽弱体"
            items.append(f'<span class="patch-chip {cls}">{esc(w)} {lbl}</span>')
        ptitle = esc(patch.get("title", "最新アップデート 調整ブキ"))
        pver = esc(patch.get("version", ""))
        n_buff = sum(1 for t in patch_weapons.values() if t == "buff")
        n_nerf = sum(1 for t in patch_weapons.values() if t == "nerf")
        patch_section = f"""
  <section class="patch-section">
    <details class="patch-details">
      <summary>
        <span class="patch-sum-title">🛠 {ptitle}{(' ' + pver) if pver else ''}</span>
        <span class="patch-sum-meta">🔼{n_buff} ・ 🔽{n_nerf}</span>
        <span class="patch-sum-toggle">クリックで開閉</span>
      </summary>
      <div class="patch-body">
        <div class="patch-chips">{''.join(items)}</div>
        <p class="patch-hint">調整されたブキは表内でも <span class="patch-badge buff">🔼強化</span> / <span class="patch-badge nerf">🔽弱体</span> で表示しています。</p>
      </div>
    </details>
  </section>"""

    # SEO description
    top = modes.get(active_mode, {}).get("rules", {}).get("overall", [])[:3]
    top_desc = "、".join(f"{i}位 {esc(t['weapon'])}（{t['win_rate']:.1f}%）" for i, t in enumerate(top, 1))
    description = f"スプラトゥーン3（{season_label}）の実対戦データに基づく最強武器ランキング。Xマッチ・バンカラのルール別勝率、前シーズン比、tier、アプデ調整ブキを毎日自動更新。総合TOPは{top_desc}。"

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
{google_verify_meta()}<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{SITE_NAME}｜Xマッチ・バンカラの勝率で毎日更新【スプラ3】</title>
<meta name="description" content="{esc(description)}">
<meta name="keywords" content="スプラ 最強武器,スプラ ブキ 勝率,スプラ tier,スプラトゥーン3 武器 ランキング,スプラ3 最強,バンカラ Xマッチ">
<link rel="canonical" href="{SITE_URL}">
<meta property="og:title" content="{SITE_NAME}｜勝率データで毎日更新">
<meta property="og:description" content="{esc(description)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{SITE_URL}">
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"WebSite","name":"{SITE_NAME}","url":"{SITE_URL}"}}
</script>
<link rel="stylesheet" href="style.css">
</head>
<body>
<header class="hero">
  <div class="hero-splat hero-splat-pink" aria-hidden="true"></div>
  <div class="hero-splat hero-splat-yellow" aria-hidden="true"></div>
  <div class="hero-splat hero-splat-cyan" aria-hidden="true"></div>
  <div class="hero-inner">
    <p class="hero-tag">SPLATOON 3 / Xマッチデータ</p>
    <h1><span class="ink">スプラ</span>最強武器<br class="sp-br">ランキング</h1>
    <p class="lead">Xマッチ・バンカラの実対戦データ（stat.ink）から、勝率・tier・前シーズン比を自動集計。</p>
    <p class="badges"><span class="season-badge">スプラトゥーン3 / {esc(season_label)}</span></p>
    <p class="updated">最終更新: {updated}（毎日自動更新）</p>
    <p class="hero-cta"><a href="tier.html" class="cta-btn ghost">最強tier表</a> <a href="border.html" class="cta-btn ghost">Xボーダー</a> <a href="shindan.html" class="cta-btn accent">タイプ診断</a> <a href="beginner.html" class="cta-btn ghost">初心者ガイド</a> <a href="rules.html" class="cta-btn ghost">ルール別</a> <a href="report.html" class="cta-btn ghost">環境レポート</a></p>
  </div>
</header>
{site_nav()}

<main class="container">
{top5_section}
{highlight_cards}
{patch_section}

  <section class="card">
    <div class="mode-switch">{mode_btns}</div>
    {filter_bar}
    {mode_blocks}
  </section>
{trend_sections}

  <section class="about">
    <h2>このランキングについて</h2>
    <p>本ランキングは、対戦記録共有サービス <a href="https://stat.ink/" target="_blank" rel="noopener">stat.ink</a> が公開するスプラトゥーン3の集計データ（最新シーズン）をもとに、ブキごとの勝率を算出して並べたものです。勝率の高い順に <b>S / A / B / C / D</b> の tier を自動判定し、前シーズンからの勝率変化を <span class="delta up">▲</span>（上昇）/ <span class="delta down">▼</span>（下降）で表示しています。</p>
    <h3>tier の目安</h3>
    <ul class="tier-legend">
      <li><span class="tier-badge" style="background:#ff3b6b">S</span> 勝率52%以上</li>
      <li><span class="tier-badge" style="background:#ff8a3d">A</span> 50.5%以上</li>
      <li><span class="tier-badge" style="background:#ffd23d">B</span> 49.5%以上</li>
      <li><span class="tier-badge" style="background:#52d273">C</span> 48%以上</li>
      <li><span class="tier-badge" style="background:#5b9cff">D</span> 48%未満</li>
    </ul>
    <h3>注意</h3>
    <p>データは stat.ink 利用者の対戦結果に基づくため、全プレイヤーの傾向とは多少異なる場合があります。「サンプル」は集計に使われた対戦データ件数で、少ないほど勝率がブレやすくなります。勝率は使う人の腕前にも左右されるため、参考としてご覧ください。</p>
  </section>

  <footer class="site-footer">
    <p>{SITE_NAME} ｜ データ出典: <a href="https://stat.ink/" target="_blank" rel="noopener">stat.ink</a>（CC-BY-4.0）</p>
    <p class="disclaimer">本サイトは非公式のファンサイトです。任天堂株式会社とは関係ありません。</p>
  </footer>
</main>

<script src="app.js"></script>
</body>
</html>
"""


def collect_weapons(data):
    """ブキ名 -> {meta, modes:{mode:{rule:{win_rate,delta,samples,rank,label}}}} を集計。"""
    modes = data.get("modes", {})
    rule_labels = data.get("rule_labels", {})
    weapons = {}
    for mk, mode in modes.items():
        mlabel = mode.get("label", mk)
        for rk in RULE_ORDER:
            lst = mode.get("rules", {}).get(rk, [])
            for rank, r in enumerate(lst, 1):
                name = r["weapon"]
                w = weapons.setdefault(name, {"meta": r, "modes": {}})
                # メタはXマッチ総合を優先
                if mk == list(modes.keys())[0] and rk == "overall":
                    w["meta"] = r
                w["modes"].setdefault(mlabel, {})[rk] = {
                    "win_rate": r["win_rate"],
                    "delta": r.get("delta"),
                    "samples": r["samples"],
                    "rank": rank,
                    "label": rule_labels.get(rk, rk),
                }
    return weapons


def render_tier_gauge(win_rate):
    pos = max(2.0, min(98.0, (win_rate - 45.0) / 10.0 * 100.0))
    bar = ("linear-gradient(90deg,"
           "#5b9cff 0%,#5b9cff 30%,"
           "#52d273 30%,#52d273 45%,"
           "#ffd23d 45%,#ffd23d 55%,"
           "#ff8a3d 55%,#ff8a3d 70%,"
           "#ff3b6b 70%,#ff3b6b 100%)")
    return f"""
      <div class="wp-gauge">
        <div class="wp-gauge-bar" style="background:{bar}">
          <span class="wp-gauge-mid" style="left:50%"></span>
          <span class="wp-gauge-pin" style="left:{pos:.1f}%"><b>{win_rate:.2f}%</b></span>
        </div>
        <div class="wp-gauge-labels"><span>D</span><span>C</span><span>B</span><span>A</span><span>S</span></div>
      </div>"""


def _wchip(m, prefix=""):
    slug = weapon_slug(m)
    img = (f'<span class="iplate wchip-img"><img src="{esc(m["image"])}" alt="" loading="lazy"></span>'
           if m.get("image") else "")
    return (f'<a class="wchip" href="{prefix}{esc(slug)}.html">{img}'
            f'<span class="wchip-name">{esc(m["weapon"])}</span>'
            f'<span class="wchip-wr">{m["win_rate"]:.2f}%</span></a>')


def render_similar(meta, all_weapons):
    name = meta["weapon"]

    def pick(key, val):
        if not val:
            return []
        items = [m for m in all_weapons if m["weapon"] != name and m.get(key) == val]
        items.sort(key=lambda x: x["win_rate"], reverse=True)
        return items[:6]

    blocks = []
    groups = [
        (f'同じ種別（{esc(meta.get("category",""))}）の強いブキ', pick("category", meta.get("category"))),
        (f'同じサブ（{esc(meta.get("sub",""))}）のブキ', pick("sub", meta.get("sub"))),
        (f'同じスペシャル（{esc(meta.get("special",""))}）のブキ', pick("special", meta.get("special"))),
    ]
    for title, items in groups:
        if not items:
            continue
        chips = "".join(_wchip(m) for m in items)
        blocks.append(f'<div class="wp-sim-group"><h3>{title}</h3><div class="wchips">{chips}</div></div>')
    if not blocks:
        return ""
    return f"""
  <section class="card wp-card">
    <h2>関連するブキ</h2>
    {''.join(blocks)}
  </section>"""


def render_weapon_topplayers(name, toplayers):
    players = (toplayers or {}).get("players") or []
    key = name.lstrip(".・")
    hits = [p for p in players if (p.get("weapon") or "").lstrip(".・") == key]
    if not hits:
        return ""
    lis = []
    for p in hits:
        try:
            xp = f'{float(p.get("xp")):,.1f}'
        except (TypeError, ValueError):
            xp = esc(str(p.get("xp", "")))
        x = (p.get("x") or "").lstrip("@").strip()
        xlink = f' <a href="https://x.com/{esc(x)}" target="_blank" rel="noopener nofollow">@{esc(x)}</a>' if x else ""
        lis.append(f'<li><span class="wp-tp-name">{esc(p.get("name",""))}</span><span class="wp-tp-xp">XP {xp}</span>{xlink}</li>')
    return f"""
  <section class="card wp-card">
    <h2 class="ink-label">このブキでXP4000到達したプレイヤー</h2>
    <ul class="wp-tp-list">{''.join(lis)}</ul>
    <p class="patch-hint">超高レート帯での使用実績。手動データのため一部のみです。</p>
  </section>"""


def render_matchup(name, meta, matchups):
    if not matchups:
        return ""
    entry = (matchups.get("by_weapon", {}) or {}).get(name)
    if not entry:
        entry = (matchups.get("by_category", {}) or {}).get(meta.get("category", ""))
    if not entry:
        return ""
    good = entry.get("good") or []
    bad = entry.get("bad") or []
    note = entry.get("note")

    def chips(types, cls):
        return "".join(f'<span class="mu-chip {cls}">{esc(t)}</span>' for t in types)

    good_html = f'<div class="mu-row"><span class="mu-label good">有利</span><div class="mu-chips">{chips(good, "good")}</div></div>' if good else ""
    bad_html = f'<div class="mu-row"><span class="mu-label bad">苦手</span><div class="mu-chips">{chips(bad, "bad")}</div></div>' if bad else ""
    note_html = f'<p class="wp-note">💬 {esc(note)}</p>' if note else ""
    return f"""
  <section class="card wp-card">
    <h2 class="ink-label">相性（有利・苦手な相手）</h2>
    {good_html}
    {bad_html}
    {note_html}
    <p class="patch-hint">ブキ種ごとの一般的な目安です（立ち位置や腕前で変わります）。</p>
  </section>"""


def site_nav(prefix: str = "") -> str:
    """全ページ共通ナビ。武器ページは prefix='../'"""
    p = prefix
    return f"""<nav class="site-nav" aria-label="サイト内ナビ">
  <a href="{p}index.html">ランキング</a>
  <a href="{p}tier.html">tier表</a>
  <a href="{p}border.html">Xボーダー</a>
  <a href="{p}shindan.html">診断</a>
  <a href="{p}beginner.html">初心者</a>
  <a href="{p}rules.html">ルール別</a>
  <a href="{p}report.html">環境</a>
</nav>"""


def render_playstyle(name, playstyle):
    data = (playstyle or {}).get("weapons", {}) if isinstance(playstyle, dict) else {}
    e = data.get(name)
    if not e:
        return ""
    pros = e.get("pros") or []
    cons = e.get("cons") or []
    play = e.get("playstyle")
    rep = e.get("reputation")
    source = e.get("source")
    pros_html = ("".join(f'<li>{esc(p)}</li>' for p in pros))
    cons_html = ("".join(f'<li>{esc(c)}</li>' for c in cons))
    cols = []
    if pros:
        cols.append(f'<div class="ps-col pros"><h3>長所</h3><ul>{pros_html}</ul></div>')
    if cons:
        cols.append(f'<div class="ps-col cons"><h3>短所</h3><ul>{cons_html}</ul></div>')
    grid = f'<div class="ps-grid">{"".join(cols)}</div>' if cols else ""
    play_html = f'<div class="ps-play"><h3>立ち回り</h3><p>{esc(play)}</p></div>' if play else ""
    rep_html = f'<p class="ps-rep"><b>評判:</b> {esc(rep)}</p>' if rep else ""
    source_html = f'<p class="patch-hint">出典: {esc(source)}</p>' if source else ""
    return f"""
  <section class="card wp-card">
    <h2 class="ink-label">立ち回り・長所/短所</h2>
    {grid}
    {play_html}
    {rep_html}
    {source_html}
  </section>"""


def render_weapon_page(name, info, data, patch_weapons, tips, all_weapons, toplayers):
    r = info["meta"]
    tier, color = tier_of(r["win_rate"])
    season_label = f"シーズン{data.get('season')}" if data.get("season") else ""
    badge = patch_badge(name, patch_weapons)

    note = tips.get(name) or auto_note(r, tier, patch_weapons)
    note_icon = "💬" if tips.get(name) else "📊"

    ss = []
    if r.get("sub"):
        si = f'<img class="ss-icon" src="{esc(r["sub_img"])}" alt="" loading="lazy">' if r.get("sub_img") else ""
        ss.append(f'<span class="ss-item">{si}サブ: {esc(r["sub"])}</span>')
    if r.get("special"):
        spi = f'<img class="ss-icon" src="{esc(r["special_img"])}" alt="" loading="lazy">' if r.get("special_img") else ""
        ss.append(f'<span class="ss-item">{spi}SP: {esc(r["special"])}</span>')
    ss_html = '<div class="wp-ss">' + "".join(ss) + "</div>" if ss else ""

    # モード別・ルール別テーブル
    tables = []
    for mlabel, rules in info["modes"].items():
        rws = []
        for rk in RULE_ORDER:
            if rk not in rules:
                continue
            d = rules[rk]
            rws.append(f"""
          <tr>
            <td>{esc(d['label'])}</td>
            <td><b>{d['win_rate']:.2f}</b>%</td>
            <td>{delta_html(d['delta'])}</td>
            <td>{d['rank']}位</td>
            <td>{d['samples']:,}</td>
          </tr>""")
        if rws:
            tables.append(f"""
        <h3>{esc(mlabel)}</h3>
        <table class="wp-table">
          <thead><tr><th>ルール</th><th>勝率</th><th>前期比</th><th>順位</th><th>サンプル</th></tr></thead>
          <tbody>{''.join(rws)}</tbody>
        </table>""")

    img = r.get("image")
    img_html = (f'<span class="iplate t5-img-lg"><img src="{esc(img)}" '
                f'alt="{esc(name)}" loading="lazy"></span>') if img else ""

    desc = (f"スプラトゥーン3の「{name}」の最新勝率・tier・前シーズン比（{season_label}）。"
            f"Xマッチ・バンカラのルール別勝率を毎日自動更新。種別{esc(r.get('category',''))}、"
            f"サブ{esc(r.get('sub',''))}、スペシャル{esc(r.get('special',''))}。")
    page_url = f"{SITE_URL}weapon/{weapon_slug(r)}.html"

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
{google_verify_meta()}<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(name)}の勝率・tier【スプラ3 最強武器ランキング】</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{page_url}">
<meta property="og:title" content="{esc(name)}の勝率・tier｜{SITE_NAME}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:type" content="article">
<meta property="og:url" content="{page_url}">
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[
{{"@type":"ListItem","position":1,"name":"{SITE_NAME}","item":"{SITE_URL}"}},
{{"@type":"ListItem","position":2,"name":"{esc(name)}","item":"{page_url}"}}]}}
</script>
<link rel="stylesheet" href="../style.css">
</head>
<body>
{site_nav("../")}
<main class="container wp-container">
  <nav class="wp-breadcrumb"><a href="../index.html">← {SITE_NAME}</a></nav>
  <section class="wp-hero">
    {img_html}
    <div class="wp-hero-info">
      <div class="wp-hero-top">
        <span class="tier-badge" style="background:{color}">{tier}</span>
        <span class="wp-cat">{esc(r.get('category',''))}</span>{badge}
      </div>
      <h1>{esc(name)}</h1>
      <div class="wp-wr">総合勝率 <b>{r['win_rate']:.2f}</b>% {delta_html(r.get('delta'))}</div>
      {render_tier_gauge(r['win_rate'])}
      {ss_html}
      <p class="wp-note">{note_icon} {note}</p>
    </div>
  </section>

  <section class="card wp-card">
    <h2>ルール別の勝率</h2>
    {''.join(tables)}
    <p class="patch-hint">データ出典: <a href="https://stat.ink/" target="_blank" rel="noopener">stat.ink</a>（{esc(season_label)}）。勝率は使用者の腕前にも左右されます。</p>
  </section>
{render_playstyle(name, data.get('playstyle'))}
{render_matchup(name, r, data.get('matchups'))}
{render_weapon_topplayers(name, toplayers)}
{render_similar(r, all_weapons)}

  <footer class="site-footer">
    <p><a href="../index.html">{SITE_NAME}</a> ｜ データ出典: <a href="https://stat.ink/" target="_blank" rel="noopener">stat.ink</a>（CC-BY-4.0）</p>
    <p class="disclaimer">本サイトは非公式のファンサイトです。任天堂株式会社とは関係ありません。</p>
  </footer>
</main>
</body>
</html>
"""


SHINDAN_TYPES = {
    "front": {"emoji": "⚔️", "name": "前線アタッカー", "cats": ["シューター", "マニューバー"],
              "desc": "中射程で撃ち合い、前線を押し上げるエースタイプ。汎用性が高く、どのルールでも腐りません。"},
    "assassin": {"emoji": "🔥", "name": "近接アサシン", "cats": ["ローラー", "フデ", "ワイパー", "ブラスター"],
                 "desc": "懐に潜り込んで一気に仕留める奇襲タイプ。裏取り・キル能力で試合を動かします。"},
    "backline": {"emoji": "🎯", "name": "後衛スナイパー", "cats": ["チャージャー", "スピナー", "ストリンガー"],
                 "desc": "安全な距離から制圧する司令塔タイプ。エイムと位置取りで強さが青天井。"},
    "support": {"emoji": "🛡️", "name": "塗り・サポート", "cats": ["スロッシャー", "シェルター"],
                "desc": "塗り・スペシャル・盾で味方を支える縁の下タイプ。安定感で勝率を底上げ。"},
}

SHINDAN_QUESTIONS = [
    ("敵を見つけたら、まず？", [
        ("まっすぐ突っ込む", "assassin"), ("中距離で削り合う", "front"),
        ("安全な距離から狙う", "backline"), ("味方の援護を優先", "support")]),
    ("自分の得意プレイは？", [
        ("一対一のキル", "assassin"), ("立ち回りで翻弄", "front"),
        ("一撃必殺", "backline"), ("塗り広げて陣地確保", "support")]),
    ("ピンチになりがちなのは？", [
        ("囲まれて溶ける", "assassin"), ("中距離の撃ち合い負け", "front"),
        ("近づかれてパニック", "backline"), ("キル不足で押し込まれる", "support")]),
    ("好きな距離感は？", [
        ("ゼロ距離", "assassin"), ("半歩前", "front"),
        ("画面の端から", "backline"), ("後方〜中央", "support")]),
    ("試合で一番重視するのは？", [
        ("キル数", "assassin"), ("前線の押し上げ", "front"),
        ("デスしないこと", "backline"), ("塗りとスペシャル", "support")]),
]


SHINDAN_CONTENT_MAP = {
    "frontline_attacker": "front",
    "melee_assassin": "assassin",
    "rear_sniper": "backline",
    "paint_support": "support",
}


def render_shindan(all_weapons, shindan_content=None):
    sc = shindan_content or {}
    sc_types = sc.get("types") or {}
    recos = {}
    for key, t in SHINDAN_TYPES.items():
        sc_key = next((k for k, v in SHINDAN_CONTENT_MAP.items() if v == key), None)
        sc_type = sc_types.get(sc_key) if sc_key else None
        if sc_type and sc_type.get("recommended_weapons"):
            recos[key] = wchips_by_names(sc_type["recommended_weapons"], all_weapons, prefix="weapon/")
        else:
            items = [m for m in all_weapons if m.get("category") in t["cats"]]
            items.sort(key=lambda x: x["win_rate"], reverse=True)
            recos[key] = "".join(_wchip(m, prefix="weapon/") for m in items[:4])

    result_info = {}
    for k, v in SHINDAN_TYPES.items():
        sc_key = next((sk for sk, sv in SHINDAN_CONTENT_MAP.items() if sv == k), None)
        sc_type = sc_types.get(sc_key) if sc_key else None
        name = sc_type.get("display_name") if sc_type else v["name"]
        desc = sc_type.get("description") if sc_type else v["desc"]
        catch = sc_type.get("catchphrase") if sc_type else ""
        if catch:
            desc = f"{catch} {desc}"
        result_info[k] = {
            "emoji": v["emoji"],
            "name": name,
            "desc": desc,
            "recos": recos[k],
        }

    bonus = sc.get("bonus_content") or {}
    bonus_html = ""
    mistakes = bonus.get("beginners_mistakes_top5")
    if mistakes:
        items = "".join(
            f'<li><span class="sd-mistake-rank">{m.get("rank")}</span> {esc(m.get("issue",""))}</li>'
            for m in mistakes.get("list") or []
        )
        bonus_html += f"""<section class="guide-section sd-bonus">
          <h2>{esc(mistakes.get("title",""))}</h2>
          <ol class="sd-mistakes">{items}</ol>
        </section>"""
    meta = bonus.get("season16_meta_comment")
    if meta:
        bonus_html += f"""<section class="guide-section sd-bonus">
          <h2>{esc(meta.get("title",""))}</h2>
          <p class="sd-meta">{esc(meta.get("comment",""))}</p>
        </section>"""
    suit = bonus.get("suitability_by_category")
    if suit:
        rows = "".join(
            f"""<tr><th>{esc(cat)}</th><td>{esc(v.get("target",""))}</td><td>{esc(v.get("not_target",""))}</td></tr>"""
            for cat, v in suit.items()
        )
        bonus_html += f"""<section class="guide-section sd-bonus">
          <h2>武器種別・向き不向き</h2>
          <div class="sd-suit-table-wrap"><table class="sd-suit-table">
            <thead><tr><th>武器種</th><th>向いてる人</th><th>向いてない人</th></tr></thead>
            <tbody>{rows}</tbody>
          </table></div>
        </section>"""

    q_html = []
    for qi, (q, opts) in enumerate(SHINDAN_QUESTIONS):
        btns = "".join(
            f'<button class="sd-opt" data-q="{qi}" data-type="{t}">{esc(label)}</button>'
            for label, t in opts
        )
        q_html.append(f"""
      <div class="sd-q" data-q="{qi}"{'' if qi == 0 else ' style="display:none"'}>
        <p class="sd-qnum">Q{qi+1} / {len(SHINDAN_QUESTIONS)}</p>
        <h2 class="sd-qtext">{esc(q)}</h2>
        <div class="sd-opts">{btns}</div>
      </div>""")

    desc = "スプラトゥーン3の戦闘タイプ診断。5つの質問であなたのプレイスタイル（前線/アサシン/後衛/サポート）を判定し、今の環境で勝てるおすすめブキを提案します。"
    page_url = f"{SITE_URL}shindan.html"
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
{google_verify_meta()}<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>スプラ 戦闘タイプ診断｜あなたに合う最強ブキは？【スプラ3】</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{page_url}">
<meta property="og:title" content="スプラ 戦闘タイプ診断｜あなたに合う最強ブキは？">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{page_url}">
<link rel="stylesheet" href="style.css">
</head>
<body>
{site_nav()}
<main class="container wp-container">
  <nav class="wp-breadcrumb"><a href="index.html">← {SITE_NAME}</a></nav>
  <section class="sd-card">
    <h1 class="sd-title">戦闘タイプ診断</h1>
    <p class="sd-lead">5つの質問で、あなたのプレイスタイルとおすすめブキを判定！</p>
    <div class="sd-progress"><span class="sd-progress-bar" id="sdBar"></span></div>
    {''.join(q_html)}
    <div class="sd-result" id="sdResult" style="display:none"></div>
  </section>
  {bonus_html}
  <footer class="site-footer">
    <p><a href="index.html">{SITE_NAME}</a> ｜ データ出典: <a href="https://stat.ink/" target="_blank" rel="noopener">stat.ink</a></p>
  </footer>
</main>
<script>
const RESULTS = {json.dumps(result_info, ensure_ascii=False)};
const TOTAL = {len(SHINDAN_QUESTIONS)};
const scores = {{}};
let answered = 0;
function showResult() {{
  let best = null, max = -1;
  for (const k in RESULTS) {{ const s = scores[k] || 0; if (s > max) {{ max = s; best = k; }} }}
  const r = RESULTS[best];
  document.querySelectorAll('.sd-q').forEach(e => e.style.display = 'none');
  const el = document.getElementById('sdResult');
  el.innerHTML =
    '<p class="sd-result-label">あなたのタイプは…</p>' +
    '<h2 class="sd-result-name">' + r.name + '</h2>' +
    '<p class="sd-result-desc">' + r.desc + '</p>' +
    '<h3 class="sd-reco-title">あなたにおすすめのブキ</h3>' +
    '<div class="wchips">' + r.recos + '</div>' +
    '<button class="sd-retry" onclick="location.reload()">もう一度診断する</button>';
  el.style.display = 'block';
  document.getElementById('sdBar').style.width = '100%';
}}
document.querySelectorAll('.sd-opt').forEach(btn => {{
  btn.addEventListener('click', () => {{
    const t = btn.dataset.type;
    scores[t] = (scores[t] || 0) + 1;
    answered++;
    document.getElementById('sdBar').style.width = (answered / TOTAL * 100) + '%';
    const cur = parseInt(btn.dataset.q, 10);
    const next = document.querySelector('.sd-q[data-q="' + (cur + 1) + '"]');
    document.querySelector('.sd-q[data-q="' + cur + '"]').style.display = 'none';
    if (next) {{ next.style.display = 'block'; }} else {{ showResult(); }}
  }});
}});
</script>
</body>
</html>
"""


def _wlink(name, index, prefix="weapon/"):
    meta = index.get(name) or index.get(name.lstrip(".・"))
    if meta:
        return f'<a class="wlink" href="{prefix}{esc(weapon_slug(meta))}.html">{esc(name)}</a>'
    return esc(name)


def wchips_by_names(names, all_weapons, prefix="weapon/"):
    by_name = {m["weapon"]: m for m in all_weapons}
    chips = []
    for n in names:
        m = by_name.get(n) or by_name.get(n.lstrip(".・"))
        if m:
            chips.append(_wchip(m, prefix))
    return "".join(chips)


def _guide_page(title, desc, filename, body):
    page_url = f"{SITE_URL}{filename}"
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
{google_verify_meta()}<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}｜{SITE_NAME}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{page_url}">
<link rel="stylesheet" href="style.css">
</head>
<body>
{site_nav()}
<main class="container wp-container">
  <nav class="wp-breadcrumb"><a href="index.html">← {SITE_NAME}</a></nav>
  {body}
  <footer class="site-footer">
    <p><a href="index.html">{SITE_NAME}</a> ｜ データ出典: <a href="https://stat.ink/" target="_blank" rel="noopener">stat.ink</a></p>
  </footer>
</main>
</body>
</html>
"""


def render_beginner_page(data, index):
    b = data if data.get("by_category") else (data.get("beginner") or {})
    if not b:
        return ""
    cats = []
    for cat, items in (b.get("by_category") or {}).items():
        lis = []
        for it in items:
            lis.append(f"""<li class="guide-item">
              <h3>{_wlink(it["weapon"], index)}</h3>
              <p>{esc(it.get("reason",""))}</p>
              <p class="guide-tip">TIP: {esc(it.get("tip",""))}</p>
            </li>""")
        cats.append(f'<section class="guide-section"><h2>{esc(cat)}</h2><ul class="guide-list">{"".join(lis)}</ul></section>')
    avoid = "".join(
        f'<li><b>{_wlink(a["weapon"], index)}</b> — {esc(a.get("reason",""))}</li>'
        for a in b.get("avoid_for_beginners") or []
    )
    weapon_list = _index_to_list(index)
    tiers = ""
    for block in (b.get("rankings_by_tier") or {}).values():
        pick_names = block.get("picks") or []
        tiers += f"""<div class="tier-pick-block">
          <h3>{esc(block.get("label",""))}</h3>
          <p>{esc(block.get("comment",""))}</p>
          <div class="wchips">{wchips_by_names(pick_names, weapon_list)}</div>
        </div>"""
    body = f"""<article class="guide-card">
      <h1 class="guide-title">{esc(b.get("title","初心者におすすめのブキ"))}</h1>
      <p class="guide-intro">{esc(b.get("intro",""))}</p>
      {''.join(cats)}
      <section class="guide-section avoid"><h2>避けた方がいいブキ</h2><ul>{avoid}</ul></section>
      <section class="guide-section"><h2>ウデマエ帯別おすすめ</h2>{tiers}</section>
    </article>"""
    desc = b.get("intro", "")[:120]
    return _guide_page(b.get("title", "初心者におすすめのブキ"), desc, "beginner.html", body)


def _index_to_list(index):
    seen = set()
    out = []
    for v in index.values():
        w = v.get("weapon")
        if w and w not in seen:
            seen.add(w)
            out.append(v)
    return out


def render_rules_page(data, index):
    if not data.get("rules"):
        return ""
    weapon_list = _index_to_list(index)
    sections = []
    for key in ("area", "yagura", "hoko", "asari"):
        rule = data["rules"].get(key)
        if not rule:
            continue
        picks = []
        for i, p in enumerate(rule.get("picks") or [], 1):
            picks.append(f"""<li class="rule-pick">
              <span class="rule-rank">{i}</span>
              <div><h3>{_wlink(p["weapon"], index)}</h3><p>{esc(p.get("reason",""))}</p></div>
            </li>""")
        sections.append(f"""<section class="guide-section rule-block" id="{key}">
          <h2>{esc(rule.get("label", key))}</h2>
          <p class="rule-lead">{esc(rule.get("lead",""))}</p>
          <ol class="rule-picks">{''.join(picks)}</ol>
        </section>""")
    tips = data.get("team_composition_tips") or {}
    tip_html = ""
    if tips:
        tip_html = f"""<section class="guide-section team-tip">
          <h2>{esc(tips.get("title",""))}</h2>
          <p>{esc(tips.get("advice",""))}</p>
        </section>"""
    body = f"""<article class="guide-card">
      <h1 class="guide-title">{esc(data.get("title","ルール別おすすめブキ"))}</h1>
      <p class="guide-intro">ガチルールごとに刺さるブキと、その理由をまとめました。ランキングと合わせて編成の参考に。</p>
      {''.join(sections)}
      {tip_html}
    </article>"""
    desc = "スプラ3 ガチエリア・ヤグラ・ホコ・アサリ別のおすすめブキTOP5と編成のコツ。"
    return _guide_page(data.get("title", "ルール別おすすめブキ"), desc, "rules.html", body)


def render_border_page(data):
    if not data.get("rules"):
        return ""
    updated = jst(data.get("updated_at", ""))
    season = data.get("season")
    season_label = f"シーズン{season}" if season else ""
    rows = []
    for rule in data.get("rules") or []:
        if rule.get("error"):
            continue
        st = rule.get("stats") or {}
        rows.append(f"""<tr>
          <td><a href="{esc(rule.get('source_url',''))}" target="_blank" rel="noopener">{esc(rule.get('label',''))}</a></td>
          <td class="xb-top">{st.get('top1_x_power','—')}</td>
          <td class="xb-border"><b>{st.get('border_x_power','—')}</b></td>
          <td>{st.get('border_rank','—')}位</td>
        </tr>""")
    body = f"""<article class="guide-card">
      <h1 class="guide-title">Xランキング ボーダー目安</h1>
      <p class="guide-intro">{season_label} / {data.get('year')}年{data.get('month')}月 / 地域 {esc(data.get('region','JP'))}。
        ガチルール別の TOP500 付近 X パワー（<a href="https://sendou.ink/" target="_blank" rel="noopener">sendou.ink</a> 参考）。最終更新: {updated}。</p>
      <table class="xb-table">
        <thead><tr><th>ルール</th><th>1位 X</th><th>ボーダー目安</th><th>順位</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
      <p class="patch-hint">{esc(data.get('source_note',''))} 王冠（TOP500）はイカリング3でも確認できます。</p>
    </article>"""
    desc = f"スプラ3 XマッチのTOP500ボーダー目安（{season_label}）。ルール別Xパワーを毎日更新。"
    return _guide_page("Xランキング ボーダー", desc, "border.html", body)


def render_meta_report(data, index):
    if not data.get("summary"):
        return ""
    hi = "".join(f"<li>{esc(x)}</li>" for x in data.get("highlights") or [])
    rising = "".join(f"<li>{esc(x)}</li>" for x in data.get("rising") or [])
    falling = "".join(f"<li>{esc(x)}</li>" for x in data.get("falling") or [])
    body = f"""<article class="guide-card report-card">
      <h1 class="guide-title">{esc(data.get("title","環境レポート"))}</h1>
      <p class="report-date">更新: {esc(data.get("date",""))}</p>
      <p class="guide-intro report-summary">{esc(data.get("summary",""))}</p>
      <section class="guide-section"><h2>今シーズンのハイライト</h2><ul class="report-list">{hi}</ul></section>
      <section class="guide-section report-up"><h2>上昇中</h2><ul class="report-list">{rising}</ul></section>
      <section class="guide-section report-down"><h2>下降気味</h2><ul class="report-list">{falling}</ul></section>
      <section class="guide-section"><h2>Ver.11.2.0 所感</h2><p>{esc(data.get("ver_note",""))}</p></section>
      <p class="report-links"><a href="tier.html">最強tier表</a> ｜ <a href="index.html">勝率ランキング</a></p>
    </article>"""
    desc = data.get("summary", "")[:140]
    return _guide_page(data.get("title", "環境レポート"), desc, "report.html", body)


def render_tierlist(ranking, data):
    season_label = f"シーズン{data.get('season')}" if data.get("season") else ""
    updated = jst(data.get("updated_at", ""))
    tier_groups = {t[1]: [] for t in TIERS}
    for r in ranking:
        t, _ = tier_of(r["win_rate"])
        tier_groups[t].append(r)

    rows = []
    for thr, label, color in TIERS:
        items = tier_groups.get(label, [])
        chips = "".join(
            f'<a class="tl-chip" href="weapon/{esc(weapon_slug(m))}.html" title="{esc(m["weapon"])} {m["win_rate"]:.2f}%">'
            f'<span class="iplate tl-img"><img src="{esc(m["image"])}" alt="{esc(m["weapon"])}" loading="lazy"></span>'
            f'<span class="tl-name">{esc(m["weapon"])}</span></a>'
            for m in items if m.get("image")
        )
        if not items:
            continue
        rows.append(f"""
      <div class="tl-row">
        <div class="tl-label" style="background:{color}">{label}</div>
        <div class="tl-items">{chips}</div>
      </div>""")

    desc = f"スプラトゥーン3の最強武器tier表（{season_label}）。Xマッチ総合の実勝率で S/A/B/C/D を自動判定。毎日更新。"
    page_url = f"{SITE_URL}tier.html"
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
{google_verify_meta()}<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>スプラ3 最強武器tier表【{esc(season_label)}・毎日更新】</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{page_url}">
<meta property="og:title" content="スプラ3 最強武器tier表｜{SITE_NAME}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{page_url}">
<link rel="stylesheet" href="style.css">
</head>
<body>
{site_nav()}
<main class="container wp-container">
  <nav class="wp-breadcrumb"><a href="index.html">← {SITE_NAME}</a></nav>
  <section class="tl-card">
    <h1 class="tl-title">スプラ3 最強武器 tier表</h1>
    <p class="tl-lead">Xマッチ総合の実勝率で自動判定（{esc(season_label)}）。最終更新: {updated}。武器をタップで詳細へ。</p>
    <div class="tl-list">{''.join(rows)}</div>
    <p class="patch-hint">勝率ベースの自動tierです。腕前や環境で変わるため目安としてご覧ください。データ: <a href="https://stat.ink/" target="_blank" rel="noopener">stat.ink</a></p>
  </section>
  <footer class="site-footer">
    <p><a href="index.html">{SITE_NAME}</a> ｜ データ出典: <a href="https://stat.ink/" target="_blank" rel="noopener">stat.ink</a></p>
  </footer>
</main>
</body>
</html>
"""


def write_sitemap(slugs, extra_pages=None):
    today = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d")
    static = ["tier.html", "shindan.html", "border.html", "beginner.html", "rules.html", "report.html"]
    if extra_pages:
        static = [p for p in static if p in extra_pages]
    urls = [SITE_URL] + [f"{SITE_URL}{p}" for p in static] + [f"{SITE_URL}weapon/{s}.html" for s in slugs]
    body = "".join(
        f"  <url><loc>{u}</loc><lastmod>{today}</lastmod></url>\n" for u in urls
    )
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{body}</urlset>\n")


def main():
    with open("ranking.json", encoding="utf-8") as f:
        data = json.load(f)
    # patch.json / tips.json は直接読み込む（データ取得をやり直さず反映できる）
    if os.path.exists("patch.json"):
        with open("patch.json", encoding="utf-8") as f:
            data["patch"] = json.load(f)
    if os.path.exists("tips.json"):
        with open("tips.json", encoding="utf-8") as f:
            data["tips"] = json.load(f)
    if os.path.exists("toplayers.json"):
        with open("toplayers.json", encoding="utf-8") as f:
            data["toplayers"] = json.load(f)
    if os.path.exists("matchups.json"):
        with open("matchups.json", encoding="utf-8") as f:
            data["matchups"] = json.load(f)
    if os.path.exists("playstyle.json"):
        with open("playstyle.json", encoding="utf-8") as f:
            data["playstyle"] = json.load(f)
    if os.path.exists("trending.json"):
        with open("trending.json", encoding="utf-8") as f:
            data["trending"] = json.load(f)
    beginner_data = {}
    if os.path.exists("beginner.json"):
        with open("beginner.json", encoding="utf-8") as f:
            beginner_data = json.load(f)
    rule_picks = {}
    if os.path.exists("rule_picks.json"):
        with open("rule_picks.json", encoding="utf-8") as f:
            rule_picks = json.load(f)
    meta_report = {}
    if os.path.exists("meta_report.json"):
        with open("meta_report.json", encoding="utf-8") as f:
            meta_report = json.load(f)
    shindan_content = {}
    if os.path.exists("shindan_content.json"):
        with open("shindan_content.json", encoding="utf-8") as f:
            shindan_content = json.load(f)
    if os.path.exists("x_borders.json"):
        with open("x_borders.json", encoding="utf-8") as f:
            x_borders = json.load(f)
    else:
        x_borders = {}
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(build(data))
    for asset in ("style.css", "app.js"):
        if os.path.exists(asset):
            with open(asset, encoding="utf-8") as src, \
                 open(os.path.join(OUT_DIR, asset), "w", encoding="utf-8") as dst:
                dst.write(src.read())

    # ブキ個別ページ生成
    patch = data.get("patch", {}) or {}
    patch_weapons = patch.get("weapons", {}) or {}
    tips = data.get("tips") or {}
    weapons = collect_weapons(data)
    all_weapons = [info["meta"] for info in weapons.values()]
    weapon_index = build_weapon_index(data)
    toplayers = data.get("toplayers")
    wp_dir = os.path.join(OUT_DIR, "weapon")
    os.makedirs(wp_dir, exist_ok=True)
    slugs, used = [], set()
    for name, info in weapons.items():
        slug = weapon_slug(info["meta"])
        if slug in used:
            slug = f"{slug}-{len(used)}"
        used.add(slug)
        slugs.append(slug)
        with open(os.path.join(wp_dir, f"{slug}.html"), "w", encoding="utf-8") as f:
            f.write(render_weapon_page(name, info, data, patch_weapons, tips, all_weapons, toplayers))

    # 戦闘タイプ診断ページ
    with open(os.path.join(OUT_DIR, "shindan.html"), "w", encoding="utf-8") as f:
        f.write(render_shindan(all_weapons, shindan_content))

    extra_pages = ["tier.html", "shindan.html"]
    if x_borders.get("rules"):
        html = render_border_page(x_borders)
        if html:
            with open(os.path.join(OUT_DIR, "border.html"), "w", encoding="utf-8") as f:
                f.write(html)
            extra_pages.append("border.html")
    if beginner_data:
        html = render_beginner_page(beginner_data, weapon_index)
        if html:
            with open(os.path.join(OUT_DIR, "beginner.html"), "w", encoding="utf-8") as f:
                f.write(html)
            extra_pages.append("beginner.html")
    if rule_picks.get("rules"):
        html = render_rules_page(rule_picks, weapon_index)
        if html:
            with open(os.path.join(OUT_DIR, "rules.html"), "w", encoding="utf-8") as f:
                f.write(html)
            extra_pages.append("rules.html")
    if meta_report.get("summary"):
        html = render_meta_report(meta_report, weapon_index)
        if html:
            with open(os.path.join(OUT_DIR, "report.html"), "w", encoding="utf-8") as f:
                f.write(html)
            extra_pages.append("report.html")

    # 最強tier表ページ（Xマッチ総合）
    first_mode = next(iter(data.get("modes", {}).values()), {})
    primary_overall = first_mode.get("rules", {}).get("overall", [])
    with open(os.path.join(OUT_DIR, "tier.html"), "w", encoding="utf-8") as f:
        f.write(render_tierlist(primary_overall, data))

    # sitemap.xml / robots.txt
    with open(os.path.join(OUT_DIR, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(write_sitemap(slugs, extra_pages))
    with open(os.path.join(OUT_DIR, "robots.txt"), "w", encoding="utf-8") as f:
        f.write(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}sitemap.xml\n")

    print(f"{OUT_DIR}/index.html と ブキ個別ページ {len(slugs)}件 を生成しました。")


if __name__ == "__main__":
    main()
