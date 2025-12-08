# 用户配置变量
CONFIG = {
    "IP": "127.0.0.1",                  # 请求目标 ip
    "PORT": "1025",                     # 请求目标端口
    "model_name": "ds_r1",              # 模型名称
    "presence_penalty": 0,
    "frequency_penalty": 0,
    "repetition_penalty": 1,
    "temperature": 0.6,
    "top_p": 0.9,
    "top_k": 1,
    "seed": 42,
    "ignore_eos": False,                        # 是否忽略停止词
    "think": False,                             # 是否开启 think, 仅对deepseek v3.1有效
    "max_tokens": 131072,                       # 最大输出 token 数
    "is_stream": True,                          # 是否开启流式响应
    "test_concurrent_workers": 0,               # 测试并发数量 (0表示只进行后台压力测试)
    "background_concurrent_workers": 1024,      # 后台并发数量
    "background_duration": 1000000,             # 后台压力测试持续时间(秒)
    "timeout": 600,                             # 请求超时时间, 建议和服务端的端到端超时时间保持一致

    # 后台压力测试参数范围
    "background_param_ranges": {
        "presence_penalty_range": [-2.0, 2.0],
        "frequency_penalty_range": [-2.0, 2.0],
        "repetition_penalty_range": [1.0, 2.0],
        "temperature_range": [0.1, 1.5],
        "top_p_range": [0.1, 1.0],
        "top_k_range": [1, 10],
        "seed_range": [1, 10000]
    }
}