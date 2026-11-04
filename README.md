# xhs-note-finder

主动查找、精读和筛选小红书对标笔记的 Codex Skill；负责真实来源与适配判断，不生成改写稿。自带商家口吻参照，不预设产品，单独安装也可使用。

共享台账 v2 已接通查找与写作：任务事实快照、原文阅读范围、迁移理由和稳定编号保存在交接文件中；查找前读取历史去重与模板反馈，完成选择后实际写入。用户要求“找并改写”时顺序交给 xhs-product-copy，无需重复确认。

台账支持事件重试去重、来源规范化、版本保留、续写计数、限定对象的反馈、模板复查、并发写入、旧数据迁移和手动导出。每个技能自带同版脚本，默认连接本机 `~/Documents/Codex/小红书笔记台账`；可用 `XHS_LEDGER_ROOT` 或 `--root` 指定共享位置。记录由技能执行阶段主动调用，不是后台监听；跨设备自动同步不包含在内。

技能文件位于 `skills/xhs-note-finder`。可请求 Codex 使用 `$skill-installer` 从本仓库安装该目录；私有仓库需要访问权限。运行依赖 Python 3.9+ 标准库，适用于 macOS/Linux。

随包 `references/style-baseline.md` 提供风格基础，个人台账、产品快照、来源全文、成稿和历史反馈不上传到本仓库。没有旧台账也能工作；继续原使用历史时再迁移台账。

在技能目录运行 `python3 tests/test_ledger.py` 验证台账行为。实际操作接口见 `references/ledger.md`。两个技能中的 ledger.py、ledger.md 和测试应保持同版。
