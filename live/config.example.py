# Server酱推送配置
# 从 https://sct.ftqq.com/sendkey 获取 SendKey 并填入 config.py
SERVERCHAN_SENDKEY = ""

# 策略参数（与回测保持一致）
LONG_THRESHOLD = 0.035
REDUCE_THRESHOLD = -0.02
SHORT_THRESHOLD = -0.03
LONG_WEIGHT = 1.0
REDUCE_WEIGHT = 0.5

# 概念动量参数
MOMENTUM_WINDOW = 5
TOP_N = 3
DIVERSITY_STRENGTH = 0.5

# 推送开关
PUSH_ON_NO_SIGNAL = False  # 无信号时是否也推送每日简报
