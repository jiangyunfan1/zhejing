# 用户配置变量
CONFIG = {
    "IP": "127.0.0.1",          # 请求目标 ip
    "PORT": "1025",             # 请求目标端口
    "model_name": "ds_r1",      # 模型名称
    "presence_penalty": 0,      # 后处理参数
    "frequency_penalty": 0,
    "repetition_penalty": 1,
    "temperature": 0.6,
    "top_p": 1,
    "top_k": -1,
    "seed": 1,
    "ignore_eos": False,        # 无视结束符
    "think": True,              # 是否启用 think 模式, 仅 deepseek v3.1 支持
    "max_tokens": 131072,       # 最大输出 token 数, 支持范围(0，2147483647]
    "is_stream": False,         # 是否开启流式响应
    "concurrent_workers": 50,   # 并发量
    "timeout": 600              # 请求超时时间
}