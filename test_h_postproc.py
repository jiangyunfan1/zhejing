import json
import time
import requests
from datetime import datetime
from typing import List, Tuple, Dict, Any


def read_input_file(file_path: str) -> str:
    """读取输入文件内容"""
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()

def create_base_request(content: str, model_name: str) -> Dict[str, Any]:
    """创建基础请求模板"""
    return {
        "model": model_name,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 2048,
        "temperature": 1.0,
        "top_p": 1.0,
        "top_k": 0,
        "min_p": 0.0,
        "presence_penalty": 0,
        "frequency_penalty": 0.0,
        "repetition_penalty": 1,
        "ignore_eos": False,
        "logprobs": False,
        "prompt_logprobs": 0,
        "stream": False
    }

def generate_requests(base_request: Dict[str, Any], param_ranges: Dict[str, List[Any]]) -> List[Tuple[str, Dict[str, Any]]]:
    """生成所有请求变体"""
    requests_list = [("P1", base_request.copy())]
    request_count = 1

    for param_name, values in param_ranges.items():
        for value in values:
            request_count += 1
            request_name = f"P{request_count}"
            new_request = base_request.copy()
            new_request[param_name] = value
            requests_list.append((request_name, new_request))

    return requests_list

def init_result_file(file_path: str, total_requests: int) -> None:
    """初始化结果文件"""
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("HTTP请求测试结果\n")
        f.write(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"超时时间: 15分钟 (900秒)\n")
        f.write(f"请求间隔: 15秒\n")
        f.write(f"总请求数: {total_requests}\n")
        f.write("=" * 80 + "\n\n")

def log_request_result(
    file_path: str,
    name: str,
    current_time: str,
    elapsed_time: float,
    req: Dict[str, Any],
    base_request: Dict[str, Any],
    status: str,
    response_data: Any = None,
    error: str = None
) -> None:
    """记录单个请求结果到文件"""
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(f"=== {name} ===\n")
        f.write(f"发送时间: {current_time}\n")
        f.write(f"处理耗时: {elapsed_time:.2f}秒\n")

        if name != "P1":
            for key in req:
                if key in base_request and req[key] != base_request[key]:
                    f.write(f"修改参数: {key} = {req[key]}\n")

        if status == "success":
            f.write(f"HTTP状态码: {response_data.status_code}\n")
            f.write(f"响应内容:\n{response_data.text}\n")
        elif status == "timeout":
            f.write("状态: 请求超时 (超过15分钟)\n")
        elif status == "error":
            f.write(f"状态: 请求失败 - {error}\n")

        f.write("-" * 60 + "\n\n")

def send_request(
    server_ip: str,
    port,
    name: str,
    req: Dict[str, Any],
    base_request: Dict[str, Any],
    result_file: str
) -> None:
    """发送单个HTTP请求并处理结果"""
    start_time = time.time()
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    print(f"[{current_time}] 发送 {name}")

    try:
        response = requests.post(
            url=f"http://{server_ip}:{port}/v1/chat/completions",
            headers={"Content-Type": "application/json"},
            json=req,
            timeout=900
        )
        elapsed_time = time.time() - start_time
        log_request_result(result_file, name, current_time, elapsed_time, req, base_request, "success", response)
        print(f"  ✓ {name} 完成 (耗时: {elapsed_time:.2f}秒)")

    except requests.exceptions.Timeout:
        elapsed_time = time.time() - start_time
        log_request_result(result_file, name, current_time, elapsed_time, req, base_request, "timeout")
        print(f"  ✗ {name} 超时 (耗时: {elapsed_time:.2f}秒)")

    except requests.exceptions.RequestException as e:
        elapsed_time = time.time() - start_time
        log_request_result(result_file, name, current_time, elapsed_time, req, base_request, "error", error=str(e))
        print(f"  ✗ {name} 失败: {str(e)} (耗时: {elapsed_time:.2f}秒)")

def run_postproc(server_ip="localhost", port=1025, model_name="auto", is_long=False) -> None:
    """主函数控制整个流程"""
    # 配置参数
    curr_time = datetime.now().strftime('%Y%m%d%H%M%S')
    result_file = f"result_houchuli_{curr_time}.txt"
    param_ranges = {
        "temperature": [0.1, 0.6, 1.0],
        "top_p": [0.1, 0.6, 1.0],
        "top_k": [0, 1],
        "min_p": [0.1, 0.6, 1.0],
        "presence_penalty": [0, -1, -2, 1, 2],
        "frequency_penalty": [0, -1, -2, 1, 2],
        "repetition_penalty": [0.5, 1.0, 2.0],
        "ignore_eos": [False, True],
        "logprobs": [False, True],
        "prompt_logprobs": [0, 1, -1]
    }

    # 初始化
    content = "San Francisco is a"
    if is_long:
        input_file = os.path.join("datasets", "长输入_119k_小说续写.txt")
        content = read_input_file(input_file)
    base_request = create_base_request(content, model_name)
    requests_list = generate_requests(base_request, param_ranges)

    # 初始化结果文件
    init_result_file(result_file, len(requests_list))
    print("开始发送HTTP请求，每秒发送一个...")
    print(f"超时时间: 15分钟 (900秒)")
    print(f"结果将保存到 {result_file} 文件中")
    print("-" * 80)

    # 发送请求
    for i, (name, req) in enumerate(requests_list, 1):
        send_request(server_ip, port, name, req, base_request, result_file)

        # 添加请求间隔
        if i < len(requests_list):
            print("等待1秒后发送下一个请求...")
            time.sleep(1)

    # 结束处理
    end_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(result_file, "a", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write(f"测试完成时间: {end_time}\n")
        f.write(f"总请求数: {len(requests_list)}\n")
        f.write("=" * 80 + "\n")

    print("\n" + "=" * 80)
    print("所有请求发送完成!")
    print(f"总请求数: {len(requests_list)}")
    print(f"结果已保存到 {result_file} 文件中")

if __name__ == "__main__":
    run_postproc()
