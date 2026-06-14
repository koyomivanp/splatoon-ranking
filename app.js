"use strict";

// モード切替（Xマッチ / バンカラ）
document.querySelectorAll(".mode-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const mode = btn.dataset.mode;
    document.querySelectorAll(".mode-btn").forEach((b) => b.classList.toggle("active", b === btn));
    document.querySelectorAll(".mode-block").forEach((block) => {
      block.style.display = block.dataset.mode === mode ? "" : "none";
    });
  });
});

// ルール切替（各モードブロック内でスコープ）
document.querySelectorAll(".mode-block").forEach((block) => {
  const tabs = block.querySelectorAll(".tab");
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const rule = tab.dataset.rule;
      tabs.forEach((t) => t.classList.toggle("active", t === tab));
      block.querySelectorAll(".ranking-panel").forEach((p) => {
        p.style.display = p.dataset.rule === rule ? "" : "none";
      });
    });
  });
});

// 検索・絞り込み（全テーブル横断で適用）
(function () {
  const searchBox = document.getElementById("searchBox");
  const catBtns = document.querySelectorAll(".cat-btn");
  const emptyMsg = document.getElementById("filterEmpty");
  if (!searchBox) return;

  let query = "";
  let cat = "";

  function apply() {
    const q = query.trim().toLowerCase();
    document.querySelectorAll(".ranking-table tbody").forEach((tbody) => {
      let visible = 0;
      tbody.querySelectorAll("tr").forEach((tr) => {
        const matchText = !q || (tr.dataset.search || "").includes(q);
        const matchCat = !cat || tr.dataset.cat === cat;
        const show = matchText && matchCat;
        tr.style.display = show ? "" : "none";
        if (show) visible++;
      });
    });
    // 表示中パネルが0件のときだけメッセージ
    const activePanel = document.querySelector(
      ".mode-block:not([style*='display: none']) .ranking-panel:not([style*='display: none'])"
    );
    let anyVisible = false;
    if (activePanel) {
      anyVisible = [...activePanel.querySelectorAll("tbody tr")].some(
        (tr) => tr.style.display !== "none"
      );
    }
    if (emptyMsg) emptyMsg.style.display = anyVisible ? "none" : "";
  }

  searchBox.addEventListener("input", () => {
    query = searchBox.value;
    apply();
  });
  catBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      cat = btn.dataset.cat;
      catBtns.forEach((b) => b.classList.toggle("active", b === btn));
      apply();
    });
  });
})();
