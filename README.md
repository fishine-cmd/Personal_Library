# Personal Library 项目开发说明书

> 这份文档写给开发者们。  
> 包括：这个系统为什么这样设计、每个文件在做什么、这些文件怎样连起来、每个功能是怎样被代码实现出来的，以及最后如何把整个项目打包成可分发的桌面程序。

---

## 1. 项目概要

这是一个基于 **Flask + MySQL + Bootstrap** 开发的个人图书馆/个人文献管理系统。

主要解决这些问题：

1. 把论文、书籍、报告等资料统一记录在一个系统里。
2. 给文献附加作者、关键词、分类、出版社、期刊/会议来源、阅读状态、评分、个人笔记等信息。
3. 给每篇文献上传 PDF、DOCX、EPUB 等附件。
4. 支持 BibTeX 导入导出，方便和其他学术工具互通。
5. 接入 MinerU，实现 PDF 自动识别和 Markdown 导出。
6. 最终既能以“网页方式”运行，也能打包成 Windows 桌面程序交给普通用户使用。

---

## 2. 设计理念

这一部分很重要。理解了设计理念，后面看文件时就不会迷路。

### 2.1 为什么使用 Flask

Flask 是一个轻量级 Python Web 框架。  
这里的“轻量级”不是功能少，而是结构清楚、自由度高，适合做这种中小型业务系统。

在本项目中，Flask 负责：

1. 接收浏览器或桌面窗口发来的请求。
2. 决定应该执行哪段 Python 代码。
3. 读取数据库。
4. 把结果渲染成 HTML 页面返回给前端。

### 2.2 为什么使用 MySQL

MySQL 是关系型数据库。  
本项目的数据不是简单的“一个表存一切”，而是拆成了多个相关联的表：

1. 用户表
2. 文献表
3. 作者表
4. 关键词表
5. 分类表
6. 出版社表
7. 来源表（期刊、会议等）
8. 附件表
9. 用户设置表
10. 以及若干中间关联表

这样设计的好处是：

1. 数据不容易重复。
2. 修改一处信息时，不会到处都要改。
3. 后续扩展更方便。

### 2.3 采用“前后端不分离”

很多现代项目会把前端和后端拆成两个独立工程，例如：

1. 前端用 Vue / React
2. 后端用 Flask / Java / Node

本项目没有这样做，而是采用 **Flask + Jinja2 模板 + Bootstrap** 的方式。

这意味着：

1. 前端页面文件放在 `app/templates/`
2. 后端逻辑放在 `app/blueprints/`
3. Flask 在服务器端把数据直接填进 HTML 页面

这样做的优点：

1. 项目结构更简单，适合个人项目和桌面软件包装。
2. 学习门槛更低。
3. 打包成桌面程序时更自然，因为本质上它仍然是一个本地 Web 应用。

### 2.4 同时支持“网页运行”和“桌面运行”

本项目实际上有两种运行形态：

1. **开发模式**：直接运行 Flask，用浏览器打开。
2. **发布模式**：把 Flask 嵌入 `pywebview`，打包成 Windows 可执行程序。

这意味着开发者可以方便调试，普通用户也可以像使用普通软件一样双击打开。

### 2.5 接入 MinerU

MinerU 是一个独立的文档解析工具。  
它负责把 PDF 转成结构化内容，例如 Markdown 和文本块列表。

本项目并不直接修改 MinerU 的内部算法，而是：

1. 通过 HTTP 请求把 PDF 发给 MinerU
2. 拿回解析结果
3. 再用本项目自己的规则提取标题、作者、摘要、关键词等建议字段

这种设计叫“解耦”，好处是：

1. 主项目和 PDF 识别服务彼此独立
2. 以后要换识别服务时，只需要改接入层

---

## 3. 整体运行架构

以下链路可以概括整个系统：

**用户在页面上填写表单 -> Flask 接收请求 -> Python 业务代码处理 -> SQLAlchemy 读写 MySQL -> Jinja2 渲染 HTML 页面 -> 用户继续操作**

如果涉及 PDF 识别，则多一条支线：

**用户上传 PDF -> Flask 把 PDF 发给 MinerU -> MinerU 返回 Markdown 和结构化结果 -> 本项目提取建议字段 -> 页面展示识别结果**

### 3.1 架构分层

项目可以分成 7 层：

1. **入口层**：决定程序怎么启动  
   文件：`run.py`、`desktop_app.py`
2. **配置层**：告诉程序数据库地址、上传目录等  
   文件：`config.py`、`.env`
3. **扩展层**：初始化数据库、登录系统  
   文件：`app/extensions.py`
4. **模型层**：定义数据库里有哪些表，它们如何关联  
   文件：`app/models.py`
5. **路由/控制层**：决定页面访问和表单提交该由谁处理  
   文件：`app/blueprints/*.py`
6. **服务层**：放复用的业务函数  
   文件：`app/services/*.py`
7. **展示层**：HTML 页面、CSS 样式、JS 交互  
   文件：`app/templates/*`、`app/static/*`

### 3.2 数据流

最常见的数据流如下：

1. 用户打开“新增文献”页面
2. Flask 执行 `documents.new()`
3. 页面模板 `app/templates/documents/edit.html` 被渲染出来
4. 用户填写表单并提交
5. Flask 再次进入 `documents.new()`
6. 该函数调用 `_persist_document_form()`
7. `_persist_document_form()` 再调用 `upsert.py` 里的函数处理作者、关键词、来源等
8. SQLAlchemy 把最终结果保存到 MySQL
9. Flask 跳转到文献详情页 `documents.detail()`
10. 模板 `app/templates/documents/detail.html` 把这篇文献展示出来

---

## 4. 运行环境与第一次运行说明

这一节非常适合第一次接手项目的人。

### 4.1 基础运行环境

开发本项目至少需要：

| 项目 | 作用 | 是否必须 |
|---|---|---|
| Python 3.10 - 3.13 | 运行后端代码 | 必须 |
| MySQL 5.7+ 或 8.x | 存储业务数据 | 必须 |
| Windows | 当前项目主要面向 Windows 打包发布 | 强烈建议 |
| PowerShell | 执行脚本和命令 | 建议 |
| 虚拟环境 `.venv` | 隔离依赖 | 建议 |

如果你只是想跑测试，不连接 MySQL，也可以使用项目里的测试环境，因为测试使用的是 SQLite 内存数据库。

### 4.2 第一次运行前要知道的事

第一次接手本项目时，请特别注意下面几点：

1. **MySQL 必须先安装好**
2. **`.env` 文件里有数据库连接信息**
3. **桌面版第一次运行时会弹出 MySQL 配置向导**
4. **`build/`、`dist/`、`__pycache__/`、`.pytest_cache/` 不是核心源码**
5. **MinerU 不是自动内嵌启动的**

### 4.3 从源码第一次运行

#### 步骤 1：进入项目目录

```powershell
cd C:\Users\lya\Desktop\library_system
```

#### 步骤 2：创建虚拟环境

```powershell
python -m venv .venv
```

#### 步骤 3：激活虚拟环境

```powershell
.\.venv\Scripts\Activate.ps1
```

#### 步骤 4：安装依赖

```powershell
pip install -r requirements.txt
```

#### 步骤 5：检查 `.env`

将'.env.example'中的FLASK_SECRET_KEY和DATABASE_URL修改后存为.env文件
确认 `.env` 中的数据库地址正确，例如：

1. 用户名是否正确
2. 密码是否正确
3. 数据库名是否正确

#### 步骤 6：运行开发服务器

```powershell
python run.py
```

#### 步骤 7：在浏览器打开

```
http://127.0.0.1:5000
```

#### 第一次运行时会发生什么

`create_app()` 在启动时会执行一次 `db.create_all()`。

这表示：

1. 如果数据库表还不存在，会自动创建。
2. 如果表已经存在，再运行也不会重复创建。

#### 第一次运行常见问题

1. 启动后提示无法连接 MySQL  
   说明 `.env` 里的数据库地址不对，或者 MySQL 服务没启动。

2. 中文显示异常  
   需要检查 MySQL 是否使用 `utf8mb4` 字符集。

3. 上传文件失败  
   需要检查上传目录是否有写入权限。

### 4.4 桌面版第一次运行

如果你运行的是：

```powershell
python desktop_app.py
```

或者双击打包后的：

```text
PersonalLibrary.exe
```

那么第一次运行时流程是：

1. 程序先打开一个“配置向导”窗口
2. 你填写 MySQL 主机、端口、用户名、密码、数据库名
3. 程序测试连接
4. 如果数据库不存在，会自动创建数据库
5. 程序把这份配置保存到：
   `%APPDATA%\PersonalLibrary\config.json`
6. 之后才进入主界面

#### 桌面版后续使用说明

第一次配置成功后，后续使用会更简单：

1. 双击程序
2. 程序读取本地配置
3. 自动连接数据库
4. 直接进入登录页

如果需要重新配置数据库，只要删除：

```text
%APPDATA%\PersonalLibrary\config.json
```

---

## 5. 普通用户后续怎样使用

这部分虽然看起来偏“用户手册”，但对开发者也很重要，因为你需要知道每个页面的业务目标。

### 5.1 登录和注册

1. 打开系统后先注册账号
2. 使用用户名和密码登录
3. 登录后进入文献列表页

### 5.2 新增文献

1. 点击“新增文献”
2. 填标题、作者、来源、摘要、关键词等
3. 可上传附件
4. 保存后进入详情页

### 5.3 编辑文献

1. 在列表页或详情页点击“编辑”
2. 修改内容
3. 保存

### 5.4 分类管理

1. 在分类页新建父分类或子分类
2. 删除分类时，该分类下文献会变成“未分类”
3. 删除父分类时，子分类会上移

### 5.5 PDF 识别

1. 先启动 MinerU 服务
2. 在设置页填好 MinerU 地址
3. 在新增/编辑文献页点击“识别 PDF”
4. 程序会返回建议字段和 Markdown
5. 用户可下载 `.md` 或手动填入表单

### 5.6 BibTeX 导入导出

1. 导入：上传 `.bib` 文件或粘贴 BibTeX 文本
2. 导出：导出整个库或单篇文献

### 5.7 字典清理

字典表是作者、单位、出版社、来源、关键词等公共信息表。

使用流程：

1. 打开“字典表”
2. 点击“检测冗余数据”
3. 查看孤立项和疑似重复项
4. 一键删除未被引用的孤立项

---

## 6. 项目目录总览

下面先从“目录级别”建立地图。

```text
library_system/
├── app/                            主应用源码
├── docs/                           设计图文档
├── tests/                          自动化测试
├── uploads/                        开发模式附件目录
├── output/                         MinerU 输出样例/结果目录
├── instance/                       Flask 运行时目录
├── MinerU-master（PDF识别工具）     第三方 MinerU 源码快照
├── build/                          PyInstaller 构建中间产物
├── dist/                           PyInstaller 打包输出
├── .venv/                          本地 Python 虚拟环境
├── .pytest_cache/                  pytest 缓存
├── __pycache__/                    Python 缓存
├── .env                            本地环境变量
├── .gitignore                      Git 忽略规则
├── build.ps1                       打包脚本
├── build_log.txt                   历史构建日志
├── config.py                       全局配置
├── desktop_app.py                  桌面程序入口
├── launch.bat                      同时启动主程序和 MinerU 的批处理
├── library_system.spec             PyInstaller 打包配置
├── mineru.ps1                      启动 MinerU 服务的脚本
├── README.md                       本说明书
├── requirements-build.txt          打包依赖
├── requirements.txt                运行依赖
├── run.py                          开发入口
└── start.bat                       简单启动 Flask 的批处理
```

---

## 7. 每个文件和目录的具体作用

这一节是本说明书的核心内容。

### 7.1 根目录文件

#### `.env`

作用：

1. 保存本地环境变量
2. 最重要的是数据库连接地址和 Flask 密钥

它被谁使用：

1. [config.py](C:/Users/lya/Desktop/library_system/config.py) 通过 `load_dotenv()` 读取它
2. 整个 Flask 应用通过配置系统间接使用它

开发注意：

1. 不要把真实密码随意发给别人
2. 修改数据库地址后，重启程序才会生效

#### `.gitignore`

作用：

1. 告诉 Git 哪些文件不要提交
2. 常见是缓存、虚拟环境、构建产物、运行时文件

#### `config.py`

作用：

1. 定义开发、生产、测试三套配置
2. 告诉 Flask 使用哪个数据库
3. 设置上传目录、上传大小限制、允许的文件类型

关键类：

1. `BaseConfig`
2. `DevConfig`
3. `ProdConfig`
4. `TestConfig`

它连接谁：

1. 被 [app/__init__.py](C:/Users/lya/Desktop/library_system/app/__init__.py) 读取
2. 影响数据库、上传目录、测试模式等全局行为

#### `run.py`

作用：

1. 开发模式入口
2. 调用 `create_app()` 创建 Flask 应用
3. 以 `127.0.0.1:5000` 运行

#### `desktop_app.py`

作用：

1. 桌面版程序入口
2. 把 Flask 嵌入 `pywebview`
3. 首次运行时引导用户填写 MySQL 配置
4. 自动建库、建表
5. 把上传文件保存到 `%APPDATA%` 下

为什么它很重要：

这是“源码项目”变成“普通用户可双击软件”的关键。

它内部主要做了 5 件事：

1. 找到用户配置文件位置
2. 读取或保存数据库连接配置
3. 确保 MySQL 数据库存在
4. 在后台线程中运行本地 Flask 服务
5. 用原生窗口打开这个本地服务

#### `requirements.txt`

作用：

1. 声明项目运行所需的 Python 依赖

里面包含的核心依赖：

1. `Flask`
2. `Flask-Login`
3. `Flask-WTF`
4. `SQLAlchemy`
5. `PyMySQL`
6. `python-dotenv`
7. `bibtexparser`
8. `requests`
9. `pywebview`
10. `pytest`

#### `requirements-build.txt`

作用：

1. 在运行依赖基础上增加打包依赖
2. 目前最重要的是 `pyinstaller`

#### `library_system.spec`

作用：

1. 告诉 PyInstaller 如何打包本项目
2. 指定入口脚本是 `desktop_app.py`
3. 指定需要一起打包的模板、静态文件、隐藏导入、运行资源

#### `build.ps1`

作用：

1. 自动执行打包命令
2. 先激活虚拟环境
3. 安装构建依赖
4. 调用 PyInstaller 生成发布产物

#### `build_log.txt`

作用：

1. 记录历史构建过程输出
2. 用于排查打包失败问题

#### `launch.bat`

作用：

1. 一次性打开两个终端窗口
2. 一个运行主程序
3. 一个运行 MinerU

#### `start.bat`

作用：

1. 最简单地运行 `python run.py`

#### `mineru.ps1`

作用：

1. 设置 `MINERU_MODEL_SOURCE`
2. 启动本地 `mineru-api`

#### `README.md`

作用：

1. 项目说明文档
2. 也是新开发者的入门地图

### 7.2 `app/` 目录

这是最核心的源码目录。

#### `app/__init__.py`

作用：

1. 创建 Flask 应用对象
2. 读取配置
3. 初始化数据库和登录系统
4. 导入模型
5. 注册所有蓝图
6. 定义首页跳转逻辑

你可以把它理解成：

**“把零散部件组装成完整应用的总装配文件”**

它连接谁：

1. 读取 [config.py](C:/Users/lya/Desktop/library_system/config.py)
2. 使用 [app/extensions.py](C:/Users/lya/Desktop/library_system/app/extensions.py)
3. 导入 [app/models.py](C:/Users/lya/Desktop/library_system/app/models.py)
4. 注册 `blueprints/` 里的所有页面模块

#### `app/extensions.py`

作用：

1. 创建数据库对象 `db`
2. 创建登录管理器 `login_manager`

为什么单独拆出来：

因为这些对象要被很多文件共用，如果每个文件都各自创建一份，系统会乱掉。

#### `app/models.py`

作用：

1. 定义数据库中的全部核心表
2. 定义表与表之间的关系
3. 提供模型上的辅助属性和方法

主要模型说明：

| 模型 | 作用 |
|---|---|
| `User` | 用户账号 |
| `Category` | 分类树节点 |
| `Document` | 文献主记录 |
| `Author` | 作者字典 |
| `Affiliation` | 单位字典 |
| `Keyword` | 关键词字典 |
| `Publisher` | 出版社字典 |
| `Source` | 期刊/会议/书系来源 |
| `File` | 文献附件 |
| `UserSetting` | 用户设置，例如 MinerU 地址 |
| `DocumentAuthor` | 文献与作者的中间表 |
| `DocumentKeyword` | 文献与关键词的中间表 |
| `AuthorAffiliation` | 作者与单位的中间表 |
| `AuthorCode` | 同名作者编号计数器 |

特别要理解的点：

1. `Document` 是系统中心。
2. 作者、关键词、单位不是直接写死在 `Document` 一张表里，而是拆成独立表。
3. 同名作者用 `code` 区分，例如 `张三#1`、`张三#2`。

### 7.3 `app/blueprints/` 目录

蓝图可以理解成“按业务模块拆分的页面控制器”。

#### `app/blueprints/__init__.py`

作用：

1. 把 `blueprints` 目录标记为 Python 包
2. 当前没有核心业务代码

#### `app/blueprints/auth.py`

作用：

1. 处理注册
2. 处理登录
3. 处理退出登录

主要页面：

1. `/auth/register`
2. `/auth/login`
3. `/auth/logout`

它连接谁：

1. 使用 `User` 模型
2. 使用 `login_user()`、`logout_user()`
3. 渲染 `templates/auth/*.html`

#### `app/blueprints/documents.py`

作用：

这是全项目最重要的蓝图，负责：

1. 文献列表
2. 文献搜索
3. 文献详情
4. 新建文献
5. 编辑文献
6. 删除文献
7. 上传和下载附件
8. 删除附件
9. 作者消歧接口
10. PDF 识别接口

这是项目的核心：

因为系统最主要的业务就是“文献管理”，而这些逻辑基本都在这里。

内部重要函数：

1. `_allowed_file()`：检查上传文件类型是否合法。
2. `_expand_category_ids()`：递归找出父分类下全部子分类。
3. `_ordered_categories()`：整理分类树显示顺序。
4. `_save_uploaded_files()`：把文件写入磁盘并生成 `File` 记录。
5. `_persist_document_form()`：把表单内容真正转换成数据库记录。
6. `_build_combined_markdown()`：合成 PDF 识别结果的 Markdown。

#### `app/blueprints/categories.py`

作用：

1. 展示分类树
2. 新建分类
3. 重命名分类
4. 删除分类

删除分类时的特殊逻辑：

1. 子分类会提升到上一层
2. 原分类下的文献会变成未分类

#### `app/blueprints/library.py`

作用：

1. 展示字典表
2. 删除作者、单位、出版社、来源
3. 扫描孤立项
4. 执行字典清理
5. 提供自动补全接口

#### `app/blueprints/bibtex.py`

作用：

1. 导入 BibTeX
2. 导出整个文献库为 BibTeX
3. 导出单篇文献为 BibTeX

#### `app/blueprints/settings.py`

作用：

1. 管理每个用户自己的设置
2. 当前最重要的设置是 `mineru_url`
3. 提供“测试 MinerU 连接”功能

### 7.4 `app/services/` 目录

服务层用于放“可复用业务逻辑”。

#### `app/services/__init__.py`

作用：

1. 把目录标记为 Python 包

#### `app/services/upsert.py`

作用：

这是文献录入流程中的关键服务，负责“查已有数据，如果没有就创建”。

它解决的问题：

1. 同一个作者不要重复建很多次
2. 同一个关键词不要重复建很多次
3. 同一个出版社、期刊来源不要重复建很多次

核心函数：

| 函数 | 作用 |
|---|---|
| `get_or_create_author()` | 严格模式作者查找/创建 |
| `allocate_new_author()` | 显式创建同名新作者编号 |
| `get_or_create_author_lenient()` | 宽松模式作者复用，主要给 BibTeX 导入用 |
| `peek_authors_by_name()` | 查询同名作者候选项 |
| `get_or_create_affiliation()` | 单位查找/创建 |
| `get_or_create_keyword()` | 关键词查找/创建 |
| `get_or_create_publisher()` | 出版社查找/创建 |
| `get_or_create_source()` | 来源查找/创建 |
| `parse_csv_list()` | 解析关键词、单位列表 |
| `parse_authors_field()` | 解析作者文本框 |
| `authors_field_to_text()` | 把数据库作者信息重新变回文本框内容 |

#### `app/services/bibtex_io.py`

作用：

1. 解析 BibTeX 文本并导入数据库
2. 把数据库中的文献导出为 BibTeX 文本

#### `app/services/mineru_client.py`

作用：

1. 封装对 MinerU 的 HTTP 调用
2. 让项目其他部分不需要关心底层请求细节

核心函数：

1. `health_check()`：访问 `/health`，检查 MinerU 是否在线。
2. `parse_pdf()`：访问 `/file_parse`，把 PDF 发给 MinerU 并拿回解析结果。

#### `app/services/pdf_metadata.py`

作用：

1. 从 MinerU 返回的 Markdown 和结构化块中，启发式提取元数据

提取内容包括：

1. 标题
2. 作者
3. 作者邮箱
4. 摘要
5. 关键词
6. DOI
7. 年份
8. 来源

#### `app/services/dict_cleanup.py`

作用：

1. 扫描未被引用的字典项
2. 删除孤立作者、单位、来源、出版社、关键词
3. 检测名称相似的潜在重复项
4. 文献删除后，顺带清理其周边孤立字典项

### 7.5 `app/templates/` 目录

模板文件是前端页面。

#### `app/templates/base.html`

作用：

1. 所有页面的共同底板
2. 包含导航栏、主题切换、提示消息、公共 CSS/JS 引入

#### `app/templates/auth/login.html`

登录页

#### `app/templates/auth/register.html`

注册页

#### `app/templates/documents/list.html`

1. 文献列表页
2. 分类侧栏
3. 搜索框
4. 筛选条件
5. 文献表格展示

#### `app/templates/documents/edit.html`

1. 新增文献页
2. 编辑文献页
3. 附件上传
4. 作者自动补全和消歧
5. PDF 识别弹窗
6. 来源/出版社自动补全

#### `app/templates/documents/detail.html`

作用：

1. 文献详情页
2. 展示文献元数据、摘要、笔记、作者、关键词、附件

#### `app/templates/categories/tree.html`

1. 展示分类树
2. 分类新增、重命名、删除

#### `app/templates/library/index.html`

1. 展示字典表
2. 字典清理弹窗
3. 孤立项扫描结果展示

#### `app/templates/bibtex/import.html`

1. BibTeX 导入页面
2. 支持上传 `.bib` 文件或粘贴文本

#### `app/templates/settings/index.html`

1. 设置页
2. 配置 MinerU 地址
3. 测试 MinerU 是否可连接

### 7.6 `app/static/` 目录

这里放静态资源。

#### `app/static/css/app.css`

作用：

1. 自定义整站视觉风格
2. 定义 light/dark 主题变量
3. 调整 Bootstrap 默认样式
4. 定义交互动画、加载遮罩、光标效果

#### `app/static/js/app.js`

作用：

1. 自动关闭提示框
2. 主题切换
3. 页面跳转加载动画
4. 鼠标光晕效果

### 7.7 `docs/` 目录

#### `docs/diagrams.md`

作用：

1. 用 Mermaid 图记录数据库 E-R 图
2. 记录数据流图 DFD

### 7.8 `tests/` 目录

#### `tests/__init__.py`

作用：

1. 把测试目录标记为 Python 包

#### `tests/conftest.py`

作用：

1. 提供测试共用夹具
2. 创建测试用 Flask 应用
3. 使用 SQLite 内存库代替 MySQL
4. 提供测试客户端和测试用户

#### `tests/test_models.py`

作用：

1. 测试模型关系
2. 测试 upsert 逻辑
3. 测试 BibTeX 导入导出逻辑

#### `tests/test_routes.py`

作用：

1. 测试首页重定向
2. 测试注册登录流程
3. 测试文献 CRUD 基本流程

### 7.9 运行时与生成目录

#### `uploads/`

作用：

1. 存放开发模式下上传的附件

#### `output/`

作用：

1. 存放 MinerU 输出结果
2. 通常包括 Markdown、内容列表、图片等

#### `instance/`

作用：

1. Flask 运行时目录

#### `build/`

作用：

1. PyInstaller 构建中间文件

#### `dist/`

作用：

1. 最终打包产物目录
2. 面向最终用户分发

#### `.venv/`

作用：

1. 本地 Python 依赖环境

#### `__pycache__/`

作用：

1. Python 自动生成的缓存文件

#### `.pytest_cache/`

作用：

1. pytest 自动生成的缓存目录

### 7.10 第三方源码目录

#### `MinerU-master（PDF识别工具）/`

作用：

1. 这是第三方 MinerU 项目的源码快照
2. 主要用于参考、研究或本地配套使用

重要说明：

1. 本项目的主业务代码并不直接从这里 import 核心解析逻辑
2. 主项目是通过 HTTP 调用正在运行的 `mineru-api`
3. 因此，这个目录更多是“参考/附带源码”，不是日常业务修改主战场

---

## 8. 前后端是如何搭建和连接的

本项目是“服务端渲染”模式。

### 8.1 前端由哪些部分构成

前端主要由三部分组成：

1. `templates/` 中的 HTML 模板
2. `static/css/app.css` 中的样式
3. `static/js/app.js` 和模板内联 JS 中的交互代码

### 8.2 后端由哪些部分构成

后端主要由四部分组成：

1. Flask 应用工厂
2. 蓝图路由
3. 服务层函数
4. SQLAlchemy 模型

### 8.3 它们如何连起来

可以用下面这条链理解：

```text
浏览器/桌面窗口
-> Flask 路由（blueprints）
-> 服务函数（services）
-> 数据模型（models）
-> MySQL
-> 返回数据给模板（templates）
-> CSS/JS 美化和交互
```

### 8.4 一个典型页面如何工作

以“文献列表页”为例：

1. 用户访问 `/documents/`
2. Flask 命中 `app/blueprints/documents.py` 中的 `list_documents()`
3. `list_documents()` 查询 `Document` 及相关作者、关键词等信息
4. 将结果传给 `app/templates/documents/list.html`
5. 模板渲染文献表格
6. `base.html` 自动引入 `app.css` 和 `app.js`
7. 页面最终展示在浏览器或 `pywebview` 窗口中

---

## 9. 每个功能由哪些文件实现、如何连接、代码逻辑是什么

这一节按“功能”而不是按“文件”来讲，更适合理解业务。

### 9.1 用户注册、登录、退出

涉及文件：

1. `app/blueprints/auth.py`
2. `app/models.py`
3. `app/templates/auth/login.html`
4. `app/templates/auth/register.html`
5. `app/extensions.py`
6. `app/__init__.py`

逻辑链：

1. 用户打开登录/注册页面
2. 表单提交给 `auth.py`
3. `auth.py` 读取用户名、邮箱、密码
4. 使用 `User` 模型保存或查询用户
5. 使用 `set_password()` 生成密码哈希
6. 使用 Flask-Login 完成登录会话
7. 登录后跳转到文献列表页

### 9.2 文献新增与编辑

涉及文件：

1. `app/blueprints/documents.py`
2. `app/services/upsert.py`
3. `app/models.py`
4. `app/templates/documents/edit.html`
5. `app/templates/documents/detail.html`

逻辑链：

1. 页面显示由 `edit.html` 完成
2. 用户提交表单后进入 `documents.new()` 或 `documents.edit()`
3. 两者最终都会调用 `_persist_document_form()`
4. `_persist_document_form()` 处理：
   - 标题
   - 摘要
   - 文献类型
   - 年份
   - 来源
   - 出版社
   - 作者
   - 单位
   - 关键词
   - 附件
5. 作者、关键词、来源继续通过 `upsert.py` 查重或创建
6. 保存成功后跳转到详情页

### 9.3 文献列表与搜索

涉及文件：

1. `app/blueprints/documents.py`
2. `app/templates/documents/list.html`
3. `app/models.py`

逻辑链：

1. 用户访问列表页
2. 可传入搜索词 `q`
3. 可按分类、类型、年份筛选
4. 后端构造 SQLAlchemy 查询
5. 如有搜索词，则联合作者和关键词表进行模糊查询
6. 结果按更新时间倒序显示

### 9.4 分类树管理

涉及文件：

1. `app/blueprints/categories.py`
2. `app/models.py`
3. `app/templates/categories/tree.html`
4. `app/blueprints/documents.py`

逻辑链：

1. 分类页读取当前用户全部分类
2. 后端把平面分类列表整理成树
3. 页面用递归模板展示
4. 新增时可选父分类
5. 删除时调整子分类和文献归属

### 9.5 附件上传、下载、删除

涉及文件：

1. `app/blueprints/documents.py`
2. `app/models.py`
3. `config.py`
4. `app/templates/documents/edit.html`
5. `app/templates/documents/detail.html`

逻辑链：

1. 编辑页/新增页选择本地文件
2. 后端检查扩展名是否允许
3. 生成随机文件名
4. 写入上传目录
5. 在 `files` 表中记录原始文件名、存储路径、文件大小和类型
6. 详情页可下载或删除附件

### 9.6 作者消歧

涉及文件：

1. `app/services/upsert.py`
2. `app/models.py`
3. `app/blueprints/documents.py`
4. `app/templates/documents/edit.html`

逻辑链：

1. 用户在作者文本框输入姓名
2. 前端 JS 调用 `/documents/api/author_lookup`
3. 后端查当前用户库中有没有同名作者
4. 如果有，就返回编号列表
5. 前端提示用户选择现有人物或创建新编号

### 9.7 BibTeX 导入导出

涉及文件：

1. `app/blueprints/bibtex.py`
2. `app/services/bibtex_io.py`
3. `app/services/upsert.py`
4. `app/models.py`
5. `app/templates/bibtex/import.html`

逻辑链：

1. 导入时读取 `.bib` 文本
2. `bibtexparser` 负责解析格式
3. 本项目把 BibTeX 字段转换成自己的 `Document` 字段
4. 作者、关键词、来源继续复用 `upsert.py`
5. 导出时再把 `Document` 反向转换成 BibTeX

### 9.8 MinerU PDF 识别

涉及文件：

1. `app/blueprints/settings.py`
2. `app/blueprints/documents.py`
3. `app/services/mineru_client.py`
4. `app/services/pdf_metadata.py`
5. `app/templates/settings/index.html`
6. `app/templates/documents/edit.html`
7. `mineru.ps1`
8. `launch.bat`

逻辑链：

1. 用户在设置页保存 MinerU 地址
2. 用户在编辑页上传 PDF
3. 前端 JS 把 PDF 提交到 `/documents/recognize_pdf`
4. 后端调用 `mineru_client.parse_pdf()`
5. MinerU 返回 Markdown 和 `content_list`
6. `pdf_metadata.extract_metadata()` 解析建议字段
7. 后端再用 `_build_combined_markdown()` 组装最终文本
8. 前端弹窗显示结果，可复制或下载

### 9.9 字典表维护与清理

涉及文件：

1. `app/blueprints/library.py`
2. `app/services/dict_cleanup.py`
3. `app/models.py`
4. `app/templates/library/index.html`

逻辑链：

1. 页面展示当前用户所有作者、单位、来源、出版社
2. 点击“检测冗余数据”
3. 后端扫描是否有未被文献使用的记录
4. 结果以 JSON 返回页面
5. 前端弹窗显示扫描结果
6. 用户确认后执行删除

### 9.10 主题切换与全站交互

涉及文件：

1. `app/templates/base.html`
2. `app/static/js/app.js`
3. `app/static/css/app.css`

逻辑链：

1. 页面加载前先读取本地主题设置
2. 给 `html` 节点写入 `data-theme`
3. CSS 根据主题变量改变界面颜色
4. JS 处理切换按钮、加载动画、提示自动消失等

---

## 10. 文件之间是怎样连接的

下面用“关系图式”的方式再梳理一次。

### 10.1 启动连接链

```text
run.py / desktop_app.py
-> app/__init__.py:create_app()
-> config.py
-> app/extensions.py
-> app/models.py
-> app/blueprints/*.py
```

### 10.2 文献保存连接链

```text
templates/documents/edit.html
-> blueprints/documents.py
-> _persist_document_form()
-> services/upsert.py
-> models.py
-> MySQL
```

### 10.3 PDF 识别连接链

```text
templates/settings/index.html
-> blueprints/settings.py
-> user_settings 表

templates/documents/edit.html
-> blueprints/documents.py:recognize_pdf()
-> services/mineru_client.py
-> MinerU 服务
-> services/pdf_metadata.py
-> 返回前端弹窗
```

### 10.4 打包连接链

```text
desktop_app.py
-> library_system.spec
-> requirements-build.txt
-> build.ps1 / pyinstaller 命令
-> dist/PersonalLibrary/
```

---

## 11. 自动化测试说明

### 11.1 测试存在原因

测试是为了保证：

1. 新改动不会轻易把旧功能搞坏
2. 关键业务逻辑有基本验证

### 11.2 当前测试覆盖内容

1. 首页跳转
2. 注册登录
3. 文献创建、查询、删除
4. 模型关系
5. upsert 逻辑
6. BibTeX 导入导出

### 11.3 运行测试

建议运行：

```powershell
pytest -q tests
```

仓库里还带有第三方 `MinerU-master` 的测试目录，直接跑会把那部分也收集进去，而它需要额外依赖。

---

## 12. 最后重点说明：项目打包功能

这一节请特别重视。  
本项目最有价值的特点之一，就是它不仅是一个 Flask 网站，更是一个可打包成 Windows 桌面软件的项目。

### 12.1 打包功能的意义

打包后，最终用户不需要：

1. 安装 Python
2. 手动运行 `python run.py`
3. 打开命令行

用户只需要：

1. 解压目录
2. 双击 `PersonalLibrary.exe`
3. 首次填写 MySQL 连接
4. 开始使用

这让项目从“开发者工具”变成“可交付产品”。

### 12.2 打包相关的关键文件

打包功能主要由这些文件共同实现：

| 文件 | 作用 |
|---|---|
| `desktop_app.py` | 桌面入口，决定 `.exe` 启动后运行什么 |
| `library_system.spec` | PyInstaller 打包规则 |
| `requirements-build.txt` | 打包所需依赖 |
| `build.ps1` | 一键打包脚本 |
| `dist/` | 最终产物目录 |
| `build/` | 构建中间目录 |

### 12.3 `library_system.spec` 到底做了什么

这个文件在打包时主要完成以下事情：

1. 指定入口脚本为 `desktop_app.py`
2. 把 `app/templates` 和 `app/static` 一起打包进去
3. 把蓝图和服务层的“隐藏导入”加进去
4. 把 `webview`、`pythonnet`、`clr_loader` 等桌面运行必需资源打进去
5. 排除某些无关模块，例如 `pytest`

为什么要显式写这些：

因为 PyInstaller 不能总是自动识别 Flask 项目的动态导入关系。  
如果不写清楚，打包后的程序可能会启动失败、页面找不到、模板缺失、按钮无效。

### 12.4 如何打包

#### 方式 1：手动命令

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements-build.txt
pyinstaller library_system.spec --clean --noconfirm
```

#### 方式 2：使用脚本

```powershell
.\build.ps1
```

### 12.5 打包输出在哪

最终产物在：

```text
dist\PersonalLibrary\
```

重点说明：

1. 这里不是只有一个 `exe`
2. 它通常还包含 `_internal/` 等依赖文件
3. **分发给别人时，要把整个 `PersonalLibrary` 文件夹一起发**
4. **不能只把 `PersonalLibrary.exe` 单独拷出去**

### 12.6 打包后的首次运行流程

最终用户拿到软件后：

1. 双击 `PersonalLibrary.exe`
2. 程序打开首次配置向导
3. 用户填写 MySQL 连接信息
4. 程序自动建库建表
5. 配置保存到 `%APPDATA%\PersonalLibrary\config.json`
6. 之后每次双击都直接进入主界面

### 12.7 打包后的文件与数据存放位置

打包后要区分三类内容：

1. **程序本体**
   - 位于 `dist\PersonalLibrary\`
2. **数据库数据**
   - 位于用户自己的 MySQL 中
3. **本地配置与附件**
   - 位于 `%APPDATA%\PersonalLibrary\`

这意味着：

1. 升级程序时，不一定会影响数据库
2. 删除程序文件夹，不等于自动删除数据库
3. 用户的附件和连接配置是保存在系统用户目录中的

### 12.8 打包时最容易忽视的问题

1. **MySQL 不会被打包进去**
2. **MinerU 也不会自动变成主程序的一部分**
3. **模板和静态文件必须被打包**
4. **不要只发 exe**
5. **Windows WebView2 运行环境要正常**

### 12.9 对后续开发者的建议

如果你要继续开发这个项目，请优先牢记下面几点：

1. 新增功能时，先判断它应该放在：
   - 蓝图层
   - 服务层
   - 模型层
   - 模板层
2. 如果改了页面资源，记得确认打包规则仍然包含这些资源。
3. 如果新增了新的 Python 动态导入，打包失败时可能需要修改 `library_system.spec`。
4. 如果新增了重要功能，最好补一个测试。
5. 如果面向最终用户分发，请始终在打包后亲自试运行一遍。

---

