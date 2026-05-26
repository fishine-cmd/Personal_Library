# PDF 识别结果内嵌到编辑页 · 设计文档

- 日期：2026-05-26
- 作者：与 Claude 协作
- 影响范围：`app/templates/documents/edit.html`（前端）；后端 `/recognize_pdf` 接口契约不变

## 背景与目标

当前文献编辑页 `app/templates/documents/edit.html` 的 PDF 识别功能流程：

1. 顶部"识别 PDF · 导出 Markdown"大按钮 → 打开 Bootstrap modal
2. modal 内上传 PDF → POST `/recognize_pdf` → 返回的 markdown 渲染到 `<pre>` 标签
3. 用户在弹窗里复制 / 下载，然后**手动关闭弹窗**回到表单继续填写

问题：

- markdown 局限在弹窗内，用户复制后弹窗就关了，**无法边看 markdown 边填表单**
- 后端 `/recognize_pdf` 同时返回的 `suggested_fields`（结构化字段：标题、作者、摘要、关键词、DOI、年份、来源、单位、邮箱）**前端完全没用**，识别成本浪费

目标：

- markdown 识别结果直接呈现在编辑页上，便于复制、对照填表
- 利用后端已经提供的 `suggested_fields`，提供"一键填入字段"能力
- 改动只限于一个模板文件，后端契约不动
- 不破坏现有的"作者同名消歧"和 autocomplete 功能

## 用户故事

1. 用户在编辑页点击右上角的小图标按钮 → 浏览器原生文件选择器弹出
2. 用户选好 PDF → 编辑页右侧分栏自动出现，显示"解析中"
3. 识别完成后右栏切到结果态，展示 markdown 内容 + 4 个动作按钮（一键填入字段 / 复制 / 下载 / 关闭）
4. 用户可以一边看右栏 markdown，一边在左侧表单里手工填字段
5. 或者直接点"一键填入字段"，把后端识别出来的标题、作者、摘要等灌入表单（若已有内容则弹覆盖确认）
6. 用户点"×"关闭右栏 → 表单恢复满宽；再点小按钮 → 直接回到上次的识别结果（不重新上传）

## 布局设计（B2 方案）

### 容器结构

替换 `edit.html` 当前的单栏布局：

```html
<div class="row">
  <div class="col-lg-12" id="edit-form-col">
    <form method="post" enctype="multipart/form-data" class="row g-3">
      <!-- 现有表单字段全部保留 -->
    </form>
  </div>
  <div class="col-lg-4 d-none" id="recognize-pane">
    <!-- 上传态 / 加载态 / 结果态 / 错误态 -->
  </div>
</div>
```

### 响应式行为

| 屏幕宽度 | 右栏隐藏 | 右栏展开 |
|---|---|---|
| ≥992px（桌面） | 表单 `col-lg-12` 占满 | 表单 `col-lg-8`，右栏 `col-lg-4` 在右侧；右栏内部 `position: sticky; top: 70px` |
| <992px（窄屏） | 表单 `col-12` 占满 | 表单 `col-12`，右栏 `col-12` 堆叠到表单**下方**；不强制两栏 |

Bootstrap 5 的 `col-lg-*` 在 lg 以下自动堆叠成单列，无需额外媒体查询。

### 顶部按钮替换

把第 4-9 行的大按钮替换成右上角小图标按钮：

```html
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4 class="mb-0">{% if doc %}编辑文献{% else %}新增文献{% endif %}</h4>
  <button type="button" class="btn btn-sm btn-outline-primary" id="btn-recognize-toggle"
          title="识别 PDF · 导出 Markdown">
    <i class="bi bi-magic"></i>
  </button>
</div>
```

### 右栏四种状态

通过 `d-none` 切换四个子 DOM：

| 态 | id | 内容 |
|---|---|---|
| 上传态 | `#rp-upload` | 提示文字"请选择 PDF 文件"+ "选择文件"按钮（点了再次触发隐藏 file input）+ 右上角 × 关闭 |
| 加载态 | `#rp-loading` | spinner + "正在解析 PDF（数十秒到数分钟，请勿关闭页面）..." |
| 结果态 | `#rp-result` | 顶栏：文件名 + 字符数 + 动作按钮（一键填入字段 / 复制 / 下载 / 识别新 PDF / ×）；下方：`<pre>` 渲染 markdown（`max-height: calc(100vh - 200px); overflow: auto; white-space: pre-wrap`） |
| 错误态 | `#rp-error` | 红色 alert + 错误详情 + 重试按钮（回到上传态） |

页面任意位置（建议右栏外部）挂一个隐藏的 file input：

```html
<input type="file" id="recognize-file-hidden" accept="application/pdf" class="d-none">
```

## 前端逻辑

### 状态机

```
[初始：右栏隐藏，无数据]
   │ 点击右上角小按钮（首次）
   ▼
[右栏展开 = 上传态] ── 自动触发 fileInput.click() ──┐
   │                                                 │
   │ 文件选择器 → 取消                                │ 选中 PDF
   │ (停在上传态)                                     ▼
   └───────────────────────────────────────────► [加载态] ── fetch /recognize_pdf
                                                    │
                                  成功 ────────────┴──────── 失败
                                  ▼                          ▼
                              [结果态]                  [错误态]
                                  │                          │ 重试
                                  ├─ 复制 → clipboard         └──→ [上传态]
                                  ├─ 下载 → Blob a.download
                                  ├─ 一键填入 → fillFormFromSuggested()
                                  ├─ 识别新 PDF → 回 [上传态]
                                  └─ × 关闭 → 右栏 d-none，但保留数据
```

### 数据持久化策略

- markdown 字符串 + `suggested_fields` 对象存在 IIFE 闭包变量里：`let lastMarkdown = ''`, `let lastSuggested = null`, `let lastFilename = ''`
- 关闭右栏（×）只是隐藏 DOM，**不清空闭包变量**
- 再次点小按钮：若有 `lastMarkdown` → 直接进入结果态，不重新触发文件选择器
- "识别新 PDF" 按钮：清空闭包变量 + 触发 `fileInput.click()`
- **刷新页面则数据丢失**：不写 `localStorage`，避免和后端会话脱节

### 小按钮的 toggle 行为

```js
btnToggle.addEventListener('click', () => {
  if (paneVisible) {
    hidePane();   // 右栏已开 → 关闭
  } else {
    showPane();   // 右栏未开 → 展开
    if (lastMarkdown) {
      showResultState();   // 有缓存 → 直接显示结果
    } else {
      showUploadState();
      fileInput.click();   // 无缓存 → 触发文件选择器
    }
  }
});
```

### `/recognize_pdf` 请求处理

复用现有 modal 的请求/错误判别逻辑，搬到右栏：

- 网络失败 / fetch reject → 错误态显示 `请求失败：${e}`
- HTTP 404 → "该接口未注册 —— 你跑的可能是旧 exe，或没装新依赖"
- HTTP 401 / 302 → "登录会话可能已失效，请刷新页面重新登录"
- HTTP 413 → "PDF 文件超过大小限制（默认 50MB）"
- HTTP 5xx → "服务器内部错误，请查看 Flask 终端输出"
- 响应不是 JSON → 折叠展示原始响应前 500 字符
- `j.ok === false` → 错误态显示 `j.error`
- `j.ok === true` → 结果态，缓存 `j.markdown` / `j.suggested_fields` / `j.filename`

## 一键填入字段

### 字段映射

| `suggested_fields` 键 | 表单 `name` | 写入规则 |
|---|---|---|
| `title` (string) | `title` (input) | 直接 `value =` |
| `year` (int 或 null) | `publication_year` (input) | 若非 null `value =`，null 时跳过 |
| `doi` (string) | `doi` (input) | 直接 `value =` |
| `source` (string) | `source_name` (input) | 直接 `value =`（不动 `source_type`，保持用户原选择） |
| `abstract` (string) | `abstract` (textarea) | 直接 `value =` |
| `keywords` (array) | `keywords_raw` (input) | `.join(', ')` 后写入 |
| `authors` + `affiliations` (arrays) | `authors_raw` (textarea) | 见下 |
| `emails` (array) | — | 不映射（表单无对应字段），仅在 markdown 中可见 |

### 作者拼装规则

生成符合 `authors_raw` 多行格式（每行 `姓名 | 单位1; 单位2`，单位可选）的字符串：

```js
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
```

规则要点：

- `authors.length === affiliations.length` → 一一对应
- 长度不等或 `affiliations` 为空 → 每行只写姓名，不带 `|`
- **不自动加 `#编号`**：交给现有"作者同名消歧"面板处理

### 覆盖确认

`fillFormFromSuggested(s)` 在写入前先扫描所有目标字段：

```js
function fillFormFromSuggested(s) {
  const conflicts = [];   // [{label, name, oldValue, newValue}, ...]
  // 对每个映射目标做对比；目标字段当前非空且 newValue 也非空 → 记入 conflicts

  if (conflicts.length === 0) {
    applyAll(s);
    return;
  }

  const msg = '以下字段已有内容，是否覆盖？\n\n' +
    conflicts.map(c => `• ${c.label}`).join('\n') +
    '\n\n点"确定"将覆盖全部上述字段。';

  if (confirm(msg)) {
    applyAll(s);
  }
}
```

- 全空 → 直接全部填入，不弹窗
- 有冲突 → 一次性列出所有冲突字段名，用户选择覆盖或取消
- 不做"逐字段单独确认"——避免 UX 碎裂

### 触发同名消歧刷新

写完 `authors_raw` 后手动 dispatch 一次 `input` 事件：

```js
const ta = document.getElementById('authors-raw');
ta.value = packAuthors(s.authors, s.affiliations);
ta.dispatchEvent(new Event('input', { bubbles: true }));
```

让现有的"作者同名消歧"IIFE（`setupAuthorConflicts`）自动跑刷新逻辑。

## 后端

**完全不动。**

`/recognize_pdf` 当前返回的 JSON 结构 `{ ok, filename, suggested_fields: {...}, markdown }` 已经完美匹配前端需求。`_build_combined_markdown` 拼出来的 markdown 当作纯文本贴在前端 `<pre>` 标签里，渲染效果与现状一致。

## 文件改动清单

只动一个文件：`app/templates/documents/edit.html`

| 操作 | 行号 | 内容 |
|---|---|---|
| 修改 | 4-9 | 顶部 header：大按钮 → 小图标按钮 |
| 新增 | 11 前 | `<div class="row"><div class="col-lg-12" id="edit-form-col">` 包住 `<form>` |
| 新增 | 129 后 | 闭合 `</div>`，加同级 `<div class="col-lg-4 d-none" id="recognize-pane">...</div>`，再闭合外层 `</div>` |
| 新增 | （随便位置） | 隐藏 file input `<input id="recognize-file-hidden">` |
| 删除 | 135-167 | 旧 modal `<div id="recognizeModal">...</div>` 全部 |
| 删除 | 294-402 | 旧 "PDF recognition" IIFE 全部 |
| 新增 | 在删除位置 | 新的"右栏状态机 + 一键填入"IIFE |
| 保留 | 170-178 | autocomplete datalists — 完全不碰 |
| 保留 | 180-291 | 作者同名消歧 IIFE — 完全不碰 |

## 测试策略

### 自动化测试

- **前端无单测**：纯 DOM 交互、闭包状态机，单测成本高、收益低，跳过
- **后端**：`/recognize_pdf` 路由契约不变，若已有相关测试会保持通过；不新增测试

### 手动验证清单

实施完成后必须按顺序跑一遍：

1. 进入编辑页 → 看到右上角小按钮
2. 点小按钮 → 文件选择器弹出，右栏出现并处于上传态
3. 选 PDF → 自动进入加载态，spinner 转动
4. 识别完成 → 右栏切到结果态，显示文件名 + 字符数 + markdown 内容
5. 点"复制" → 剪贴板中粘出来正确，按钮短暂变"已复制"
6. 点"下载" → 浏览器下载 `<pdf名>.md`，内容正确
7. 表单全空时点"一键填入字段" → 无弹窗，所有字段直接被填入；作者消歧面板自动刷新
8. 表单已有"标题/摘要"时点"一键填入字段" → 弹覆盖确认列出所有冲突项；点取消则什么都不变；点确定则全部覆盖
9. 点"×"关闭 → 右栏隐藏，表单恢复满宽
10. 再点小按钮 → 直接回到上次结果态（不重新弹文件选择器）
11. 点"识别新 PDF" → 文件选择器再次弹出，旧数据被清空
12. 文件选择器里直接按取消 → 停在上传态，可再次触发
13. 缩窗口到 <992px → 右栏堆到表单下方
14. 停掉 MinerU 服务再识别 → 错误态显示 502 错误 + "重试"按钮可用
15. 上传非 PDF 文件 → 后端返回错误，错误态显示
16. 上传超过 50MB 的 PDF → 错误态显示 413 提示

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| 用户在长 PDF 识别期间手动改了表单，"一键填入"时覆盖确认把刚改的内容也覆盖掉 | 覆盖确认列出**全部**非空字段，让用户看清楚再决定；用户可选取消 |
| `position: sticky` 在老版 Safari 不生效 | 退化为静态定位，不影响功能 |
| markdown 内容极长（数万字符）`<pre>` 渲染卡顿 | `max-height` + `overflow:auto`，浏览器只渲染可见部分；测试时跑一份 100k 字符的 markdown 验证 |
| 用户期望小按钮是"开关"而不是"上传入口" | 小按钮做成 toggle：右栏已开则关闭右栏；右栏未开则展开（有缓存进结果态，无缓存进上传态并弹文件选择器） |
| 现有 `suggested_fields.authors` 格式不适配 `authors_raw` textarea | `packAuthors` 函数做格式转换；若实施后发现作者识别质量不佳，可在覆盖确认前提示用户"作者识别可能不准，建议人工核对" |

## 验收标准

- 旧 modal 弹窗不再存在
- 编辑页右上角有小图标按钮，点击触发完整识别流程
- markdown 识别结果在右栏可见、可复制、可下载
- "一键填入字段"按预期映射所有字段并处理冲突
- 不破坏作者同名消歧和 autocomplete
- 窄屏下不出现横向滚动条
- 手动验证清单全部通过

## 不在本次范围内

- markdown 的语法高亮渲染（仍是 `<pre>` 纯文本）
- 多 PDF 批量识别
- 后端 `/recognize_pdf` 的接口契约调整
- `suggested_fields` 的提取算法改进（在 `app/services/pdf_metadata.py`，与本次 UI 改动无关）
- 移动端的特殊优化（窄屏堆叠已够用）
