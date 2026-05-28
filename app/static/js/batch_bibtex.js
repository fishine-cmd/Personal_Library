/* Batch PDF recognition + batch BibTeX import state machine. */
(function () {
  "use strict";

  const MAX_FILES = 20;
  const LS_PREFIX = "batchbib:v1:";
  const LS_TTL_MS = 7 * 24 * 60 * 60 * 1000;
  const DRAFT_DEBOUNCE_MS = 500;

  const root = document.getElementById("batch-app");
  if (!root) return;
  const RECOGNIZE_URL = root.dataset.recognizeUrl;
  const IMPORT_URL = root.dataset.importUrl;
  const NEXT_DOC_ID = Math.max(parseInt(root.dataset.nextDocId || "1", 10) || 1, 1);
  let nextDocKey = NEXT_DOC_ID;
  let supportedTypes = ["article"];
  try {
    const parsed = JSON.parse(root.dataset.supportedTypes || "[]");
    if (Array.isArray(parsed) && parsed.length > 0) {
      supportedTypes = parsed.map((t) => String(t || "").toLowerCase()).filter(Boolean);
    }
  } catch (e) {
    // keep default
  }

  const els = {
    empty: document.getElementById("state-empty"),
    working: document.getElementById("state-working"),
    input: document.getElementById("pdf-input"),
    pickBtn: document.getElementById("pick-files-btn"),
    list: document.getElementById("file-list"),
    count: document.getElementById("file-count"),
    retryBtn: document.getElementById("retry-failed-btn"),
    submitBtn: document.getElementById("submit-all-btn"),
    emptyPane: document.getElementById("empty-pane"),
    splitPane: document.getElementById("split-pane"),
    mdFilename: document.getElementById("md-filename"),
    mdStatus: document.getElementById("md-status"),
    mdRender: document.getElementById("md-render"),
    bibInput: document.getElementById("bib-input"),
    bibFeedback: document.getElementById("bib-feedback"),
    summary: document.getElementById("result-summary"),
    defaultCategory: document.getElementById("default-category"),
  };

  const items = [];
  let activeIdx = null;
  let queueBusy = false;

  function buildBibTemplate(seq, entryType = supportedTypes[0] || "article") {
    return `@${entryType}{doc${seq},
  abstract = {},
  author = {},
  doi = {},
  number = {},
  pages = {},
  publisher = {},
  title = {},
  volume = {},
  year = {}
}`;
  }

  function detectBibTypeTag(text) {
    const m = String(text || "").trim().match(/^@(\w+)\s*\{/m);
    if (!m) return `@${supportedTypes[0] || "article"}`;
    return `@${m[1].toLowerCase()}`;
  }

  function allTypeHintsHtml() {
    const tags = supportedTypes.map((t) => `@${t}`);
    return tags.map((t) => `<code>${escapeHtml(t)}</code>`).join("、");
  }

  function hashId(file) {
    return `${file.name}|${file.size}|${file.lastModified}`;
  }

  function lsKey(id) {
    return LS_PREFIX + id;
  }

  function loadDraft(id) {
    try {
      const raw = localStorage.getItem(lsKey(id));
      if (!raw) return "";
      const obj = JSON.parse(raw);
      if (Date.now() - obj.ts > LS_TTL_MS) {
        localStorage.removeItem(lsKey(id));
        return "";
      }
      return obj.text || "";
    } catch (e) {
      return "";
    }
  }

  function saveDraft(id, text) {
    try {
      localStorage.setItem(lsKey(id), JSON.stringify({ ts: Date.now(), text }));
    } catch (e) {
      console.warn("localStorage 草稿保存失败", e);
    }
  }

  function clearDraft(id) {
    try {
      localStorage.removeItem(lsKey(id));
    } catch (e) {
      // no-op
    }
  }

  function purgeOldDrafts() {
    try {
      for (let i = localStorage.length - 1; i >= 0; i--) {
        const k = localStorage.key(i);
        if (!k || !k.startsWith(LS_PREFIX)) continue;
        try {
          const obj = JSON.parse(localStorage.getItem(k));
          if (Date.now() - obj.ts > LS_TTL_MS) localStorage.removeItem(k);
        } catch (e) {
          localStorage.removeItem(k);
        }
      }
    } catch (e) {
      // no-op
    }
  }

  els.pickBtn.addEventListener("click", () => els.input.click());
  els.input.addEventListener("change", (e) => onFilesPicked(e.target.files));

  function onFilesPicked(fileList) {
    const files = Array.from(fileList).filter((f) =>
      f.name.toLowerCase().endsWith(".pdf")
    );
    if (files.length === 0) {
      alert("请选择 PDF 文件");
      return;
    }
    if (files.length > MAX_FILES) {
      alert(`单次最多 ${MAX_FILES} 篇，本次选了 ${files.length} 篇`);
      return;
    }
    purgeOldDrafts();

    for (const file of files) {
      const id = hashId(file);
      if (items.some((it) => it.id === id)) continue;
      const seq = nextDocKey++;
      const draft = loadDraft(id);
      items.push({
        id,
        seq,
        file,
        filename: file.name,
        status: "queued",
        markdown: null,
        bibText: draft || buildBibTemplate(seq),
        errorMsg: null,
        documentId: null,
      });
    }
    els.empty.classList.add("d-none");
    els.working.classList.remove("d-none");
    const restored = items.filter((it) => it.bibText.length > 0).length;
    if (restored > 0) {
      console.info(`已从本地草稿恢复 ${restored} 篇的 .bib 内容`);
    }
    renderList();
    pumpRecognizeQueue();
  }

  const STATUS_LABEL = {
    queued: { icon: "⌛", text: "排队中", cls: "text-muted" },
    recognizing: { icon: "⟳", text: "识别中", cls: "text-primary" },
    recognized: { icon: "✔", text: "待填写", cls: "text-success" },
    rec_failed: { icon: "✘", text: "识别失败", cls: "text-danger" },
    submitting: { icon: "⟳", text: "入库中", cls: "text-primary" },
    imported: { icon: "✓", text: "已入库", cls: "text-success" },
    import_failed: { icon: "✘", text: "入库失败", cls: "text-danger" },
    skipped: { icon: "⊘", text: "跳过", cls: "text-warning" },
  };

  function renderList() {
    els.count.textContent = String(items.length);
    els.list.innerHTML = "";
    items.forEach((it, idx) => {
      const li = document.createElement("li");
      li.className =
        "list-group-item list-group-item-action d-flex justify-content-between align-items-center";
      if (idx === activeIdx) li.classList.add("active");
      const status = STATUS_LABEL[it.status] || STATUS_LABEL.queued;
      li.innerHTML = `
        <span class="text-truncate" style="max-width: 70%" title="${escapeHtml(it.filename)}">${escapeHtml(it.filename)}</span>
        <span class="${status.cls}" title="${escapeHtml(it.errorMsg || status.text)}">${status.icon} ${status.text}</span>`;
      li.addEventListener("click", () => selectItem(idx));
      els.list.appendChild(li);
    });
    refreshButtons();
  }

  function refreshButtons() {
    const hasFailed = items.some((it) => it.status === "rec_failed");
    els.retryBtn.disabled = !hasFailed || queueBusy;
    const canSubmit = items.some(
      (it) => it.status === "recognized" && hasMeaningfulBibText(it)
    );
    els.submitBtn.disabled = !canSubmit || queueBusy;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[c]
    );
  }

  function hasMeaningfulBibText(it) {
    const text = (it.bibText || "").trim();
    if (!text) return false;
    return text !== buildBibTemplate(it.seq || 1).trim();
  }

  async function pumpRecognizeQueue() {
    if (queueBusy) return;
    const next = items.find((it) => it.status === "queued");
    if (!next) {
      renderList();
      return;
    }
    queueBusy = true;
    next.status = "recognizing";
    renderList();
    try {
      const form = new FormData();
      form.append("pdf", next.file, next.filename);
      const resp = await fetch(RECOGNIZE_URL, { method: "POST", body: form });
      const data = await resp.json();
      if (!resp.ok || !data.ok) {
        next.status = "rec_failed";
        next.errorMsg = data.error || `HTTP ${resp.status}`;
      } else {
        next.status = "recognized";
        next.markdown = data.markdown || "";
        next.errorMsg = null;
      }
    } catch (e) {
      next.status = "rec_failed";
      next.errorMsg = String(e);
    } finally {
      queueBusy = false;
      renderList();
      if (activeIdx !== null && items[activeIdx] === next) selectItem(activeIdx);
      pumpRecognizeQueue();
    }
  }

  function selectItem(idx) {
    activeIdx = idx;
    const it = items[idx];
    if (!it) return;
    renderList();
    els.emptyPane.classList.add("d-none");
    els.splitPane.classList.remove("d-none");
    els.mdFilename.textContent = it.filename;
    const status = STATUS_LABEL[it.status] || STATUS_LABEL.queued;
    els.mdStatus.textContent = `${status.icon} ${status.text}`;
    els.mdStatus.className = `badge bg-${status.cls.replace("text-", "")}`;

    if (
      it.status === "recognized" ||
      it.status === "imported" ||
      it.status === "import_failed"
    ) {
      renderMarkdown(it.markdown || "");
    } else if (it.status === "rec_failed") {
      els.mdRender.innerHTML = `<div class="alert alert-danger">${escapeHtml(
        it.errorMsg || "识别失败"
      )}</div>`;
    } else {
      els.mdRender.innerHTML = '<div class="text-muted">识别中…请稍候</div>';
    }
    els.bibInput.value = it.bibText || "";
    updateBibFeedback(it.bibText || "");
  }

  function renderMarkdown(md) {
    if (md.length > 200 * 1024) {
      els.mdRender.innerHTML = `<div class="alert alert-warning">原文过长（${(
        md.length / 1024
      ).toFixed(0)}KB），仅显示前 50KB</div><pre style="white-space: pre-wrap">${escapeHtml(
        md.slice(0, 50 * 1024)
      )}</pre>`;
      return;
    }
    try {
      els.mdRender.innerHTML = window.marked.parse(md);
    } catch (e) {
      els.mdRender.innerHTML = `<pre style="white-space: pre-wrap">${escapeHtml(
        md
      )}</pre>`;
    }
  }

  function updateBibFeedback(text) {
    const trimmed = text.trim();
    const typeTag = detectBibTypeTag(trimmed);
    const hintLine = `<span class="text-secondary">支持类型：${allTypeHintsHtml()}</span>`;
    if (!trimmed) {
      els.bibFeedback.innerHTML =
        `（未填写；提交时将跳过此篇）<br>${hintLine}`;
      els.bibFeedback.className = "small text-muted mt-2";
      return;
    }
    const matches = trimmed.match(/^@\w+\s*\{/gm) || [];
    if (matches.length === 0) {
      els.bibFeedback.innerHTML =
        `格式可疑：未发现 @type{ 开头<br>${hintLine}`;
      els.bibFeedback.className = "small text-danger mt-2";
    } else if (matches.length === 1) {
      els.bibFeedback.innerHTML = `已识别为 1 个条目（${matches[0].slice(
        0,
        -1
      )}）<br><span class="text-secondary">当前文献类型：<code>${escapeHtml(typeTag)}</code></span><br>${hintLine}`;
      els.bibFeedback.className = "small text-success mt-2";
    } else {
      els.bibFeedback.innerHTML = `检测到 ${matches.length} 个条目：该输入框只能填 1 个，提交时会被拒绝<br><span class="text-secondary">当前文献类型：<code>${escapeHtml(typeTag)}</code></span><br>${hintLine}`;
      els.bibFeedback.className = "small text-danger mt-2";
    }
  }

  let draftTimer = null;
  els.bibInput.addEventListener("input", () => {
    if (activeIdx === null) return;
    const it = items[activeIdx];
    it.bibText = els.bibInput.value;
    updateBibFeedback(it.bibText);
    clearTimeout(draftTimer);
    draftTimer = setTimeout(() => saveDraft(it.id, it.bibText), DRAFT_DEBOUNCE_MS);
    refreshButtons();
  });

  els.retryBtn.addEventListener("click", () => {
    items.forEach((it) => {
      if (it.status === "rec_failed") {
        it.status = "queued";
        it.errorMsg = null;
      }
    });
    renderList();
    pumpRecognizeQueue();
  });

  els.submitBtn.addEventListener("click", async () => {
    await runSubmitQueue();
  });

  async function runSubmitQueue() {
    queueBusy = true;
    refreshButtons();
    const categoryId = els.defaultCategory.value || "";
    let success = 0;
    let skipped = 0;
    let failed = 0;
    const failures = [];

    for (const it of items) {
      if (it.status === "imported") continue;
      if (it.status === "rec_failed") {
        it.status = "skipped";
        it.errorMsg = "识别未完成";
        skipped++;
        renderList();
        continue;
      }
      if (it.status !== "recognized" && it.status !== "import_failed") continue;
      if (!hasMeaningfulBibText(it)) {
        it.status = "skipped";
        it.errorMsg = "未填写 .bib";
        skipped++;
        renderList();
        continue;
      }

      it.status = "submitting";
      it.errorMsg = null;
      renderList();
      if (activeIdx !== null && items[activeIdx] === it) selectItem(activeIdx);

      try {
        const form = new FormData();
        form.append("pdf", it.file, it.filename);
        form.append("bib_text", it.bibText);
        if (categoryId) form.append("category_id", categoryId);
        const resp = await fetch(IMPORT_URL, { method: "POST", body: form });
        const data = await resp.json();
        if (resp.ok && data.ok) {
          it.status = "imported";
          it.documentId = data.document_id;
          it.errorMsg = null;
          clearDraft(it.id);
          success++;
        } else if (resp.ok && data.ok === false && data.reason === "duplicate") {
          it.status = "skipped";
          it.errorMsg = data.error_detail || "已存在";
          skipped++;
        } else if (resp.ok && data.ok === false && data.reason === "bib_empty") {
          it.status = "skipped";
          it.errorMsg = "未填写 .bib";
          skipped++;
        } else {
          it.status = "import_failed";
          it.errorMsg =
            data.error_detail || data.error || data.reason || `HTTP ${resp.status}`;
          failed++;
          failures.push({ filename: it.filename, reason: it.errorMsg });
        }
      } catch (e) {
        it.status = "import_failed";
        it.errorMsg = String(e);
        failed++;
        failures.push({ filename: it.filename, reason: String(e) });
      }
      renderList();
      if (activeIdx !== null && items[activeIdx] === it) selectItem(activeIdx);
    }

    queueBusy = false;
    renderList();
    showSummary(success, skipped, failed, failures);
  }

  function showSummary(success, skipped, failed, failures) {
    let html = `批量提交完成：<strong class="text-success">${success} 成功</strong>
                · <strong class="text-warning">${skipped} 跳过</strong>
                · <strong class="text-danger">${failed} 失败</strong>`;
    if (success > 0) {
      html += ` · <a href="/documents">查看文献库</a>`;
    }
    if (failures.length > 0) {
      html += '<ul class="mt-2 mb-0">';
      for (const f of failures) {
        html += `<li><code>${escapeHtml(f.filename)}</code>：${escapeHtml(
          f.reason
        )}</li>`;
      }
      html += "</ul>";
    }
    els.summary.innerHTML = html;
    els.summary.className =
      failed > 0 ? "alert alert-warning mt-3" : "alert alert-success mt-3";
    els.summary.classList.remove("d-none");
  }

  window.addEventListener("beforeunload", (e) => {
    const dirty = items.some(
      (it) =>
        (it.status === "recognized" ||
          it.status === "rec_failed" ||
          it.status === "import_failed") &&
        it.bibText.trim().length > 0
    );
    if (dirty) {
      e.preventDefault();
      e.returnValue = "未提交的内容已保存在本地草稿，确认离开？";
      return e.returnValue;
    }
  });

  purgeOldDrafts();

  (async function () {
    try {
      const resp = await fetch("/bibtex/batch/health");
      const data = await resp.json();
      if (!data.ok) {
        const banner = document.getElementById("mineru-banner");
        const msg = document.getElementById("mineru-banner-msg");
        if (banner && msg) {
          msg.textContent = `MinerU 未就绪：${data.error}（${data.url}）`;
          banner.classList.remove("d-none");
        }
        if (els.pickBtn) els.pickBtn.disabled = true;
      }
    } catch (e) {
      console.warn("health check 出错", e);
    }
  })();

  window.__batchApp = {
    items,
    els,
    selectItem,
    renderList,
    refreshButtons,
    clearDraft,
    MAX_FILES,
  };
})();
