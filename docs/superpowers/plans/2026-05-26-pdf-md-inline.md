# PDF 识别结果内嵌到编辑页 · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `app/templates/documents/edit.html` 的 PDF 识别 modal 改造为编辑页右侧分栏 + 一键填入字段，让 markdown 识别结果可见、可复制、可下载，并复用后端已返回的 `suggested_fields`。

**Architecture:** 仅修改一个模板文件。HTML 上新增右侧分栏（B2 方案：默认隐藏，点小按钮才展开）；JS 把旧的 modal IIFE 替换为新的"右栏状态机 + 字段自动填入"模块；后端 `/recognize_pdf` 接口契约完全不动。

**Tech Stack:** Flask + Jinja2 模板、Bootstrap 5（已通过 `base.html` 加载）、Bootstrap Icons（已可用，原代码用过 `bi-magic`）、原生 fetch / FormData / Clipboard API。

**Reference Spec:** [docs/superpowers/specs/2026-05-26-pdf-md-inline-design.md](../specs/2026-05-26-pdf-md-inline-design.md)

**关于测试：** 此次改动是纯模板 + DOM 交互，没有可单元测试的纯函数。验证靠 (a) 改完后让 Flask 跑起来，在浏览器手动点完整流程；(b) 关键点用 DevTools Console 观察。所有验证步骤会显式写在每个 Task 末尾。

**前置条件：** 工作目录 `D:\GitHub项目\Personal_Library`，分支 `fishine`。设计文档已提交（commit `909fe2e`）。开始前 `git status` 应为 clean。

---

## 文件结构

唯一改动文件：`app/templates/documents/edit.html`

修改前的关键定位锚点（按当前文件内容）：
- 顶部 header `<div class="d-flex justify-content-between...">` 在第 4-9 行
- `<form method="post" enctype="multipart/form-data" class="row g-3">` 在第 11 行
- `<datalist id="dl-sources"></datalist>` 在第 131 行
- `<datalist id="dl-publishers"></datalist>` 在第 132 行
- 旧 modal `<div class="modal fade" id="recognizeModal" ...>` 在第 135-167 行
- 旧 PDF 识别 IIFE `// PDF recognition - shows Markdown ...` 在第 294-402 行
- 作者同名消歧 IIFE `setupAuthorConflicts` 在第 180-291 行（**不动**）
- autocomplete datalists fetch 在第 170-178 行（**不动**）

---

## Task 1：替换顶部大按钮为右上角小按钮 + 隐藏 file input

**Files:**
- Modify: `app/templates/documents/edit.html`（替换 4-9 行的 header 块）

- [ ] **Step 1：替换顶部 header**

把当前的 4-9 行：

```html
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4 class="mb-0">{% if doc %}编辑文献{% else %}新增文献{% endif %}</h4>
  <button type="button" class="btn btn-outline-primary" data-bs-toggle="modal" data-bs-target="#recognizeModal">
    <i class="bi bi-magic"></i> 识别 PDF · 导出 Markdown
  </button>
</div>
```

替换为：

```html
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4 class="mb-0">{% if doc %}编辑文献{% else %}新增文献{% endif %}</h4>
  <button type="button" class="btn btn-sm btn-outline-primary" id="btn-recognize-toggle"
          title="识别 PDF · 导出 Markdown">
    <i class="bi bi-magic"></i> 识别 PDF
  </button>
</div>
<input type="file" id="recognize-file-hidden" accept="application/pdf" class="d-none">
```

**变化点：**
- `btn-outline-primary` → `btn-sm btn-outline-primary`（变小）
- 去掉 `data-bs-toggle="modal" data-bs-target="#recognizeModal"`（旧 modal 触发逻辑）
- 加上 `id="btn-recognize-toggle"`（新 JS 用）
- 文案 "识别 PDF · 导出 Markdown" → "识别 PDF"（节约横向空间）
- 紧接 header div 下方加一个隐藏 file input

- [ ] **Step 2：起 Flask 服务确认页面仍能渲染**

```bash
cd "D:\GitHub项目\Personal_Library"
./start.bat
```

打开任意一篇文献的编辑页（例如 `http://127.0.0.1:5000/documents/1/edit`），目测：
- 右上角看到一个**小一号**的"识别 PDF"按钮
- 点击按钮 → 旧 modal 依然能弹出（因为 modal HTML 此时还在；本步未连新 JS）

期望：页面正常渲染，控制台无报错。

- [ ] **Step 3：提交**

```bash
git add app/templates/documents/edit.html
git commit -m "refactor(edit): 顶部识别按钮改为右上角小按钮 + 加隐藏 file input"
```

---

## Task 2：把表单包进 row 容器，在右侧加一个空的 recognize-pane（先不写 JS）

**Files:**
- Modify: `app/templates/documents/edit.html`（包裹 `<form>`、移动 `<datalist>`、新增右栏 DOM）

- [ ] **Step 1：在 `<form>` 标签前插入 row 容器开标签**

定位到第 11 行 `<form method="post" enctype="multipart/form-data" class="row g-3">`，**在它之前**插入：

```html
<div class="row">
  <div class="col-lg-12" id="edit-form-col">
```

- [ ] **Step 2：在 `</form>` 闭合后关闭 col + 加右栏 + 关闭 row**

定位到 `<form>` 闭合 `</form>` 标签（目前在第 129 行的"取消"按钮 div 之后）。

**当前形态（关注 129-132 行附近）：**
```html
    <a class="btn btn-outline-secondary" href="{{ url_for('documents.list_documents') }}">取消</a>
  </div>
</form>

<datalist id="dl-sources"></datalist>
<datalist id="dl-publishers"></datalist>
```

**改为：**
```html
    <a class="btn btn-outline-secondary" href="{{ url_for('documents.list_documents') }}">取消</a>
  </div>
</form>

<datalist id="dl-sources"></datalist>
<datalist id="dl-publishers"></datalist>

  </div><!-- /#edit-form-col -->

  <div class="col-lg-4 d-none" id="recognize-pane">
    <div class="position-sticky" style="top: 70px;">
      <div class="card">
        <div class="card-body p-3" id="rp-body">
          <!-- 状态化内容将在 Task 3 中填充 -->
          <div class="text-muted small">（识别面板）</div>
        </div>
      </div>
    </div>
  </div>

</div><!-- /.row -->
```

**变化点：**
- datalists 留在 `#edit-form-col` 内（保持原作用域）
- `#edit-form-col` 关闭于 datalists 之后
- 同级新增 `#recognize-pane`（默认 `d-none`，桌面下占 `col-lg-4`）
- 最外层 `.row` 闭合

- [ ] **Step 3：DevTools 验证布局**

刷新页面，打开 DevTools（F12）的 Elements 面板，确认 DOM 结构是：
```
div.row
├── div.col-lg-12#edit-form-col
│   ├── form.row.g-3
│   ├── datalist#dl-sources
│   └── datalist#dl-publishers
└── div.col-lg-4.d-none#recognize-pane
    └── ...
```

页面外观应**完全不变**（右栏处于 `d-none`，表单仍占满）。

在 Console 跑一次手动测试，验证右栏切换的 class 操作能正确改变布局：
```js
document.getElementById('recognize-pane').classList.remove('d-none');
document.getElementById('edit-form-col').classList.replace('col-lg-12', 'col-lg-8');
```
此时右栏应该出现在右侧，左侧表单变窄。然后还原：
```js
document.getElementById('recognize-pane').classList.add('d-none');
document.getElementById('edit-form-col').classList.replace('col-lg-8', 'col-lg-12');
```

- [ ] **Step 4：提交**

```bash
git add app/templates/documents/edit.html
git commit -m "refactor(edit): 表单包进 row 容器, 右侧加 recognize-pane 骨架"
```

---

## Task 3：填充 recognize-pane 的四态 DOM

**Files:**
- Modify: `app/templates/documents/edit.html`（替换 `#rp-body` 内的占位 div）

- [ ] **Step 1：替换 `#rp-body` 内容为四态 DOM**

把 Task 2 里加的：
```html
<div class="card-body p-3" id="rp-body">
  <!-- 状态化内容将在 Task 3 中填充 -->
  <div class="text-muted small">（识别面板）</div>
</div>
```

改为：

```html
<div class="card-body p-3" id="rp-body">

  <!-- 上传态 -->
  <div id="rp-upload">
    <div class="d-flex justify-content-between align-items-center mb-2">
      <strong><i class="bi bi-magic"></i> 识别 PDF</strong>
      <button type="button" class="btn-close" id="rp-close-upload" aria-label="关闭"></button>
    </div>
    <div class="text-center py-4 border rounded bg-body-tertiary">
      <i class="bi bi-file-earmark-pdf fs-1 text-muted d-block mb-2"></i>
      <div class="mb-3 small text-muted">请选择一个 PDF 文件开始识别</div>
      <button type="button" class="btn btn-primary btn-sm" id="rp-btn-pick">选择文件</button>
    </div>
  </div>

  <!-- 加载态 -->
  <div id="rp-loading" class="d-none">
    <div class="d-flex justify-content-between align-items-center mb-2">
      <strong><i class="bi bi-magic"></i> 识别 PDF</strong>
    </div>
    <div class="alert alert-info py-3 mb-0 d-flex align-items-center">
      <div class="spinner-border spinner-border-sm me-2" role="status"></div>
      <div class="small">正在解析 PDF（数十秒到数分钟，请勿关闭页面）…</div>
    </div>
  </div>

  <!-- 结果态 -->
  <div id="rp-result" class="d-none">
    <div class="d-flex justify-content-between align-items-center mb-2 gap-2">
      <strong class="text-truncate" id="rp-filename" title=""></strong>
      <button type="button" class="btn-close flex-shrink-0" id="rp-close-result" aria-label="关闭"></button>
    </div>
    <div class="small text-muted mb-2" id="rp-charcount"></div>
    <div class="d-flex flex-wrap gap-1 mb-2">
      <button type="button" class="btn btn-sm btn-success" id="rp-btn-fill" title="把识别出的字段写入左侧表单">
        <i class="bi bi-magic"></i> 一键填入字段
      </button>
      <button type="button" class="btn btn-sm btn-outline-primary" id="rp-btn-copy">复制</button>
      <button type="button" class="btn btn-sm btn-outline-success" id="rp-btn-download">下载</button>
      <button type="button" class="btn btn-sm btn-outline-secondary" id="rp-btn-new-pdf">识别新 PDF</button>
    </div>
    <pre id="rp-markdown" class="small bg-body-tertiary text-body p-2 rounded border mb-0"
         style="max-height: calc(100vh - 280px); overflow:auto; white-space:pre-wrap;"></pre>
  </div>

  <!-- 错误态 -->
  <div id="rp-error" class="d-none">
    <div class="d-flex justify-content-between align-items-center mb-2">
      <strong class="text-danger">识别失败</strong>
    </div>
    <div class="alert alert-danger py-2 small" id="rp-error-body"></div>
    <button type="button" class="btn btn-sm btn-outline-primary" id="rp-btn-retry">重试</button>
  </div>

</div>
```

- [ ] **Step 2：手动让右栏显示，目测四态 UI**

刷新页面后在 Console 跑：
```js
// 显示右栏 + 上传态
document.getElementById('recognize-pane').classList.remove('d-none');
document.getElementById('edit-form-col').classList.replace('col-lg-12', 'col-lg-8');
```
目测：右栏出现在右侧，显示 PDF 图标 + "请选择一个 PDF 文件开始识别" + "选择文件" 按钮 + 右上角 ×。

然后逐个切换其他态目测：
```js
function show(id) {
  ['rp-upload','rp-loading','rp-result','rp-error'].forEach(x =>
    document.getElementById(x).classList.add('d-none'));
  document.getElementById(id).classList.remove('d-none');
}
show('rp-loading');   // spinner + 文案
show('rp-result');    // 但 markdown 是空的; 测试用:
document.getElementById('rp-filename').textContent = 'test.pdf';
document.getElementById('rp-charcount').textContent = '12,345 字符';
document.getElementById('rp-markdown').textContent = '# 测试\n\n内容...';
show('rp-error');
document.getElementById('rp-error-body').innerHTML = '测试错误信息';
```
确认 4 个状态都能正常显示且样式合理。

- [ ] **Step 3：恢复隐藏状态**

```js
document.getElementById('recognize-pane').classList.add('d-none');
document.getElementById('edit-form-col').classList.replace('col-lg-8', 'col-lg-12');
```

- [ ] **Step 4：提交**

```bash
git add app/templates/documents/edit.html
git commit -m "refactor(edit): recognize-pane 加入上传/加载/结果/错误四态 DOM"
```

---

## Task 4：新增右栏状态机 JS（与旧 modal 共存）

**Files:**
- Modify: `app/templates/documents/edit.html`（在 `<script>` 块内末尾、最外层 `}` 之前，加新 IIFE）

- [ ] **Step 1：在 script 块内、原 PDF recognition IIFE 之后插入新 IIFE**

定位到当前文件第 401-402 行附近：
```js
    });   // btnRecognize.addEventListener('click', ...) 闭合
  })();   // 旧 IIFE 闭合
</script>
```

在 `})();` 之后、`</script>` 之前，**插入下面这段完整新 IIFE**：

```js
// PDF recognition (NEW) — inline right pane, supports auto-fill.
(function() {
  const btnToggle = document.getElementById('btn-recognize-toggle');
  if (!btnToggle) return;   // 若按钮不存在（极端情况）直接退出

  const pane = document.getElementById('recognize-pane');
  const formCol = document.getElementById('edit-form-col');
  const fileInput = document.getElementById('recognize-file-hidden');

  const rpUpload = document.getElementById('rp-upload');
  const rpLoading = document.getElementById('rp-loading');
  const rpResult = document.getElementById('rp-result');
  const rpError = document.getElementById('rp-error');

  const btnPickFile = document.getElementById('rp-btn-pick');
  const btnCloseFromUpload = document.getElementById('rp-close-upload');
  const btnCloseFromResult = document.getElementById('rp-close-result');
  const btnCopy = document.getElementById('rp-btn-copy');
  const btnDownload = document.getElementById('rp-btn-download');
  const btnFill = document.getElementById('rp-btn-fill');
  const btnNewPdf = document.getElementById('rp-btn-new-pdf');
  const btnRetry = document.getElementById('rp-btn-retry');

  const elFilename = document.getElementById('rp-filename');
  const elCharcount = document.getElementById('rp-charcount');
  const elMarkdown = document.getElementById('rp-markdown');
  const elErrorBody = document.getElementById('rp-error-body');

  let lastMarkdown = '';
  let lastSuggested = null;
  let lastFilename = '';

  function showPane() {
    pane.classList.remove('d-none');
    formCol.classList.replace('col-lg-12', 'col-lg-8');
  }
  function hidePane() {
    pane.classList.add('d-none');
    formCol.classList.replace('col-lg-8', 'col-lg-12');
  }
  function isPaneVisible() {
    return !pane.classList.contains('d-none');
  }

  function setState(name) {
    [rpUpload, rpLoading, rpResult, rpError].forEach(el => el.classList.add('d-none'));
    ({ upload: rpUpload, loading: rpLoading, result: rpResult, error: rpError }[name]).classList.remove('d-none');
  }

  function showResultState() {
    elFilename.textContent = lastFilename;
    elFilename.title = lastFilename;
    elCharcount.textContent = `${lastMarkdown.length.toLocaleString()} 字符`;
    elMarkdown.textContent = lastMarkdown;
    setState('result');
  }
  function showErrorState(html) {
    elErrorBody.innerHTML = html;
    setState('error');
  }
  function clearData() {
    lastMarkdown = '';
    lastSuggested = null;
    lastFilename = '';
  }

  async function recognize(file) {
    setState('loading');
    const fd = new FormData();
    fd.append('pdf', file);
    try {
      const r = await fetch('{{ url_for("documents.recognize_pdf") }}', { method: 'POST', body: fd });
      const text = await r.text();
      let j;
      try {
        j = JSON.parse(text);
      } catch (parseErr) {
        let hint = '';
        if (r.status === 404) hint = '该接口未注册 —— 你跑的可能是旧 exe，或没装新依赖。';
        else if (r.status === 401 || r.status === 302) hint = '登录会话可能已失效，请刷新页面重新登录。';
        else if (r.status === 413) hint = 'PDF 文件超过大小限制（默认 50MB）。';
        else if (r.status >= 500) hint = '服务器内部错误，请查看 Flask 终端输出的 Python 报错。';
        else hint = `HTTP ${r.status}。`;
        showErrorState(`<strong>响应不是 JSON</strong><br>${hint}<br><details class="mt-2"><summary>原始响应（前 500 字符）</summary><pre class="small mt-1">${text.substring(0, 500).replace(/</g, '&lt;')}</pre></details>`);
        return;
      }
      if (!j.ok) {
        showErrorState(`识别失败：${j.error || '未知错误'}`);
        return;
      }
      lastMarkdown = j.markdown || '';
      lastSuggested = j.suggested_fields || null;
      lastFilename = j.filename || file.name || 'mineru.pdf';
      showResultState();
    } catch (e) {
      showErrorState(`请求失败：${e}`);
    }
  }

  fileInput.addEventListener('change', () => {
    if (!fileInput.files.length) return;
    const file = fileInput.files[0];
    recognize(file);
    fileInput.value = '';   // 允许下次重选同一文件
  });

  btnToggle.addEventListener('click', () => {
    if (isPaneVisible()) {
      hidePane();
      return;
    }
    showPane();
    if (lastMarkdown) {
      showResultState();
    } else {
      setState('upload');
      fileInput.click();
    }
  });

  btnPickFile.addEventListener('click', () => fileInput.click());
  btnCloseFromUpload.addEventListener('click', () => hidePane());
  btnCloseFromResult.addEventListener('click', () => hidePane());

  btnNewPdf.addEventListener('click', () => {
    clearData();
    setState('upload');
    fileInput.click();
  });

  btnRetry.addEventListener('click', () => {
    setState('upload');
    fileInput.click();
  });

  btnCopy.addEventListener('click', async () => {
    if (!lastMarkdown) return;
    try {
      await navigator.clipboard.writeText(lastMarkdown);
      const orig = btnCopy.textContent;
      btnCopy.textContent = '已复制';
      setTimeout(() => { btnCopy.textContent = orig; }, 1800);
    } catch (e) {
      showErrorState(`复制失败：${e}`);
    }
  });

  btnDownload.addEventListener('click', () => {
    if (!lastMarkdown) return;
    const base = (lastFilename || 'mineru').replace(/\.pdf$/i, '');
    const blob = new Blob([lastMarkdown], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `${base}.md`;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  });

  function packAuthors(authors, affiliations) {
    if (!authors || authors.length === 0) return '';
    const lines = [];
    for (let i = 0; i < authors.length; i++) {
      const name = authors[i];
      const aff = (affiliations && affiliations.length === authors.length)
        ? affiliations[i] : null;
      lines.push(aff ? `${name} | ${aff}` : name);
    }
    return lines.join('\n');
  }

  const FIELD_MAP = [
    { key: 'title',    label: '标题',    selector: 'input[name="title"]',            transform: v => (typeof v === 'string' ? v.trim() : '') },
    { key: 'year',     label: '出版年份', selector: 'input[name="publication_year"]', transform: v => (v == null || v === '' ? '' : String(v)) },
    { key: 'doi',      label: 'DOI',     selector: 'input[name="doi"]',              transform: v => (typeof v === 'string' ? v.trim() : '') },
    { key: 'source',   label: '来源',    selector: 'input[name="source_name"]',      transform: v => (typeof v === 'string' ? v.trim() : '') },
    { key: 'abstract', label: '摘要',    selector: 'textarea[name="abstract"]',      transform: v => (typeof v === 'string' ? v.trim() : '') },
    { key: 'keywords', label: '关键词',   selector: 'input[name="keywords_raw"]',     transform: v => (Array.isArray(v) ? v.join(', ') : '') },
  ];

  function fillFormFromSuggested(s) {
    if (!s) return;
    const writes = [];

    FIELD_MAP.forEach(m => {
      const el = document.querySelector(m.selector);
      if (!el) return;
      const newVal = m.transform(s[m.key]);
      if (!newVal) return;
      writes.push({ el, label: m.label, oldVal: el.value, newVal });
    });

    const authorsEl = document.getElementById('authors-raw');
    if (authorsEl) {
      const newAuthors = packAuthors(s.authors, s.affiliations);
      if (newAuthors) {
        writes.push({ el: authorsEl, label: '作者', oldVal: authorsEl.value, newVal: newAuthors, isAuthors: true });
      }
    }

    if (writes.length === 0) return;

    const conflicts = writes.filter(w => (w.oldVal || '').trim() !== '');
    if (conflicts.length > 0) {
      const msg = '以下字段已有内容，是否覆盖？\n\n' +
        conflicts.map(c => `• ${c.label}`).join('\n') +
        '\n\n点"确定"将覆盖全部上述字段。';
      if (!confirm(msg)) return;
    }

    writes.forEach(w => {
      w.el.value = w.newVal;
      if (w.isAuthors) {
        w.el.dispatchEvent(new Event('input', { bubbles: true }));
      }
    });
  }

  btnFill.addEventListener('click', () => {
    if (!lastSuggested) return;
    fillFormFromSuggested(lastSuggested);
  });
})();
```

**注意点：**
- `'{{ url_for("documents.recognize_pdf") }}'` 是 Jinja2 模板表达式，Flask 会在渲染时替换成真实路径，原 IIFE 用的就是这个，**保持一致**
- 新 IIFE 自包含，与旧 IIFE 互不干扰；两个识别入口此时并存

- [ ] **Step 2：浏览器端走通新流程（旧 modal 仍可用，但不点它）**

刷新编辑页（必须刷新，因为 JS 变了）：
1. 点击右上角小按钮 → 浏览器原生文件选择器应该弹出，右栏出现（处于上传态，但被文件选择器盖住）
2. 选一个真实可用的 PDF（小一点的，几页就行）→ 右栏切到加载态（spinner 转）
3. 等识别完成 → 右栏显示结果态：文件名、字符数、markdown 内容
4. 点"复制" → 按钮短暂变"已复制"；粘贴到记事本验证内容正确
5. 点"下载" → 浏览器下载 `<pdfname>.md`，打开内容正确
6. **测覆盖确认**：先在标题字段手动输入 "TEST"，然后点"一键填入字段"
   - 应该弹 `confirm()` 对话框列出"标题"
   - 点取消 → 标题保持 "TEST"
   - 再点一次"一键填入"，点确定 → 所有字段被覆盖填入
7. 点"识别新 PDF" → 文件选择器再弹，缓存清空
8. 点 × 关闭 → 右栏隐藏，表单恢复满宽
9. 再点小按钮（此时无缓存）→ 文件选择器再弹

如果 MinerU 服务未启动，第 2 步会进入错误态（HTTP 502），点"重试"应能回到上传态。

- [ ] **Step 3：DevTools Console 必须无报错**

打开 DevTools Console，刷新页面 + 完整跑一次流程，**整个过程不能有 `Uncaught` / `Error` 出现**（蓝色 info 和 fetch 请求记录不算）。

- [ ] **Step 4：提交**

```bash
git add app/templates/documents/edit.html
git commit -m "feat(edit): 新增右栏识别状态机 + 一键填入字段 JS"
```

---

## Task 5：删除旧 modal HTML

**Files:**
- Modify: `app/templates/documents/edit.html`（删除 modal 块）

- [ ] **Step 1：删除整个 `#recognizeModal` div**

定位（按当前位置；Task 1-4 没有改这部分）`<!-- Recognize PDF Modal -->` 注释及其下面的整个 `<div class="modal fade" id="recognizeModal" ...>...</div>`，**全部删除**：

要删除的内容形如（参考原 135-167 行）：
```html
<!-- Recognize PDF Modal -->
<div class="modal fade" id="recognizeModal" tabindex="-1" aria-hidden="true">
  <div class="modal-dialog modal-lg">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title"><i class="bi bi-magic"></i> 识别 PDF · 导出 Markdown</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
      </div>
      <div class="modal-body">
        ...（中间所有内容）...
      </div>
      <div class="modal-footer">
        ...（按钮组）...
      </div>
    </div>
  </div>
</div>
```

整段（从注释到 div 闭合）全部删除。

- [ ] **Step 2：刷新页面，确认无错**

刷新编辑页：
- 页面正常渲染
- 右上角小按钮仍可用
- Console 无报错（旧 modal 不再存在；旧 IIFE 引用旧 modal 的 DOM 时会在事件触发时报错，但本步骤未触发任何旧 IIFE 中的事件 —— 详见下一步）

- [ ] **Step 3：提交**

```bash
git add app/templates/documents/edit.html
git commit -m "refactor(edit): 删除旧的识别 PDF modal HTML"
```

---

## Task 6：删除旧 PDF recognition IIFE

**Files:**
- Modify: `app/templates/documents/edit.html`（删除旧 IIFE）

**为什么这一步单独：** 旧 IIFE 在文档加载时会 `getElementById('recognize-file')` 等取已不存在的 DOM 节点，紧接着调用 `.addEventListener('show.bs.modal', ...)` —— 因为 `recognize-file` 被删除（Task 5 已删整个 modal），`getElementById` 返回 `null`，再访问 `.addEventListener` 会抛 `TypeError`。所以删除旧 IIFE 是必要的清理。

- [ ] **Step 1：删除旧 PDF recognition IIFE**

定位 `// PDF recognition - shows Markdown, supports download / copy.` 这行注释及其下面的整个 IIFE：

```js
  // PDF recognition - shows Markdown, supports download / copy.
  (function() {
    const btnRecognize = document.getElementById('btn-recognize');
    ...
    });   // btnRecognize 的 click handler 闭合
  })();   // 整个 IIFE 闭合
```

从注释行开始到 `})();` 整段删除。

**保留这之前的所有内容：** autocomplete fetch、`setupAuthorConflicts` IIFE、**Task 4 加的新 IIFE**。

**双保险：** Task 4 加的新 IIFE 应该在旧 IIFE 之后；删除旧 IIFE 后，确保新 IIFE 还在 `<script>` 标签里，紧跟在 `setupAuthorConflicts` 之后。

- [ ] **Step 2：刷新页面，跑一次完整 smoke test**

```
1. 进入编辑页 → 无 Console 报错
2. 点小按钮 → 文件选择器弹出
3. 选 PDF → 识别 → 结果态显示
4. 复制 / 下载 / 一键填入 → 全部正常
5. 关闭 → 再开 → 缓存还在
6. "识别新 PDF" → 文件选择器再弹
```

- [ ] **Step 3：提交**

```bash
git add app/templates/documents/edit.html
git commit -m "refactor(edit): 删除旧 PDF recognition IIFE"
```

---

## Task 7：终极手动验证（按 spec 验收清单）

**Files:** 无修改，仅验证。

- [ ] **Step 1：跑完整验收清单**

需要前置条件：MinerU 服务起来，至少有一份测试 PDF 文件（首选已知能正常识别的那种学术论文）。

按顺序逐项打勾：

- [ ] 1. 进入编辑页 → 看到右上角小一号按钮"识别 PDF"
- [ ] 2. 点小按钮 → 文件选择器弹出，右栏出现并处于上传态
- [ ] 3. 选 PDF → 自动进入加载态，spinner 转动
- [ ] 4. 识别完成 → 右栏切到结果态，显示文件名 + 字符数 + markdown 内容
- [ ] 5. 点"复制" → 剪贴板内容正确（粘到记事本验证），按钮短暂变"已复制"
- [ ] 6. 点"下载" → 浏览器下载 `<pdf名>.md`，打开内容正确
- [ ] 7. **表单全空时**点"一键填入字段" → **无弹窗**，所有有数据的字段直接被填入；作者消歧面板自动刷新（如果有同名作者会出现卡片）
- [ ] 8. **表单已有内容时**：先在标题输入"X"，摘要输入"Y"，再点"一键填入字段" → 弹覆盖确认列出"标题、摘要"；点取消则保持"X""Y"；再点一次→点确定 → 全部覆盖
- [ ] 9. 点"×"关闭 → 右栏隐藏，表单恢复满宽
- [ ] 10. 再点小按钮 → 直接回到上次结果态（**不重新弹文件选择器**）
- [ ] 11. 点"识别新 PDF" → 文件选择器再次弹出，旧数据被清空
- [ ] 12. 文件选择器里直接按取消 → 停在上传态，可再次点"选择文件"
- [ ] 13. 缩窗口到 <992px → 右栏堆到表单**下方**（不再在右侧），无横向滚动条
- [ ] 14. 停掉 MinerU 服务再识别 → 错误态显示 502 错误 + "重试"按钮可用
- [ ] 15. 上传非 PDF 文件（比如 `.txt` —— 注意 file input 的 `accept` 会限制，但用户可手动改"All files"绕过）→ 后端返回错误，错误态显示"仅支持 PDF 文件"
- [ ] 16. 上传超过 50MB 的 PDF → 错误态显示 413 提示

- [ ] **Step 2：DevTools 全程无 Uncaught 错误**

刷新页面 + 跑完上面 16 项过程中，Console 不能出现任何 `Uncaught` / 红色 Error。

- [ ] **Step 3：如有问题就回到对应 Task 修复，没有就标记完成**

如果上面 16 项里某条不通过：
- 4-6 / 10：JS 状态机问题 → 回 Task 4 调
- 7-8：fillForm 逻辑问题 → 回 Task 4 调 `FIELD_MAP` 或 `packAuthors`
- 13：布局问题 → 回 Task 2 调 col 类名
- 14-16：错误态处理 → 回 Task 4 调 `recognize` 错误分支

修完再走完整 16 项。

- [ ] **Step 4：清理（如有）**

不需要清理。但可以在最后跑一次：
```bash
cd "D:\GitHub项目\Personal_Library"
git log --oneline -10
git status
```
确认 6 个 commit 都在分支上（Task 1-6 各一个 commit），工作树 clean。

- [ ] **Step 5：完成通知**

实施全部完成。可调用 `superpowers:finishing-a-development-branch` 决定后续合并/PR 策略。

---

## 自审清单（plan 作者用，非实施者用）

**Spec 覆盖：**
- ✅ 顶部小按钮替换 → Task 1
- ✅ 表单包进 row 容器 + 右栏 → Task 2
- ✅ 右栏四态 DOM → Task 3
- ✅ 状态机 JS / toggle / 文件选择器 / 闭包缓存 → Task 4
- ✅ fillFormFromSuggested + 覆盖确认 + 作者拼装 + 触发同名消歧刷新 → Task 4
- ✅ 复制 / 下载 → Task 4
- ✅ 删除旧 modal → Task 5
- ✅ 删除旧 IIFE → Task 6
- ✅ 错误态四种 HTTP 状态码处理 → Task 4 `recognize` 函数
- ✅ 窄屏堆叠 → Task 2（`col-lg-*` 默认行为，无需额外 CSS）
- ✅ 手动验证 16 项清单 → Task 7

**占位符扫描：** 无 TBD / TODO；每个代码步骤都给出完整代码。

**类型一致：** `btn-recognize-toggle`、`recognize-pane`、`edit-form-col`、`rp-upload`/`rp-loading`/`rp-result`/`rp-error`、`rp-btn-*` 这些 ID 在 HTML 和 JS 中拼写一致。`FIELD_MAP` 中 `name` 属性值与 `edit.html` 现有表单字段（`title` / `publication_year` / `doi` / `source_name` / `abstract` / `keywords_raw` / `authors_raw`）核对过，匹配。

**范围：** 6 个 task 都只动一个文件；每个 task 之间可独立 commit + 验证；任一中间状态页面都仍能渲染。
