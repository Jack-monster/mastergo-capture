# 维护约定

- 与用户使用中文交流。
- 本仓库就是 mastergo-capture skill，直接位于 .agents/skills/mastergo-capture，不使用收纳仓库或符号链接。
- 只维护 SKILL.md、说明、脚本与干净模板。运行环境、角色、凭证和产物属于使用此 skill 的项目。
- 不在 skill 目录安装依赖或运行采集；不提交登录态、Cookie、令牌或设计数据。
- 修改后运行 python3 scripts/check_skills.py；基础检查不替代采集功能测试。
- 更新项目模板时保留用户本地修改。
