# 项目工作空间与迁移

Skill 只有 SKILL.md、references/、scripts/ 和 templates/tool/。它是项目的初始化来源，不是运行 cwd。
初始化脚本只使用标准库，创建项目目录和待整理地图，不登录、不下载依赖、不采集、不猜测页面内容。
所有项目角色在 .mastergo/project.json；ROLE.md 是可读说明。多项目之间不复用环境、凭证或角色。

## 初始化与升级

`python <skill>/scripts/init_project.py --project <项目> --role collector`。
同样参数重复执行不覆盖用户设计地图、资料包和登录态。已有代码与模板不同会在写入前报告冲突。
`--update` 仅更新未被本地修改的模板管理文件。未追踪的同名文件或已有本地修改不会覆盖。
角色切换需要显式 `--role consumer --change-role`；恢复采集时显式切回 collector。
项目运行入口为 tools/mastergo-capture/run.py；不依赖启动时 cwd。配置记录相对路径，整个项目可以搬家。
搬到其他操作系统/路径后，重新 setup 创建 venv，不直接复用旧虚拟环境。

## 旧版迁移

1. 停止使用旧 browser-profile 的浏览器或采集进程，避免移动正在写入的数据库。
2. 初始化项目工具；检查同名代码冲突，不强行覆盖。
3. 将旧 profile 移入 .mastergo/browser-profile；目标已有 profile 时不合并数据库，保存在 .mastergo/legacy/ 并让用户明确采用哪一份。
4. 将个人登录态移动到 .mastergo/auth/mastergo.json；不要放入产物目录。
5. 将旧 output/、examples/ 中需要保留的设计资料移入 design-bundle 的不同子目录；已有名字冲突时加 legacy 前缀，不覆盖。
6. 旧环境不可直接搬家后运行。可先保存在 .mastergo/legacy/，重新 setup；验证后按用户要求清理备份。
7. skill 根的旧 pyproject、src、capture.py、login_helper.py、ROLE.md 都不是运行入口。先保存在项目的 legacy 目录，再保留新的 templates/tool 与初始化脚本。

## 文件归属

运行时写入项目 .mastergo；采集结果写入 design-bundle；源码写入 tools/mastergo-capture。
项目运行日志仅记录命令类别、起止时间与退出码，不记录完整 CLI 参数、分享令牌或 Cookie。
Chromium 的一般系统级辅助行为可能由操作系统管理；工具显式控制的浏览器安装、profile、下载临时目录和环境缓存都指向项目。
分享脚本按白名单打包，拒绝将 ZIP 写回 skill；不要直接压缩已运行过的目录。
