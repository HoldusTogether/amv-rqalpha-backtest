# Server酱推送配置
# 方式一（推荐）：设置环境变量 SERVERCHAN_SENDKEY
#   命令行： set SERVERCHAN_SENDKEY=你的SendKey
#   PowerShell： $env:SERVERCHAN_SENDKEY="你的SendKey"
#   也可在启动脚本（如 live_update_and_monitor.ps1）中设置
#
# 方式二：取消下面这行的注释，填入 SendKey
# import os; os.environ["SERVERCHAN_SENDKEY"] = "你的SendKey"
#
# 从 https://sct.ftqq.com/sendkey 获取 SendKey

# 推送开关
PUSH_ON_NO_SIGNAL = False  # 无信号时是否也推送每日简报
