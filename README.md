# 1) 把插件仓库放到 AstrBot/data/plugins/astrbot_plugin_kards
# 2) 在插件目录下放置 metadata.yaml, main.py, requirements.txt
# 3) 按文档运行 AstrBot 并在 WebUI -> 插件管理中重载插件
# 4) 在群/私聊中发送 `/kards %%...` 或直接把卡组码贴进来并触发 /kards 指令

# 参考：
# - KARDS Deck Builder 页面 (用于构造链接和导入): https://www.kards.com/decks/deck-builder
# - 现场观察：卡组码通常以 '%%' 开头并包含分隔符，网站可接受 ?hash= 参数来载入。