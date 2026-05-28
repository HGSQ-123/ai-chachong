"""
============================================================
统一API客户端层
封装所有第三方API调用：超时重试、错误降级、密钥管理

设计原则：
1. 所有API调用统一走此模块，方便管理和切换
2. 真实API调用失败时自动降级为模拟算法，保证服务可用
3. 支持超时重试机制，避免单次故障影响用户体验
4. API密钥从config统一读取，方便更换供应商
============================================================
"""

import time
import requests
from config import config


class APIClient:
    """
    统一API客户端
    封装HTTP请求、超时重试、错误处理
    """

    # 默认超时（秒）
    DEFAULT_TIMEOUT = 30
    # 最大重试次数
    MAX_RETRIES = 2
    # 重试间隔（秒）
    RETRY_DELAY = 1

    @classmethod
    def call(cls, url: str, payload: dict, headers: dict = None,
             timeout: int = None, max_retries: int = None) -> tuple:
        """
        通用API调用方法（带超时重试）

        参数:
            url: API地址
            payload: 请求体(JSON)
            headers: 请求头
            timeout: 超时秒数
            max_retries: 最大重试次数

        返回:
            (success: bool, data: dict|None, error: str|None)
        """
        if timeout is None:
            timeout = cls.DEFAULT_TIMEOUT
        if max_retries is None:
            max_retries = cls.MAX_RETRIES

        default_headers = {
            "Content-Type": "application/json",
            "User-Agent": f"{config.SITE_NAME}/1.0",
        }
        if headers:
            default_headers.update(headers)

        last_error = None

        for attempt in range(max_retries + 1):
            try:
                response = requests.post(
                    url,
                    json=payload,
                    headers=default_headers,
                    timeout=timeout,
                )

                if response.status_code == 200:
                    import json
                    response.encoding = 'utf-8'
                    return True, json.loads(response.text), None
                elif response.status_code == 401:
                    return False, None, "API密钥无效，请检查配置"
                elif response.status_code == 429:
                    # 频率限制，等待后重试
                    if attempt < max_retries:
                        time.sleep(cls.RETRY_DELAY * (attempt + 1))
                        continue
                    return False, None, "API调用频率超限，请稍后重试"
                elif response.status_code >= 500:
                    # 服务端错误，可重试
                    last_error = f"API服务异常(HTTP {response.status_code})"
                    if attempt < max_retries:
                        time.sleep(cls.RETRY_DELAY * (attempt + 1))
                        continue
                    return False, None, last_error
                else:
                    return False, None, f"API返回异常状态码: {response.status_code}"

            except requests.exceptions.Timeout:
                last_error = "API调用超时"
                if attempt < max_retries:
                    time.sleep(cls.RETRY_DELAY)
                    continue
                return False, None, last_error

            except requests.exceptions.ConnectionError:
                last_error = "无法连接到API服务器"
                if attempt < max_retries:
                    time.sleep(cls.RETRY_DELAY)
                    continue
                return False, None, last_error

            except Exception as e:
                last_error = f"API调用异常: {str(e)}"
                return False, None, last_error

        return False, None, last_error


# ============================================================
# DeepSeek API 客户端（AI降重改写）
# 官网: https://platform.deepseek.com
# 价格: ¥1/百万tokens（极低成本）
# ============================================================

class DeepSeekClient:
    """DeepSeek大模型API客户端"""

    @classmethod
    def is_configured(cls) -> bool:
        """检查是否已配置API密钥"""
        return bool(config.DEEPSEEK_API_KEY)

    @classmethod
    def chat(cls, messages: list, temperature: float = 0.7,
             max_tokens: int = 4096) -> tuple:
        """
        调用DeepSeek Chat API

        参数:
            messages: 对话消息列表 [{"role":"user","content":"..."}]
            temperature: 生成温度(0-2)
            max_tokens: 最大生成token数

        返回:
            (success: bool, content: str|None, error: str|None)
        """
        if not cls.is_configured():
            return False, None, "DeepSeek API密钥未配置"

        success, data, error = APIClient.call(
            url="https://api.deepseek.com/v1/chat/completions",
            payload={
                "model": "deepseek-chat",
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            headers={
                "Authorization": f"Bearer {config.DEEPSEEK_API_KEY}",
            },
            timeout=60,
            max_retries=2,
        )

        if success and data:
            try:
                content = data["choices"][0]["message"]["content"]
                return True, content, None
            except (KeyError, IndexError) as e:
                return False, None, f"解析DeepSeek响应失败: {str(e)}"

        return False, None, error

    @classmethod
    def rewrite(cls, text: str, action: str = "rewrite") -> tuple:
        """
        AI降重改写（DeepSeek驱动）

        参数:
            text: 原文
            action: rewrite(降重)/polish(润色)/fix(修正)/optimize(优化)

        返回:
            (success: bool, result_text: str|None, suggestions: list, error: str|None)
        """
        # 为不同操作构建不同的提示词
        prompts = {
            "rewrite": f"""你是一位专业的学术论文降重改写专家。请对以下文本进行深度改写，要求：

1. 保持原文的学术含义和核心观点不变
2. 使用同义替换、句式重组、语序调整等方式降低重复率
3. 保持学术语言的严谨性和专业性
4. 不要添加原文没有的新观点
5. 直接输出改写后的文本，不要添加任何说明

原文：
{text}

改写稿：""",

            "polish": f"""你是一位专业的学术论文润色专家。请对以下文本进行语句润色，要求：

1. 优化词语搭配和语句流畅度
2. 提升文本的专业性和可读性
3. 保持原意不变
4. 直接输出润色后的文本

原文：
{text}

润色稿：""",

            "fix": f"""你是一位专业的语言文字专家。请检查并修正以下文本中的语病，要求：

1. 修正常见语法错误
2. 修正搭配不当
3. 修正逻辑混乱的表述
4. 保持原意不变
5. 直接输出修正后的文本

原文：
{text}

修正稿：""",

            "optimize": f"""你是一位专业的学术写作指导专家。请优化以下文本的句式结构，要求：

1. 拆分过长的句子（超过50字的句子需要拆分）
2. 提升句式多样性（避免连续使用相同句式）
3. 保持学术风格
4. 保持原意不变
5. 直接输出优化后的文本

原文：
{text}

优化稿：""",
        }

        system_prompt = prompts.get(action, prompts["rewrite"])

        success, content, error = cls.chat(
            messages=[
                {"role": "user", "content": system_prompt}
            ],
            temperature=0.8,
            max_tokens=4096,
        )

        if success and content:
            suggestions = [
                "AI改写完成，建议人工复核专业术语准确性",
                "改写后可再次检测确认降重效果",
            ]
            return True, content.strip(), suggestions, None

        return False, None, [], error

    @classmethod
    def detect_ai(cls, text: str) -> tuple:
        """
        AI生成率检测（DeepSeek驱动）

        返回:
            (success: bool, result: dict|None, error: str|None)
            result: {"ai_score": float, "human_score": float, "reasoning": str}
        """
        prompt = f"""你是一个专业的AI内容检测专家。请分析以下文本是否由AI大模型生成。

详细的评估标准：
1. 句式多样性：真人写作句式长短不一，AI生成的句式往往过于均匀
2. 用词习惯：AI常使用"首先/其次/最后"、"值得注意的是"、"综上所述"等机械过渡词
3. 情感色彩：真人文章通常带有主观情绪和个人风格，AI生成的中性客观
4. 细节丰富度：真人写作常包含具体数字、案例、个人经历，AI容易泛泛而谈
5. 逻辑跳跃：真人思维常有跳跃和联想，AI逻辑过于工整线性
6. 段落结构：AI生成的段落长度往往高度一致

请返回JSON：{{"ai_score":0到100的AI生成概率数字,"reasoning":"30字以内分析","details":["具体问题1","具体问题2"]}}

文本：
{text[:8000]}"""

        success, content, error = cls.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1, max_tokens=500
        )
        if success and content:
            try:
                import json, re
                json_match = re.search(r'\{[^{}]*\}', content)
                if json_match:
                    result = json.loads(json_match.group())
                    result["method"] = "deepseek"
                    result["confidence"] = "high" if abs(result.get("ai_score", 50) - 50) > 25 else "medium"
                    return True, result, None
            except (json.JSONDecodeError, KeyError):
                pass
        return False, None, error or "DeepSeek检测失败"

    @classmethod
    def check_plagiarism(cls, text: str) -> tuple:
        """
        全网查重检测（DeepSeek驱动）

        返回:
            (success: bool, result: dict|None, error: str|None)
            result: {"plagiarism_score": float, "original_score": float, "reasoning": str}
        """
        prompt = f"""你是一个专业论文查重专家，参考PaperPass的查重标准分析以下文本。

PaperPass原理参考：基于学术文献和网络资源指纹比对，检测连续相似片段，区分合理引用与抄袭拼接。

分析维度：
1. 是否存在"随着...发展""在...背景下""近年来"等高频套路开头
2. 核心观点是否有独创性，还是常见论点的重新排列
3. 专业术语使用是否恰当（生硬堆砌 vs 自然融入）
4. 段落逻辑是否自洽（拼接文章往往段落间逻辑断裂）

返回JSON：{{"plagiarism_score":0到100的重复率,"original_score":100减重复率,"reasoning":"30字内分析","risk_level":"低/中/高","suggestions":["建议1","建议2"]}}

文本：
{text[:8000]}"""

        success, content, error = cls.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1, max_tokens=500
        )
        if success and content:
            try:
                import json, re
                json_match = re.search(r'\{[^{}]*\}', content)
                if json_match:
                    result = json.loads(json_match.group())
                    result["method"] = "deepseek"
                    return True, result, None
            except (json.JSONDecodeError, KeyError):
                pass
        return False, None, error or "DeepSeek查重失败"


# ============================================================
# AI检测API客户端（GPTZero / Copyleaks 兼容）
# 支持多种AI检测服务商，通过.env切换
# ============================================================

class AIDetectionAPIClient:
    """AI生成文本检测 - 真实API客户端"""

    @classmethod
    def is_configured(cls) -> bool:
        """检查是否配置了AI检测API"""
        return bool(config.AI_DETECTION_API_KEY and config.AI_DETECTION_API_URL)

    @classmethod
    def detect(cls, text: str) -> tuple:
        """
        调用第三方AI检测API

        兼容 GPTZero / Copyleaks / Originality.ai 等主流服务
        只需在.env填入对应的API URL和密钥即可
        """
        if not cls.is_configured():
            return False, None, "AI检测API未配置"

        # 通用调用方式（兼容大多数AI检测API）
        success, data, error = APIClient.call(
            url=config.AI_DETECTION_API_URL,
            payload={
                "text": text,
                "language": "zh",  # 指定中文检测
            },
            headers={
                "Authorization": f"Bearer {config.AI_DETECTION_API_KEY}",
            },
            timeout=30,
            max_retries=2,
        )

        if success and data:
            # 尝试从不同API的响应格式中提取数据
            # GPTZero格式: {"documents":[{"predicted_class":"ai","confidence":0.95}]}
            # Copyleaks格式: {"results":[{"ai":{"probability":95}}]}
            # Originality格式: {"score":{"original":0.85,"ai":0.15}}

            try:
                ai_score = None
                details = []

                # 尝试GPTZero格式
                if "documents" in data:
                    doc = data["documents"][0]
                    ai_score = doc.get("predicted_class") == "ai" and doc.get("confidence", 0) * 100
                    if ai_score is None:
                        ai_score = doc.get("ai_score", 0)
                    details = [{"label": "AI概率", "value": f"{ai_score}%"}]

                # 尝试Copyleaks格式
                elif "results" in data:
                    result = data["results"][0]
                    if "ai" in result:
                        ai_score = result["ai"].get("probability", 0)
                    elif "score" in result:
                        ai_score = result.get("score", 0)
                    details = [{"label": "AI检测", "value": f"{ai_score}%"}]

                # 尝试Originality格式
                elif "score" in data:
                    ai_score = data["score"].get("ai", 0) * 100
                    details = [{"label": "AI占比", "value": f"{ai_score}%"}]

                # 通用格式
                elif "ai_score" in data:
                    ai_score = data["ai_score"]
                    details = data.get("details", [])

                if ai_score is not None:
                    return True, {
                        "ai_score": round(float(ai_score), 1),
                        "human_score": round(100 - float(ai_score), 1),
                        "confidence": data.get("confidence", "high"),
                        "details": details or data.get("details", []),
                        "suggestions": data.get("suggestions", []),
                        "method": "api",
                    }, None

                return False, None, "无法解析API返回数据格式"

            except (KeyError, IndexError, TypeError) as e:
                return False, None, f"解析AI检测结果失败: {str(e)}"

        return False, None, error


# ============================================================
# 查重API客户端（第三方公开API兼容）
# ============================================================

class PlagiarismAPIClient:
    """全网查重 - 真实API客户端"""

    @classmethod
    def is_configured(cls) -> bool:
        """检查是否配置了查重API"""
        return bool(config.PLAGIARISM_API_KEY and config.PLAGIARISM_API_URL)

    @classmethod
    def check(cls, text: str) -> tuple:
        """
        调用第三方查重API

        兼容主流查重API的返回格式
        """
        if not cls.is_configured():
            return False, None, "查重API未配置"

        success, data, error = APIClient.call(
            url=config.PLAGIARISM_API_URL,
            payload={
                "text": text,
                "language": "zh",
            },
            headers={
                "Authorization": f"Bearer {config.PLAGIARISM_API_KEY}",
            },
            timeout=60,
            max_retries=2,
        )

        if success and data:
            try:
                # 尝试多种API返回格式
                matched_segments = data.get("matches", []) or data.get("matched_segments", [])
                sources = data.get("sources", [])
                plagiarism_score = data.get("plagiarism_score", 0) or data.get("similarity", 0)

                # 如果返回的是百分比
                if plagiarism_score < 1:
                    plagiarism_score *= 100

                return True, {
                    "plagiarism_score": round(float(plagiarism_score), 1),
                    "original_score": round(100 - float(plagiarism_score), 1),
                    "matched_segments": matched_segments,
                    "sources": sources,
                    "suggestions": data.get("suggestions", []),
                    "method": "api",
                }, None

            except (KeyError, TypeError) as e:
                return False, None, f"解析查重结果失败: {str(e)}"

        return False, None, error
