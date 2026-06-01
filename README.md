# Personal Library

> 一个基于 Flask + MySQL + Bootstrap + pywebview 的个人文献管理系统。  
> 既可以作为本地 Web 应用运行，也可以打包成桌面程序分发。

---

## 1. 项目简介

`Personal Library` 用来统一管理论文、图书、报告等个人文献资料，当前版本已经不只是“录入书目信息”，而是扩展成了一套带有 PDF 解析、BibTeX 互通、字典治理、活动日志和桌面封装能力的个人知识库系统。

它主要解决这些事情：

1. 把文献基础信息、作者、关键词、来源、出版社、分类、阅读状态、评分和笔记统一存档。
2. 给文献挂载附件，支持 `pdf`、`doc`、`docx`、`txt`、`ps`、`epub`。
3. 通过 BibTeX 与其他学术工具互通。
4. 接入 MinerU 做 PDF 识别，并把识别结果转成 Markdown。
5. 用批量识别页完成“PDF + BibTeX”半自动入库。
6. 记录用户在系统中的活动，并生成 AI 日志 / 周札。
7. 支持 Web 运行和 Windows 桌面分发两种形态。

---

## 2. 当前版本重点能力

### 2.1 文献库

1. 文献新增、编辑、删除、详情页查看。
2. 按关键词、作者、摘要、DOI 搜索。
3. 按分类、文献类型、年份筛选。
4. 上传和下载附件，附件按用户分目录保存。
5. 作者支持重名区分，内部使用 `name + code` 机制消歧。

### 2.2 分类管理

1. 维护树状分类。
2. 支持父子分类。
3. 按父分类筛选时，会自动包含其所有子分类文献。

### 2.3 字典表治理

1. 维护作者、单位、出版社、来源等字典项。
2. 检测孤立项和潜在重复项。
3. 执行字典合并，并保留审计记录。
4. 支持按最近一次或指定审计记录回滚。

### 2.4 BibTeX 能力

1. 导入 `.bib` 文件或直接粘贴 BibTeX 文本。
2. 导出整个文献库或单篇文献的 BibTeX。
3. 导入时会按 `DOI` 或 `标题 + 年份` 做去重判断。
4. 当前内置支持的 BibTeX 类型包括：
   `article`、`inproceedings`、`conference`、`book`、`phdthesis`、`mastersthesis`、`techreport`、`misc`。

### 2.5 PDF 识别与批量入库

1. 单篇文献编辑页可直接调用 MinerU 识别 PDF。
2. 批量页支持一次拖入多篇 PDF，逐篇填写 `.bib` 后入库。
3. 批量入库时会把 PDF 作为附件保存，并保留识别出的 Markdown 结果供人工参考。
4. 设置页提供 MinerU 连通性测试。

### 2.6 屏幕 AI Agent 与日志

1. 页面右下角常驻 AI Agent，可记录系统内操作活动。
2. 可配置 OpenAI 兼容的 `chat completions` 接口，如 OpenAI、DeepSeek、Moonshot 或自建兼容服务。
3. 支持生成“今日日志”和“本周周札”。
4. 日志会保存到数据库，并以月历页方式展示。

### 2.7 桌面运行

1. `desktop_app.py` 使用 `pywebview` 将 Flask 嵌入原生窗口。
2. 首次运行弹出 MySQL 配置向导。
3. 配置保存到用户本地目录，之后可直接双击启动。

---

## 3. 技术栈与架构

### 3.1 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Flask 3、Flask-Login、Flask-SQLAlchemy |
| 数据库 | MySQL（测试使用 SQLite 内存库） |
| 前端 | Jinja2 模板、Bootstrap 5、少量原生 JavaScript |
| 文件处理 | `werkzeug`、本地文件系统 |
| BibTeX | `bibtexparser` |
| PDF 识别 | 外部 MinerU HTTP 服务 |
| 桌面封装 | `pywebview` + `PyInstaller` |
| AI 日志 | OpenAI 兼容 Chat Completions API |

### 3.2 当前架构分层

| 目录 / 文件 | 作用 |
|---|---|
| `run.py` | Web 开发模式入口 |
| `desktop_app.py` | 桌面模式入口 |
| `config.py` | 环境配置、上传限制、数据库连接 |
| `app/__init__.py` | 应用工厂、蓝图注册、启动初始化 |
| `app/models.py` | SQLAlchemy 模型定义 |
| `app/blueprints/` | 路由与页面控制层 |
| `app/services/` | 可复用业务逻辑，如 BibTeX、MinerU、字典治理、AI Agent |
| `app/templates/` | Jinja2 页面模板 |
| `app/static/` | CSS、JS、图片资源 |
| `tests/` | 自动化测试 |
| `docs/` | 补充文档、图示、协作说明 |

### 3.3 运行链路

最常见的请求链路如下：

```text
浏览器 / 桌面窗口
-> Flask Blueprint
-> Services
-> SQLAlchemy Models
-> MySQL
-> Jinja2 Template
-> HTML / CSS / JS
```

如果涉及 PDF 识别，则会额外经过：

```text
上传 PDF
-> app/blueprints/documents.py 或 batch_bibtex.py
-> app/services/mineru_client.py
-> MinerU HTTP API
-> Markdown / 结构化结果
-> 回填页面或批量导入流程
```

---

## 4. 快速开始

### 4.1 环境要求

建议准备以下环境：

1. Python `3.10` 到 `3.13`
2. MySQL `5.7+` 或 `8.x`
3. Windows + PowerShell
4. 可选：MinerU 服务
5. 可选：用于生成 AI 日志的 OpenAI 兼容接口

### 4.2 安装依赖

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 4.3 准备数据库

Web 开发模式下，程序会自动建表，但不会替你创建 MySQL 数据库本身，所以需要先准备一个数据库，例如：

```sql
CREATE DATABASE library_system CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 4.4 配置 `.env`

先复制示例文件：

```powershell
Copy-Item .env.example .env
```

示例内容如下：

```env
FLASK_SECRET_KEY=Please enter
DATABASE_URL=mysql+pymysql://root:PASSWORD@localhost:3306/library_system?charset=utf8mb4
UPLOAD_FOLDER=uploads
MAX_CONTENT_LENGTH=209715200
```

### 4.5 启动开发服务器

```powershell
python run.py
```

默认访问地址：

```text
http://127.0.0.1:5000
```

### 4.6 启动带 MinerU 的联调模式

如果本机已经安装并可直接调用 `mineru-api`，可以双击或执行：

```powershell
.\launch.bat
```

它会同时启动：

1. `start.bat` -> `python run.py`
2. `mineru.ps1` -> `mineru-api --host 127.0.0.1 --port 8000`

如果你没有安装 MinerU，也可以先只启动主应用；只是 PDF 识别、批量识别相关功能会不可用。

---

## 5. 配置说明

### 5.1 环境变量

| 变量 | 说明 |
|---|---|
| `FLASK_SECRET_KEY` | Flask Session / Cookie 签名密钥 |
| `DATABASE_URL` | SQLAlchemy 使用的 MySQL 连接串 |
| `UPLOAD_FOLDER` | 开发模式下附件保存目录 |
| `MAX_CONTENT_LENGTH` | 上传体积限制，默认 `209715200`（200 MB） |

### 5.2 用户级设置

登录后可在“设置”页配置两类内容：

1. `MinerU URL`
   用于单篇 PDF 识别和批量识别。
2. `AI Agent`
   包括昵称、启用状态、接口 URL、模型名、API Key。

注意：

1. AI Agent 的 API Key 保存后不会在页面回显明文。
2. AI 日志功能依赖一个兼容 `/v1/chat/completions` 风格的接口。

---

## 6. 功能使用说明

### 6.1 账号体系

1. 用户注册后会直接登录。
2. 所有文献、分类、字典项、日志和设置都按用户隔离。

### 6.2 文献录入

文献新增 / 编辑页可以维护：

1. 标题、摘要、文献类型、年份、卷期页码、DOI
2. 来源与出版社
3. 作者与作者单位
4. 关键词
5. 阅读状态、评分、笔记
6. 一个或多个附件

### 6.3 作者重名消歧

系统内部对同名作者使用递增 `code` 区分，例如同名作者会被表示为不同的内部记录。  
表单录入时也会先做去重，避免同一作者在单篇文献中被重复挂载。

### 6.4 字典治理

“字典表”页不是简单的列表页，而是一个小型数据治理入口，支持：

1. 检测孤立字典项
2. 查看潜在重复项
3. 执行合并
4. 查询审计记录
5. 按最近一次或指定记录回滚

### 6.5 BibTeX 与批量导入

系统包含两条工作流：

1. 常规导入导出
   面向已有 `.bib` 文件或剪贴板内容。
2. 批量 PDF + BibTeX 入库
   先识别 PDF，再人工补齐 / 修正 `.bib`，最后连同附件一起写入数据库。

### 6.6 AI 日志

当前代码中，以下操作会记录活动日志：

1. 注册、登录、退出
2. 文献创建、编辑、删除、下载附件、删除附件、识别 PDF
3. BibTeX 导入导出、批量导入
4. 字典清理、合并、回滚
5. 设置保存

日志生成后会保存到 `ai_agent_journals` 表，并在“日志”页以月历方式展示。

---

## 7. 项目结构总览

```text
Personal_Library/
├─ app/
│  ├─ blueprints/         # 路由层
│  ├─ services/           # 业务逻辑
│  ├─ static/             # 样式、脚本、图片
│  ├─ templates/          # 页面模板
│  ├─ __init__.py         # Flask 应用工厂
│  ├─ extensions.py       # db / login_manager
│  └─ models.py           # 数据模型
├─ docs/                  # 图示、协作开发说明等
├─ tests/                 # pytest 测试
├─ uploads/               # 开发模式默认附件目录
├─ config.py              # 配置
├─ run.py                 # Web 入口
├─ desktop_app.py         # 桌面入口
├─ launch.bat             # 同时启动应用与 MinerU
├─ mineru.ps1             # 启动 MinerU API
├─ build.ps1              # 桌面打包脚本
├─ library_system.spec    # PyInstaller 配置
└─ README.md
```

---

## 8. 开发与测试

### 8.1 测试命令

```powershell
pytest -q tests
```

### 8.2 当前测试覆盖的重点

1. 注册 / 登录流程
2. 文献 CRUD
3. 模型关系与 upsert 逻辑
4. BibTeX 解析、导入、导出
5. 附件保存与非法扩展名跳过
6. 批量 PDF + BibTeX 导入
7. AI Agent 配置、活动记录、日志生成和月历页展示

### 8.3 相关文档

1. `docs/协作开发指南.md`
   团队协作、分支和 PR 流程说明。
2. `docs/diagrams.md`
   数据结构和流程图补充说明。

---

## 9. 桌面打包与分发

### 9.1 安装打包依赖

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements-build.txt
```

### 9.2 打包方式

方式一：直接执行脚本

```powershell
.\build.ps1
```

方式二：手动执行

```powershell
pyinstaller library_system.spec --clean --noconfirm
```

### 9.3 首次运行流程

桌面版首次启动时：

1. 弹出 MySQL 配置向导
2. 填写主机、端口、用户名、密码、数据库名
3. 程序测试连接，并在需要时自动创建数据库
4. 配置写入本地用户目录
5. 随后启动嵌入式 Flask + pywebview 主窗口

### 9.4 桌面版本地数据位置

桌面模式下会使用用户本地目录：

1. 配置文件：`%APPDATA%\PersonalLibrary\config.json`
2. 附件目录：`%APPDATA%\PersonalLibrary\uploads`

### 9.5 分发注意事项

1. 打包产物不只是一个 `exe`，而是一整个目录。
2. 分发时应把 `dist/PersonalLibrary/` 整体发给用户。
3. MySQL 不会被打包进程序。
4. MinerU 也不会自动成为主程序的一部分，仍需用户自行准备服务。

---

## 10. 维护建议

如果后续还会继续迭代，这几个方向最值得在 README 之外持续补文档：

1. 为字典治理规则补充更明确的示例和边界说明。
2. 为批量导入页补充用户手册或录屏。
3. 为 AI Agent 接入补充不同服务商的配置样例。
4. 若未来引入迁移工具，补上正式的数据库迁移流程。

---

## 11. 说明

这份 README 已基于当前代码结构做过重新整理，重点从“逐文件解释”切换成了“先上手、再理解架构”。  
如果你是新开发者，推荐先按“快速开始”跑起来，再结合 `docs/协作开发指南.md` 和 `docs/diagrams.md` 继续深入。
