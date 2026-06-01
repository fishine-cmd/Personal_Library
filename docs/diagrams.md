# 数据库 E-R 图与数据流图

本文档使用 [Mermaid](https://mermaid.js.org/) 描述系统的实体关系（E-R）与数据流（DFD）。

**渲染方式（任选其一）**：
- VS Code 安装扩展 *Markdown Preview Mermaid Support* 后直接打开本文件
- 把代码块粘到在线渲染器 <https://mermaid.live> ，可导出 PNG/SVG
- GitHub / GitLab 网页查看 `.md` 文件会自动渲染

---

## 一、E-R 图（实体关系图）

数据库共 **16 张表**，严格满足第三范式（3NF）。下图覆盖全部实体、属性和关系。

- 关系基数符号：`||` 一，`o{` 多
- `PK` = 主键，`FK` = 外键，`UK` = 唯一键（含联合唯一键）

```mermaid
erDiagram
    USERS                ||--o{ DOCUMENTS          : "拥有"
    USERS                ||--o{ CATEGORIES         : "拥有"
    USERS                ||--o{ AUTHORS            : "拥有(per-user 字典)"
    USERS                ||--o{ AFFILIATIONS       : "拥有(per-user 字典)"
    USERS                ||--o{ KEYWORDS           : "拥有(per-user 字典)"
    USERS                ||--o{ TAGS               : "拥有(per-user 标签)"
    USERS                ||--o{ PUBLISHERS         : "拥有(per-user 字典)"
    USERS                ||--o{ SOURCES            : "拥有(per-user 字典)"
    USERS                ||--o{ AUTHOR_CODES       : "同名计数器"
    USERS                ||--o| USER_SETTINGS      : "1:0..1 用户配置"
    CATEGORIES           ||--o{ CATEGORIES         : "父子层级"
    CATEGORIES           ||--o{ DOCUMENTS          : "归类"
    PUBLISHERS           ||--o{ SOURCES            : "出版"
    SOURCES              ||--o{ DOCUMENTS          : "刊载"
    DOCUMENTS            ||--o{ DOCUMENT_AUTHORS   : ""
    AUTHORS              ||--o{ DOCUMENT_AUTHORS   : ""
    DOCUMENTS            ||--o{ DOCUMENT_KEYWORDS  : ""
    KEYWORDS             ||--o{ DOCUMENT_KEYWORDS  : ""
    DOCUMENTS            ||--o{ DOCUMENT_TAGS      : ""
    TAGS                 ||--o{ DOCUMENT_TAGS      : ""
    AUTHORS              ||--o{ AUTHOR_AFFILIATIONS: ""
    AFFILIATIONS         ||--o{ AUTHOR_AFFILIATIONS: ""
    DOCUMENTS            ||--o{ FILES              : "附件"

    USERS {
        int      id            PK
        varchar  username      UK
        varchar  password_hash
        varchar  email         UK
        datetime created_at
    }

    CATEGORIES {
        int      id         PK
        int      user_id    FK
        int      parent_id  FK
        varchar  name
        datetime created_at
    }

    PUBLISHERS {
        int     id       PK
        int     user_id  FK "UK(user_id,name)"
        varchar name
        varchar address
        varchar website
    }

    SOURCES {
        int     id           PK
        int     user_id      FK "UK(user_id,name,type)"
        varchar name
        enum    type         "journal/conference/book_series/other"
        int     publisher_id FK
        varchar issn
    }

    AFFILIATIONS {
        int     id       PK
        int     user_id  FK "UK(user_id,name)"
        varchar name
        varchar address
    }

    AUTHORS {
        int      id      PK
        int      user_id FK "UK(user_id,name,code)"
        varchar  name
        smallint code    "同名作者用 #1/#2/... 区分"
    }

    AUTHOR_CODES {
        int     user_id   PK_FK
        varchar name      PK
        smallint next_code "下一个可分配的 code"
    }

    AUTHOR_AFFILIATIONS {
        int author_id      PK_FK
        int affiliation_id PK_FK
    }

    KEYWORDS {
        int     id      PK
        int     user_id FK "UK(user_id,name)"
        varchar name
    }

    TAGS {
        int     id      PK
        int     user_id FK "UK(user_id,name)"
        varchar name
    }

    DOCUMENTS {
        int      id               PK
        int      user_id          FK
        int      category_id      FK
        int      source_id        FK
        varchar  title
        text     abstract
        enum     document_type    "journal_article/conference_paper/book/thesis/report/other"
        smallint publication_year
        varchar  volume
        varchar  issue
        varchar  pages
        varchar  doi
        text     notes
        smallint rating
        enum     reading_status   "unread/reading/read"
        datetime created_at
        datetime updated_at
    }

    DOCUMENT_AUTHORS {
        int      document_id  PK_FK
        int      author_id    PK_FK
        smallint author_order
    }

    DOCUMENT_KEYWORDS {
        int document_id PK_FK
        int keyword_id  PK_FK
    }

    DOCUMENT_TAGS {
        int document_id PK_FK
        int tag_id      PK_FK
    }

    USER_SETTINGS {
        int     user_id    PK_FK
        varchar mineru_url "PDF 解析服务地址"
    }

    FILES {
        int      id            PK
        int      document_id   FK
        varchar  file_path
        varchar  original_name
        int      file_size
        varchar  mime_type
        datetime uploaded_at
    }
```

### 3NF 验证要点

| 范式 | 怎么落地 |
|---|---|
| 1NF | 所有列原子化；作者/关键词/标签/单位都拆到独立表，不存逗号分隔字符串 |
| 2NF | 联合主键的中间表（如 `document_authors`）的非主键属性 `author_order` 完全依赖于整个联合主键 |
| 3NF | 比如出版社不直接放在文献表，而是 `documents → sources → publishers` 链式依赖；单位通过 `author_affiliations` 间接关联作者，消除传递依赖 |

### 关于 per-user 字典与同名作者编号

- **字典表和标签均带 `user_id`**：`authors / affiliations / publishers / sources / keywords / tags` 都按用户隔离，不会出现 A 用户改名波及 B 用户的情况；唯一约束都升级为联合 `(user_id, name [, type/code])`。
- **同名作者编号**：`authors` 增加 `code` 列，配合 `author_codes(user_id, name) → next_code` 计数器，让同一个用户库里多位"张三"以 `张三#1`、`张三#2` 等区分。表单录入走严格模式（同名必须显式选择 `#N` 或标记为新人）；BibTeX 批量导入走宽松模式（复用最低 `code`）。

---

## 二、数据流图（DFD）

### 顶层图（Context Diagram / Level 0）

系统作为一个整体，展示与外部实体的交互。

```mermaid
flowchart LR
    User((用户))
    System[/"个人文献管理系统<br/>(Flask 应用)"/]
    DB[("MySQL 数据库")]
    FS[("本地文件系统<br/>uploads/")]
    MinerU[/"MinerU 服务<br/>(本机 HTTP)"/]

    User -- "HTTP 请求<br/>登录·CRUD·搜索·上传 PDF" --> System
    System -- "HTML 页面·文件下载·BibTeX·Markdown" --> User
    System <-- "SQL 读/写" --> DB
    System <-- "PDF 等附件读/写" --> FS
    System -- "POST /file_parse (PDF)" --> MinerU
    MinerU -- "Markdown + 结构块" --> System
```

### 1 层 DFD（主要功能分解）

展开系统内部的核心处理过程与数据存储。

- 圆形：处理过程（Process）
- 圆柱：数据存储（Data Store）
- 椭圆：外部实体

```mermaid
flowchart TB
    User((用户))
    MinerU((MinerU 服务))

    subgraph SYS["个人文献管理系统"]
        P1(("1.0<br/>用户认证"))
        P2(("2.0<br/>文献 CRUD"))
        P3(("3.0<br/>检索查询<br/>(基础 + 高级字段)"))
        P4(("4.0<br/>分类管理"))
        P5(("5.0<br/>字典维护<br/>(Upsert + 清理)"))
        P6(("6.0<br/>BibTeX<br/>导入/导出"))
        P7(("7.0<br/>附件管理"))
        P8(("8.0<br/>PDF 识别<br/>(MinerU + 启发式)"))
        P9(("9.0<br/>用户设置"))
    end

    D1[("D1<br/>users")]
    D2[("D2<br/>documents<br/>+ 关联表")]
    D3[("D3<br/>categories")]
    D4[("D4 字典表与标签<br/>authors / keywords / tags<br/>publishers / sources<br/>affiliations / author_codes<br/>(全部 per-user)")]
    D5[("D5<br/>uploads/ 文件系统")]
    D6[("D6<br/>user_settings")]

    User -- "用户名 / 密码" --> P1
    P1 -- "会话 Cookie" --> User
    P1 <-- "读 / 写账号" --> D1

    User -- "文献表单 (含作者/关键词/标签)" --> P2
    P2 -- "文献详情页" --> User
    P2 <-- "INSERT / UPDATE / DELETE" --> D2
    P2 -- "标准化实体" --> P5
    P5 <-- "SELECT / INSERT / DELETE" --> D4
    P2 -- "category_id" --> D3

    User -- "搜索条件 q / 分类 / 类型 / 年份范围 / 作者 / 来源 / 关键词 / 标签" --> P3
    P3 -- "结果列表" --> User
    P3 -- "JOIN 查询" --> D2
    P3 -- "匹配作者/关键词/标签/来源" --> D4

    User -- "新建/重命名/删除分类" --> P4
    P4 -- "分类树视图" --> User
    P4 <-- "读 / 写" --> D3

    User -- "扫描孤儿/疑似重复请求" --> P5
    P5 -- "孤儿+重复报告" --> User

    User -- ".bib 文件 / 文本" --> P6
    P6 -- ".bib 导出文件" --> User
    P6 -- "解析后调用" --> P2
    P6 -- "Upsert 来源/作者/关键词" --> P5

    User -- "上传 PDF / 下载请求" --> P7
    P7 -- "文件流 (download)" --> User
    P7 <-- "保存 / 删除文件" --> D5
    P7 -- "插入 file 记录" --> D2

    User -- "上传 PDF (识别用)" --> P8
    P8 -- "PDF bytes" --> MinerU
    MinerU -- "Markdown + content_list" --> P8
    P8 -- "建议字段 + .md 下载" --> User
    P8 -- "读 MinerU URL" --> D6

    User -- "MinerU URL 配置" --> P9
    P9 <-- "读 / 写" --> D6
```

### 关键数据流说明

| 编号 | 来源 → 去向 | 数据内容 |
|---|---|---|
| 1 | 用户 → 2.0 | 标题、摘要、作者文本、关键词、标签、年份、来源、附件等 |
| 2 | 2.0 → 5.0 | 待 upsert 的作者名（含编号 `#N` 或 `new`）/ 单位 / 关键词 / 标签 / 期刊 / 出版社 |
| 3 | 5.0 → D4 | "查或建" 标准化实体（在 `user_id` 内唯一） |
| 4 | 2.0 → D2 | 新增 / 更新 / 删除文献主记录及关联表 |
| 5 | 3.0 → 用户 | 经多表 JOIN 后聚合的文献结果列表 |
| 6 | 7.0 → D5 | 重命名后的 PDF 文件（`uploads/<user_id>/<uuid>.pdf`） |
| 7 | 6.0 → 2.0 | BibTeX 解析得到的字段，再走标准 CRUD 流程入库 |
| 8 | 8.0 → MinerU | PDF 文件字节（前 3 页） |
| 9 | MinerU → 8.0 | Markdown 文本 + 结构化 content_list |
| 10 | 9.0 → D6 | per-user 的 MinerU 服务地址等配置 |

---

## 三、用例 → 数据存储 矩阵（辅助视图）

| 用例 / 数据存储     | D1 users | D2 documents | D3 categories | D4 字典/标签 | D5 文件 | D6 设置 |
|---|---|---|---|---|---|---|
| 注册 / 登录         | C / R    |              |               |          |          |          |
| 新建文献            |          | C            | R             | C / R    | C        |          |
| 编辑文献            |          | U            | R             | C / R    | C        |          |
| 删除文献            |          | D            |               | D (孤儿) | D        |          |
| 搜索                |          | R            |               | R        |          |          |
| 分类管理            |          | U (解绑)     | C / U / D     |          |          |          |
| 字典表维护 / 清理   |          |              |               | R / D    |          |          |
| BibTeX 导入         |          | C            |               | C / R    |          |          |
| BibTeX 导出         |          | R            |               | R        |          |          |
| 附件上传 / 下载     |          | C / R        |               |          | C / R / D |        |
| PDF 识别            |          |              |               |          |          | R        |
| 用户设置            |          |              |               |          |          | C / R / U|

C = Create, R = Read, U = Update, D = Delete
