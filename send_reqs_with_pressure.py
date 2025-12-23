import os
import json
import requests
import glob
import re
import concurrent.futures
import time
import random
import threading
from datetime import datetime
#from config_with_pressure import CONFIG # ide run
from zhejing.config_with_pressure import CONFIG

# 全局变量，用于后台压力测试控制
background_active = False
background_stats = {
    "start_time": 0,
    "total_requests": 0,
    "successful_requests": 0,
    "failed_requests": 0,
    "last_report_time": 0
}


def parse_message_line(line):
    """
    解析单行消息，格式为: [role]content
    例如: [user]你好
    """
    match = re.match(r'^\[(\w+)\](.*)$', line.strip())
    if match:
        role = match.group(1)
        content = match.group(2).strip()
        return {"role": role, "content": content}
    return None


def read_txt_file(file_path):
    """
    读取txt文件并解析消息内容
    """
    messages = []

    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # 如果只有一行，作为单轮对话处理
    if len(lines) == 1:
        return [{"role": "user", "content": lines[0].strip()}]

    # 多轮对话处理
    for line in lines:
        if line.strip():  # 跳过空行
            message = parse_message_line(line)
            if message:
                messages.append(message)

    return messages


def handle_stream_response(response, filename):
    """
    处理流式响应
    """
    full_content = ""
    reasoning_content = ""

    try:
        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    data = line[6:]  # 去掉 'data: ' 前缀

                    if data == '[DONE]':
                        break

                    try:
                        chunk = json.loads(data)
                        if 'choices' in chunk and len(chunk['choices']) > 0:
                            delta = chunk['choices'][0].get('delta', {})

                            # 提取普通内容
                            if 'content' in delta:
                                content = delta['content']
                                full_content += content

                            # 提取推理内容
                            if 'reasoning_content' in delta:
                                reasoning = delta['reasoning_content']
                                reasoning_content += reasoning

                    except json.JSONDecodeError:
                        continue

        # 构建完整的响应结构，模拟非流式响应
        response_data = {
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": CONFIG["model_name"],
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": full_content,
                        "reasoning_content": reasoning_content if reasoning_content else None
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 0,  # 这些值在流式响应中通常不可用
                "completion_tokens": 0,
                "total_tokens": 0
            }
        }

        return response_data
    except Exception as e:
        raise Exception(f"处理流式响应时出错: {str(e)}")


def send_request(file_info, config, is_background=False):
    """
    发送请求到聊天接口

    Args:
        file_info: 文件信息元组 (file_path, filename)
        config: 配置字典
        is_background: 是否为后台压力测试请求
    """
    file_path, filename = file_info
    start_time = time.time()

    try:
        # 读取并解析文件内容
        messages = read_txt_file(file_path)

        url = f"http://{config['IP']}:{config['PORT']}/v1/chat/completions"

        # 如果是后台压力测试，随机生成参数
        if is_background:
            payload = {
                "model": config["model_name"],
                "messages": messages,
                "stream": False,  # 后台压力测试默认不使用流式
                "presence_penalty": random.uniform(*config["background_param_ranges"]["presence_penalty_range"]),
                "frequency_penalty": random.uniform(*config["background_param_ranges"]["frequency_penalty_range"]),
                "repetition_penalty": random.uniform(*config["background_param_ranges"]["repetition_penalty_range"]),
                "temperature": random.uniform(*config["background_param_ranges"]["temperature_range"]),
                "top_p": random.uniform(*config["background_param_ranges"]["top_p_range"]),
                "top_k": random.randint(*config["background_param_ranges"]["top_k_range"]),
                "seed": random.randint(*config["background_param_ranges"]["seed_range"]),
                "ignore_eos": config["ignore_eos"],
                "chat_template_kwargs": {"enable_thinking": config["think"]},
                "max_tokens": config["max_tokens"]
            }
        else:
            payload = {
                "model": config["model_name"],
                "messages": messages,
                "stream": config["is_stream"],
                "presence_penalty": config["presence_penalty"],
                "frequency_penalty": config["frequency_penalty"],
                "repetition_penalty": config["repetition_penalty"],
                "temperature": config["temperature"],
                "top_p": config["top_p"],
                "top_k": config["top_k"],
                "seed": config["seed"],
                "ignore_eos": config["ignore_eos"],
                "chat_template_kwargs": {"enable_thinking": config["think"]},
                "max_tokens": config["max_tokens"]
            }

        # 根据是否流式选择不同的请求方式
        if config["is_stream"] and not is_background:  # 后台压力测试不使用流式
            response = requests.post(url, json=payload, timeout=config["timeout"], stream=True)
            response.raise_for_status()
            response_data = handle_stream_response(response, filename)
        else:
            response = requests.post(url, json=payload, timeout=config["timeout"])
            response.raise_for_status()
            response_data = response.json()

        end_time = time.time()
        processing_time = end_time - start_time

        # 提取回复内容和推理内容
        reply = ""
        reasoning = ""

        if "choices" in response_data and len(response_data["choices"]) > 0:
            message_data = response_data["choices"][0].get("message", {})
            reply = message_data.get("content", "")
            reasoning = message_data.get("reasoning_content", "")

        return {
            "filename": filename,
            "success": True,
            "messages": messages,
            "response": response_data,
            "reply": reply,
            "reasoning_content": reasoning,
            "processing_time": processing_time,
            "is_stream": config["is_stream"] and not is_background,
            "model_name": config["model_name"],
            "is_background": is_background,
            "error": None
        }

    except Exception as e:
        end_time = time.time()
        processing_time = end_time - start_time

        return {
            "filename": filename,
            "success": False,
            "messages": [],
            "response": None,
            "reply": "",
            "reasoning_content": "",
            "processing_time": processing_time,
            "is_stream": config["is_stream"] and not is_background,
            "model_name": config["model_name"],
            "is_background": is_background,
            "error": str(e)
        }


def background_pressure_test(config, dataset_files, duration=None):
    """
    后台压力测试函数

    Args:
        config: 配置字典
        dataset_files: 数据集文件列表
        duration: 测试持续时间(秒)，如果为None则持续运行直到被停止
    """
    global background_active, background_stats

    print(f"开始后台压力测试，并发数: {config['background_concurrent_workers']}")
    if duration:
        print(f"持续时间: {duration}秒")
    else:
        print("持续运行直到测试任务完成")
    print("后台压力测试使用随机参数，不保存结果...")

    background_stats["start_time"] = time.time()
    background_stats["last_report_time"] = time.time()

    def background_worker():
        while background_active:
            # 随机选择一个文件
            file_path = random.choice(dataset_files)
            filename = os.path.basename(file_path)
            file_info = (file_path, filename)

            try:
                result = send_request(file_info, config, is_background=True)
                background_stats["total_requests"] += 1

                if result["success"]:
                    background_stats["successful_requests"] += 1
                else:
                    background_stats["failed_requests"] += 1

                # 每10秒报告一次状态
                current_time = time.time()
                if current_time - background_stats["last_report_time"] >= 10:
                    elapsed = current_time - background_stats["start_time"]
                    qps = background_stats["total_requests"] / elapsed if elapsed > 0 else 0
                    success_rate = background_stats["successful_requests"] / background_stats["total_requests"] * 100 if \
                    background_stats["total_requests"] > 0 else 0

                    print(
                        f"[后台] 已发送: {background_stats['total_requests']}, 成功: {background_stats['successful_requests']}, "
                        f"失败: {background_stats['failed_requests']}, QPS: {qps:.2f}, 成功率: {success_rate:.1f}%")

                    background_stats["last_report_time"] = current_time

                # 随机延迟，模拟真实请求模式
                time.sleep(random.uniform(0.1, 0.5))

            except Exception as e:
                background_stats["total_requests"] += 1
                background_stats["failed_requests"] += 1
                print(f"[后台] 请求异常: {str(e)}")

    # 启动后台工作线程
    with concurrent.futures.ThreadPoolExecutor(max_workers=config["background_concurrent_workers"]) as executor:
        # 提交所有后台工作线程
        futures = [executor.submit(background_worker) for _ in range(config["background_concurrent_workers"])]

        # 如果有持续时间限制，等待指定时间
        if duration:
            try:
                # 等待指定时间
                time.sleep(duration)
            except KeyboardInterrupt:
                print("后台压力测试被中断")

            # 停止后台压力测试
            background_active = False

            # 等待所有线程结束
            concurrent.futures.wait(futures, timeout=10)
        else:
            # 如果没有持续时间限制，等待所有线程完成
            # 这种情况实际上不会发生，因为后台线程是无限循环的
            # 我们会在外部通过设置background_active=False来停止
            try:
                # 等待所有线程完成（实际上不会完成，除非被停止）
                for future in futures:
                    future.result()
            except:
                pass

    # 输出最终统计
    elapsed = time.time() - background_stats["start_time"]
    qps = background_stats["total_requests"] / elapsed if elapsed > 0 else 0
    success_rate = background_stats["successful_requests"] / background_stats["total_requests"] * 100 if \
    background_stats["total_requests"] > 0 else 0

    print(f"\n后台压力测试完成!")
    print(f"总请求数: {background_stats['total_requests']}")
    print(f"成功请求: {background_stats['successful_requests']}")
    print(f"失败请求: {background_stats['failed_requests']}")
    print(f"平均QPS: {qps:.2f}")
    print(f"成功率: {success_rate:.1f}%")
    print(f"总时长: {elapsed:.2f}秒")


def process_dataset_files(config):
    """
    处理datasets文件夹下的所有txt文件（并发版本）
    """
    global background_active

    current_dir = os.path.dirname(os.path.abspath(__file__))
    dataset_dir = os.path.join(current_dir, "datasets")
    results_dir = os.path.join(current_dir, "results")
    #dataset_dir = "datasets"
    #results_dir = "results"

    # 创建结果目录
    if not os.path.exists(results_dir):
        os.makedirs(results_dir)

    # 查找所有txt文件
    txt_files = glob.glob(os.path.join(dataset_dir, "*.txt"))

    if not txt_files:
        print(f"在 {dataset_dir} 目录下未找到txt文件")
        return

    print(f"找到 {len(txt_files)} 个txt文件")

    # 检查配置是否有效
    if config["test_concurrent_workers"] == 0 and config["background_concurrent_workers"] == 0:
        print("错误: 测试并发和后台并发不能同时为0")
        return

    # 如果测试并发为0，只进行后台压力测试
    if config["test_concurrent_workers"] == 0:
        print(f"使用 {config['background_concurrent_workers']} 个后台并发工作线程")
        print(f"模型名称: {config['model_name']}")
        print(f"后台压力测试持续时间: {config['background_duration']}秒")

        # 启动后台压力测试
        background_active = True
        background_pressure_test(config, txt_files, duration=config["background_duration"])
        return

    # 否则，进行测试并发和后台并发
    print(f"使用 {config['test_concurrent_workers']} 个测试并发工作线程")
    if config["background_concurrent_workers"] > 0:
        print(f"使用 {config['background_concurrent_workers']} 个后台并发工作线程")
    print(f"模型名称: {config['model_name']}")
    print(f"流式模式: {'开启' if config['is_stream'] else '关闭'}")
    print(f"思考模式: {'开启' if config['think'] else '关闭'}")
    print("开始处理...\n")

    # 准备文件信息列表
    file_infos = [(file_path, os.path.basename(file_path)) for file_path in txt_files]

    # 统计信息
    total_files = len(file_infos)
    completed_files = 0
    successful_requests = 0
    failed_requests = 0

    # 收集所有结果
    all_results = {
        "config": config,
        "timestamp": datetime.now().isoformat(),
        "total_files": total_files,
        "results": []
    }

    # 如果开启了后台压力测试，启动后台线程
    background_thread = None
    if config["background_concurrent_workers"] > 0:
        background_active = True
        background_thread = threading.Thread(
            target=background_pressure_test,
            args=(config, txt_files, None)  # 不设置持续时间，随测试结束而停止
        )
        background_thread.start()

    # 使用线程池并发处理测试请求
    with concurrent.futures.ThreadPoolExecutor(max_workers=config["test_concurrent_workers"]) as executor:
        # 提交所有任务
        future_to_file = {
            executor.submit(send_request, file_info, config, False): file_info
            for file_info in file_infos
        }

        # 处理完成的任务
        for future in concurrent.futures.as_completed(future_to_file):
            file_info = future_to_file[future]
            file_path, filename = file_info

            try:
                result = future.result()
                all_results["results"].append(result)

                completed_files += 1

                if result["success"]:
                    successful_requests += 1
                    status = "✓ 成功"

                    # 显示回复和推理内容
                    reply_preview = result["reply"][:50] + "..." if len(result["reply"]) > 50 else result["reply"]
                    reasoning_preview = ""
                    if result["reasoning_content"]:
                        reasoning_preview = result["reasoning_content"][:50] + "..." if len(
                            result["reasoning_content"]) > 50 else result["reasoning_content"]
                        reply_preview = f"回复: {reply_preview}, 推理: {reasoning_preview}"
                    else:
                        reply_preview = f"回复: {reply_preview}"
                else:
                    failed_requests += 1
                    status = "✗ 失败"
                    reply_preview = result["error"]

                stream_indicator = " [流式]" if result["is_stream"] else ""
                print(f"[{completed_files}/{total_files}] {status}{stream_indicator} - {filename}")
                print(f"  模型: {result['model_name']}, 时间: {result['processing_time']:.2f}s, {reply_preview}")

            except Exception as e:
                completed_files += 1
                failed_requests += 1

                # 添加错误结果到总结果中
                error_result = {
                    "filename": filename,
                    "success": False,
                    "messages": [],
                    "response": None,
                    "reply": "",
                    "reasoning_content": "",
                    "processing_time": 0,
                    "is_stream": config["is_stream"],
                    "model_name": config["model_name"],
                    "is_background": False,
                    "error": str(e)
                }
                all_results["results"].append(error_result)

                print(f"[{completed_files}/{total_files}] ✗ 异常 - {filename}")
                print(f"  错误: {str(e)}")

    # 停止后台压力测试
    if background_thread:
        background_active = False
        background_thread.join(timeout=10)
        print("\n后台压力测试已停止")

    # 更新统计信息
    all_results["successful_requests"] = successful_requests
    all_results["failed_requests"] = failed_requests
    all_results["success_rate"] = successful_requests / total_files * 100 if total_files > 0 else 0

    # 保存所有结果到一个JSON文件
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = os.path.join(results_dir, f"all_results_{timestamp}.json")

    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    # 输出统计信息
    print("\n" + "=" * 50)
    print("处理完成!")
    print(f"总文件数: {total_files}")
    print(f"成功请求: {successful_requests}")
    print(f"失败请求: {failed_requests}")
    print(f"成功率: {successful_requests / total_files * 100:.1f}%")
    print(f"模型名称: {config['model_name']}")
    print(f"流式模式: {'开启' if config['is_stream'] else '关闭'}")
    print(f"思考模式: {'开启' if config['think'] else '关闭'}")
    print(f"\n所有结果已保存到: {results_file}")


def validate_config(config):
    """
    验证配置参数
    """
    if config["test_concurrent_workers"] < 0:
        print("警告: 测试并发工作线程数不能小于0，已设置为0")
        config["test_concurrent_workers"] = 0

    if config["background_concurrent_workers"] < 0:
        print("警告: 后台并发工作线程数不能小于0，已设置为0")
        config["background_concurrent_workers"] = 0

    if config["test_concurrent_workers"] == 0 and config["background_concurrent_workers"] == 0:
        print("错误: 测试并发和后台并发不能同时为0")
        return False

    if config["test_concurrent_workers"] > 50 or config["background_concurrent_workers"] > 50:
        print("警告: 并发工作线程数较大，可能会对服务器造成压力")

    if config["timeout"] < 1:
        print("警告: 超时时间不能小于1秒，已设置为60秒")
        config["timeout"] = 60

    if config["background_duration"] < 1:
        print("警告: 后台压力测试持续时间不能小于1秒，已设置为300秒")
        config["background_duration"] = 300

    # 确保模型名称不为空
    if not config["model_name"] or config["model_name"].strip() == "":
        print("警告: 模型名称不能为空，已设置为默认值 'ds_r1'")
        config["model_name"] = "ds_r1"

    # 验证参数范围
    param_ranges = config["background_param_ranges"]
    for param_name, param_range in param_ranges.items():
        if len(param_range) != 2:
            print(f"警告: {param_name} 范围格式错误，应包含两个值 [min, max]")
            # 设置默认范围
            if "penalty" in param_name:
                param_ranges[param_name] = [-2.0, 2.0]
            elif param_name == "temperature_range":
                param_ranges[param_name] = [0.1, 1.5]
            elif param_name == "top_p_range":
                param_ranges[param_name] = [0.1, 1.0]
            elif param_name == "top_k_range":
                param_ranges[param_name] = [1, 100]
            elif param_name == "seed_range":
                param_ranges[param_name] = [1, 10000]

    return True


def run_zhejing(config=None):
    """
    主函数
    """
    if config:
        CONFIG.update(config)

    print("开始自动并发请求...")

    # 验证配置
    if not validate_config(CONFIG):
        print("配置验证失败，程序退出")
        return

    print("配置信息:")
    for key, value in CONFIG.items():
        if key != "background_param_ranges":
            print(f"  {key}: {value}")

    print("后台压力测试参数范围:")
    for param_name, param_range in CONFIG["background_param_ranges"].items():
        print(f"  {param_name}: {param_range}")

    start_time = time.time()
    process_dataset_files(CONFIG)
    end_time = time.time()

    total_time = end_time - start_time
    print(f"\n总执行时间: {total_time:.2f}秒")


if __name__ == "__main__":
    run_zhejing()
