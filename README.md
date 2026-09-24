# MasterGo Capture

独立维护的 Agent skill，通过浏览器采集 MasterGo 图层、标注、文字和 PNG，输出供 H5 实现使用的设计资料包。

## 安装

直接克隆到本地技能目录（目标目录应不存在）：

```bash
git clone git@github.com:Jack-monster/mastergo-capture.git ~/.agents/skills/mastergo-capture
```

仓库目录就是技能目录，不需要符号链接。更新时在该目录执行 `git pull`。

## 使用

Skill 本身只提供模板，不在这里安装依赖或保存登录态。完整说明见 [SKILL.md](SKILL.md)。

```bash
python3 ~/.agents/skills/mastergo-capture/scripts/init_project.py \
  --project /path/to/your-project --role collector
```

然后在目标项目执行：

```bash
python tools/mastergo-capture/run.py setup --with-browser
python tools/mastergo-capture/run.py login
python tools/mastergo-capture/run.py capture \
  --url "MasterGo设计链接" --scope layer --out player --headless
```

源码在项目 tools/mastergo-capture/，环境和会话在 .mastergo/，产物在 design-bundle/。消费方使用 --role consumer。

## 维护

直接在本仓库编辑、检查、提交并推送：

```bash
python3 scripts/check_skills.py
git add .
git commit -m "Update skill"
git push
```

GitHub Actions 自动检查 Python 语法、模板清洁度、项目初始化、重复初始化保护和分享包范围，不需要登录凭证。

已有项目不会被 skill 更新自动覆盖。显式更新未被本地修改的工具文件：

```bash
python3 scripts/init_project.py --project /path/to/your-project --update
```

分享轻量模板包：

```bash
python3 scripts/package_share.py --out /path/to/your-project/release/MasterGo-Capture-Skill-Lite.zip
```

不要提交运行环境、浏览器 profile、认证文件或项目设计数据。
