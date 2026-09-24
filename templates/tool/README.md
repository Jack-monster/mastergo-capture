# MasterGo Capture：项目工具

此目录由 mastergo-capture skill 模板初始化。源码放在 `tools/mastergo-capture/`，运行数据放在项目 `.mastergo/`，采集结果放在项目 `design-bundle/`。不要在 skill 目录安装环境、保存角色文件或执行采集。

## 运行

需要 Python 3.12+ 和 uv。以下命令从项目根目录执行；在任意其他目录也可使用 run.py 的绝对路径，路径不会随当前工作目录改变。

```bash
python tools/mastergo-capture/run.py paths
python tools/mastergo-capture/run.py setup --with-browser
python tools/mastergo-capture/run.py login
python tools/mastergo-capture/run.py capture --url "设计稿链接" --scope layer --out player --headless
python tools/mastergo-capture/run.py prepare player --coordinate-mode parent-relative
python tools/mastergo-capture/run.py validate player
```

Linux 系统需要安装浏览器依赖时：`python tools/mastergo-capture/run.py setup --with-browser --with-deps`，系统依赖安装可能需要管理员权限。`setup` 只安装运行依赖；开发依赖另行按需安装。不要在此目录手工执行 `uv sync`，统一使用 run.py，确保环境和缓存进入 `.mastergo/`。

## 路径契约

- `run.py` 根据自身在项目里的位置定位根目录，不读取或写入 skill。
- `.mastergo/venv/`：Python 环境；`.mastergo/python/`：uv 需要下载的 Python。
- `.mastergo/browsers/`：Playwright 下载的浏览器；`.mastergo/browser-profile/`：专用浏览器会话。
- `.mastergo/auth/mastergo.json`：轻量登录态；`.mastergo/cache/`、`tmp/`：缓存和临时文件。
- `.mastergo/logs/*.json`：每次运行的命令类型、时间、退出码；不保存完整参数、令牌或原始浏览器异常。
- `.mastergo/project.json`：项目角色、相对路径和模板文件哈希；`ROLE.md`：可读角色说明。
- `design-bundle/DESIGN_MAP.md`：全局地图入口；每个命名子目录是一份画板资料包。

`capture --out player`、`prepare player`、`validate player` 都指向项目 `design-bundle/player`。相对路径 `design-bundle/player` 也有效。省略 capture 的 `--out` 时自动生成唯一名称。输出目录必须为空，不覆盖旧采集。写入路径不得越过项目边界。

其他相对路径（`--profile`、`--auth-state`、`--url-file`、`--layout-overrides`、auth-export 的 `--out`）相对项目根目录。登录态不得导出到 design-bundle。环境变量由启动器固定到项目路径，不借用调用者的活动虚拟环境。

## 轻量登录态与云端

```bash
python tools/mastergo-capture/run.py auth-export
python tools/mastergo-capture/run.py capture --auth-state .mastergo/auth/mastergo.json \
  --url "设计稿链接" --scope layer --out cloud-player --headless
```

在有桌面的机器登录并导出，将源码、`.mastergo/project.json` 以及自己的轻量登录态私下复制到目标项目；云端重新 setup 安装对应平台环境，无需传 venv 或 profile。跨 IP 验证或会话过期时重新登录导出。共享设计产物只发送 design-bundle，不携带 .mastergo。

## 产物与边界

`layout.json` 是带证据、坐标策略、层叠和资源关系的派生描述；`nodes.json`、`assets.json`、`evidence/` 保留原始数据。
`preview.html` 优先用节点复合 PNG 作为视觉参考；`skeleton.html` 是结构草稿，不能作为可直接交付的 H5。
坐标默认 unknown；只有明确约定后才使用 parent-relative/root-relative/canvas-absolute，混合情况通过逐节点覆写。
详见 [references/layout-consumption.md](references/layout-consumption.md)。

已有旧位置产物不会因路径改造自动消失。将旧输出目录搬入 design-bundle，或通过项目内绝对路径 prepare/validate。不要复制别人的登录态。
