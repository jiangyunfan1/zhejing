import os
import json
import requests
import glob
import re
import concurrent.futures
import time
from datetime import datetime
from config import CONFIG


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


def send_request(file_info, config):
    """
    发送请求到聊天接口
    """
    file_path, filename = file_info
    start_time = time.time()

    try:
        # 读取并解析文件内容
        messages = read_txt_file(file_path)

        url = f"http://{config['IP']}:{config['PORT']}/v1/chat/completions"

        payload = {
            "model": config["model_name"],  # 使用配置的模型名称
            "messages": messages,
            "stream": config["is_stream"],  # 使用配置的流式设置
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
        if config["is_stream"]:
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
            "is_stream": config["is_stream"],
            "model_name": config["model_name"],
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
            "is_stream": config["is_stream"],
            "model_name": config["model_name"],
            "error": str(e)
        }


def process_dataset_files(config):
    """
    处理datasets文件夹下的所有txt文件（并发版本）
    """
    dataset_dir = "datasets"
    results_dir = "results"

    # 创建结果目录
    if not os.path.exists(results_dir):
        os.makedirs(results_dir)

    # 查找所有txt文件
    txt_files = glob.glob(os.path.join(dataset_dir, "*.txt"))

    if not txt_files:
        print(f"在 {dataset_dir} 目录下未找到txt文件")
        return

    print(f"找到 {len(txt_files)} 个txt文件")
    print(f"使用 {config['concurrent_workers']} 个并发工作线程")
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

    # 使用线程池并发处理
    with concurrent.futures.ThreadPoolExecutor(max_workers=config["concurrent_workers"]) as executor:
        # 提交所有任务
        future_to_file = {
            executor.submit(send_request, file_info, config): file_info
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
                    "error": str(e)
                }
                all_results["results"].append(error_result)

                print(f"[{completed_files}/{total_files}] ✗ 异常 - {filename}")
                print(f"  错误: {str(e)}")

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
    if config["concurrent_workers"] < 1:
        print("警告: 并发工作线程数不能小于1，已设置为1")
        config["concurrent_workers"] = 1

    if config["concurrent_workers"] > 50:
        print("警告: 并发工作线程数较大，可能会对服务器造成压力")

    if config["timeout"] < 1:
        print("警告: 超时时间不能小于1秒，已设置为60秒")
        config["timeout"] = 60

    # 确保模型名称不为空
    if not config["model_name"] or config["model_name"].strip() == "":
        print("警告: 模型名称不能为空，已设置为默认值 'ds_r1'")
        config["model_name"] = "ds_r1"

    return config


def main():
    """
    主函数
    """
    print("开始自动并发请求...")

    # 验证配置
    config = validate_config(CONFIG)

    print("配置信息:")
    for key, value in config.items():
        print(f"  {key}: {value}")

    start_time = time.time()
    process_dataset_files(config)
    end_time = time.time()

    total_time = end_time - start_time
    print(f"\n总执行时间: {total_time:.2f}秒")


if __name__ == "__main__":
    main()