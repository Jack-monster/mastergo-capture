---
name: mastergo-capture
description: >-
  在用户项目中初始化 MasterGo 采集工具及运行/产物目录，通过已登录 Chromium
  从设计链接读取图层树、查看模式属性、文字和 PNG，输出供 H5 Agent 消费的资料包。
  用于设计采集、页面/画板枚举、旧资料包布局预处理，以及按现有设计产物还原前端。
  Skill 本身只保存模板与说明，不保存运行环境、登录态或项目产物；无需 MasterGo 个人令牌或付费 MCP。
---

# MasterGo Capture

## 先确定项目位置与角色

本 skill 是只读模板。禁止在 skill 目录执行 `uv sync`、采集、登录，或创建 `.venv`、浏览器目录、缓存、ROLE.md、输出文件。也不要直接运行 `templates/tool/` 中的代码。

以当前用户项目为工作空间。用户已给项目路径时直接使用；不明确且不能从当前工作区确定时再询问。
角色配置属于项目，读取 `<项目>/.mastergo/project.json` 与 `ROLE.md`，不要在 skill 目录查找或写入角色文件。

- **collector**：可以登录、采集、导出自己的登录态、prepare、validate。
- **consumer**：读取已有产物并还原 H5；不执行 login、capture、auth-export、prepare。需要校验时可运行 validate。通常不需要安装浏览器。

若项目尚未指定角色且当前任务无法确定是收集还是消费，请用户选择；沿用已确认的角色，不重复询问。角色需要切换时，使用用户明确请求的角色配合初始化脚本 `--change-role`，不静默改写。

## 首次初始化：写入项目，不在 skill 内运行

初始化脚本仅使用 Python 标准库，不需要先安装 uv 或第三方依赖。
将 `<skill目录>` 换成本 SKILL.md 所在目录，`<项目目录>` 换成用户项目的绝对路径：

```bash
python "<skill目录>/scripts/init_project.py" --project "<项目目录>" --role collector
```

消费方使用 `--role consumer`。初始化会创建：

```text
项目/
├── tools/mastergo-capture/       # 从模板复制的可维护代码、run.py、依赖清单及指南
├── .mastergo/
│   ├── project.json             # 项目角色、相对路径、模板文件哈希
│   ├── ROLE.md                  # 可读角色说明
│   ├── venv/                    # setup 后生成的 Python 环境
│   ├── python/                  # uv 按需下载的 Python
│   ├── browsers/                # install-browser 后生成的 Chromium
│   ├── browser-profile/         # login 后生成的专用会话
│   ├── auth/                    # auth-export 生成 mastergo.json
│   ├── cache/、tmp/、logs/      # 缓存、临时文件、无敏感参数的运行记录
│   └── .gitignore               # 默认排除运行数据，只保留角色配置
└── design-bundle/
    ├── DESIGN_MAP.md            # 待整理地图入口，不宣称已经采集
    ├── all-canvases/            # 全局枚举产物
    └── <画板名>/                # 单画板资料包
```

环境、浏览器和登录文件只在使用对应功能时生成。初始化可重复执行，不删除或覆盖已有产物、地图或登录态；存在不同的工具文件时停止并报告冲突。模板升级可添加 `--update`，它只更新先前由模板管理且未被本地修改的文件；本地改动先检查再合并，不使用强制覆盖。

## 所有后续操作使用项目启动器

以下命令在项目根目录执行。也可以从任意目录调用 `run.py` 的绝对路径；所有路径始终归属于该启动器所在项目，不依赖调用者 cwd。需要 Python 3.12+ 和 uv。

```bash
python tools/mastergo-capture/run.py paths
python tools/mastergo-capture/run.py setup --with-browser
python tools/mastergo-capture/run.py login
```

不要绕开启动器直接 `uv run` 或 `uv sync`。启动器将 uv 环境/缓存、Python 下载目录、Playwright 浏览器、临时文件和运行记录固定到 `.mastergo/`，默认不装 pytest/ruff/mypy 等开发依赖。模板入口也会拒绝直接运行。

Linux 需要系统依赖时用 `setup --with-browser --with-deps`；系统包安装可能需要管理员权限。collector 初次登录需有桌面，手动登录后在终端按 Enter 保存；不读取日常 Chrome 账号。云端只采集时可以使用自己的 auth-state。

## 工作流：全局枚举 → 页面地图 → 画板采集

```bash
python tools/mastergo-capture/run.py capture \
  --url "https://mastergo.com/file/文件ID?page_id=页面ID" \
  --scope file --flat --export none --out all-canvases --headless --max-nodes 100000
```

依据 `design-bundle/all-canvases/pages.json`、`nodes.json`，在项目 `design-bundle/DESIGN_MAP.md` 中按业务模块整理目标画板名称、节点 ID、路径和缺失项。排除草稿/参考等必须有用户任务或实际证据，不由名称前缀强行推断。地图由 Agent 整理，初始化只生成待整理入口。

然后对选定画板采集：

```bash
python tools/mastergo-capture/run.py capture \
  --url "https://mastergo.com/file/文件ID?page_id=页面ID&layer_id=图层ID" \
  --scope layer --export roots-and-leaves --out player --headless \
  --download-timeout-ms 60000 --export-wait-ms 8000
```

`--out player` 保存到 **项目/design-bundle/player/**。相对的 prepare/validate 参数也以 design-bundle 为基准。可用 `design-bundle/player` 或项目内绝对路径，不能向项目外写入。省略 `--out` 自动生成唯一目录。所有输出目录必须为空，避免覆盖旧采集。

其他相对文件参数以项目根为基准：`--profile`、`--auth-state`、`--url-file`、`--layout-overrides`、auth-export 的 `--out`。`--profile`、`--channel` 是全局参数，放在 capture/login 前；后面其他参数放在子命令后。

常用采集参数：`--scope layer|page|file`（默认 file）、`--export all|roots-and-leaves|roots|none`、`--flat`（不展开折叠组件）、`--max-nodes`（默认 5000）、`--headless`、`--url-file`（避免分享令牌进入命令参数）。

## 布局与产物消费

每个画板产出原始 `nodes.json`、`assets.json`、`pages.json`、`evidence/`、`assets/`，以及派生 `layout.json`、`preview.html`、`skeleton.html`、`LAYOUT_GUIDE.md`。

- `layout.json` 是带依据的布局描述，不是无条件可信的渲染指令。坐标默认 unknown，确认规则后才使用 parent-relative/root-relative/canvas-absolute，混合坐标用逐节点覆写。
- `preview.html` 优先使用复合 PNG 作视觉对照，不能当成已实现交互的 H5。
- `skeleton.html` 是结构草稿，隐藏状态、遮罩或字体不完整时会有差异，不直接作为交付代码。
- 根据 layout + nodes + assets 编写 H5，结合原图核对效果；未采集的交互不从名字猜测。

collector 可以离线补生成、校验旧包：

```bash
python tools/mastergo-capture/run.py prepare player --coordinate-mode parent-relative
python tools/mastergo-capture/run.py prepare player --layout-overrides layout-overrides.json
python tools/mastergo-capture/run.py validate player
```

消费方先读 `design-bundle/DESIGN_MAP.md`，再读目标画板 `AGENT_README.md` → manifest → layout/LAYOUT_GUIDE → preview/skeleton → 按需 nodes/assets/evidence。
详细字段和边界见 [references/output-format.md](references/output-format.md) 与 [references/layout-consumption.md](references/layout-consumption.md)。

## 云端与分享

collector 本地导出自己的轻量登录态，默认写到项目 `.mastergo/auth/mastergo.json`：

```bash
python tools/mastergo-capture/run.py auth-export
python tools/mastergo-capture/run.py capture --auth-state .mastergo/auth/mastergo.json \
  --url "设计稿链接" --scope layer --out cloud-player --headless
```

云端初始化同样的项目目录，setup 安装对应系统的环境，再私下放入自己的登录态。不要传整个 venv/profile，不要将认证文件放入 design-bundle。会话过期或换 IP 触发验证时本地重新登录导出，不循环尝试绕过验证码。

- 分享设计数据：只发送项目 `design-bundle/`。
- 分享 skill 模板：运行 `python "<skill目录>/scripts/package_share.py" --out "<项目目录>/release/MasterGo-Capture-Skill-Lite.zip"`。包只含 skill、脚本和干净模板。
- 旧版迁移：先停止使用旧 profile 的进程，将其移到项目 `.mastergo/browser-profile/`，将登录态放到 `.mastergo/auth/`、产物放到 design-bundle。已有目标目录不覆盖，先保存在项目 `.mastergo/legacy/`；旧 venv 不跨路径复用，重新 setup。详情见 [references/project-workspace.md](references/project-workspace.md)。

## 已知边界

只读取查看模式可见的图层树、标注及导出 PNG，不读私有应用状态/未公开 API。type 可为 null；不采集完整原型连线、组件变体、动画时间轴、字体二进制。PNG 不是保证未经裁切的原始填充图。partial 是数据覆盖状态；退出码 0 仅表示所选采集步骤没有报错。MasterGo 网站变更可能需要更新项目工具中的 DOM 适配器。
