"""
AI生成率检测服务
判断文本是否由AI撰写，返回AI生成概率得分

设计说明：
- 如果配置了第三方API密钥，则调用真实API
- 如果未配置，则使用内置模拟算法（基于文本特征分析）
- 模拟算法仅供演示，生产环境请配置真实API
"""

import re
import random
import hashlib
from config import config


class AIDetector:
    """
    AI生成率检测器
    通过分析文本的语言特征来判断是否由AI生成
    """

    # AI生成文本的常见特征词（中文）
    AI_INDICATOR_PATTERNS_CN = [
        "总而言之", "值得注意的是", "不可否认", "综上所述",
        "首先", "其次", "最后", "此外", "另外", "与此同时",
        "从某种角度来说", "在一定程度上", "不可忽视的是",
        "需要强调的是", "应该指出", "必须承认",
        "随着.*的发展", "在.*背景下", "基于.*考虑",
        "不仅.*而且", "既.*又", "一方面.*另一方面",
    ]

    # AI生成文本的常见特征词（英文）
    AI_INDICATOR_PATTERNS_EN = [
        "in conclusion", "it is important to note", "furthermore",
        "moreover", "additionally", "on the other hand",
        "it is worth noting", "as a result", "consequently",
        "in summary", "to summarize", "in other words",
        "it can be argued that", "there is no doubt that",
    ]

    @classmethod
    def detect(cls, text: str) -> dict:
        """
        检测文本的AI生成率

        参数:
            text: 待检测的文本内容

        返回:
            dict: {
                "ai_score": float,        # AI生成率得分 0-100
                "human_score": float,     # 人工撰写率 0-100
                "confidence": str,        # 置信度等级: high/medium/low
                "details": list,          # 详细分析结果
                "suggestions": list,      # 优化建议
                "method": str,            # 检测方式: api/simulation
            }
        """
        # 优先使用第三方真实API
        from services.api_client import AIDetectionAPIClient
        if AIDetectionAPIClient.is_configured():
            success, result, error = AIDetectionAPIClient.detect(text)
            if success and result:
                return result
            # API失败，降级为模拟算法（附带降级提示）
            sim_result = cls._detect_via_simulation(text)
            sim_result["api_error"] = error
            return sim_result

        # 否则使用内置模拟算法
        return cls._detect_via_simulation(text)


    @classmethod
    def _detect_via_simulation(cls, text: str) -> dict:
        """
        内置模拟AI检测算法
        基于文本特征分析，检测AI生成的可能性

        分析维度：
        1. AI标志性词汇密度
        2. 句式复杂度
        3. 段落结构规律性
        4. 标点符号使用模式
        5. 词汇多样性
        """
        if not text or len(text) < 50:
            return {
                "ai_score": 0,
                "human_score": 100,
                "confidence": "low",
                "details": [{"type": "warning", "content": "文本过短，检测结果仅供参考"}],
                "suggestions": ["建议提交不少于50字的文本以获得更准确的检测结果"],
                "method": "simulation",
            }

        # ---- 维度1：AI标志性词汇密度 ----
        ai_pattern_count = 0
        text_lower = text.lower()
        for pattern in cls.AI_INDICATOR_PATTERNS_CN:
            matches = re.findall(pattern, text)
            ai_pattern_count += len(matches)
        for pattern in cls.AI_INDICATOR_PATTERNS_EN:
            matches = re.findall(pattern, text_lower)
            ai_pattern_count += len(matches)

        total_sentences = max(1, len(re.split(r'[。！？.!?\n]', text)))
        ai_pattern_density = ai_pattern_count / total_sentences
        pattern_score = min(40, ai_pattern_density * 30)

        # ---- 维度2：句式复杂度 ----
        sentences = [s.strip() for s in re.split(r'[。！？.!?\n]', text) if s.strip()]
        if len(sentences) >= 3:
            sentence_lengths = [len(s) for s in sentences]
            avg_length = sum(sentence_lengths) / len(sentence_lengths)
            # AI倾向于生成长度均匀的句子
            if len(sentence_lengths) > 1:
                variance = sum((l - avg_length) ** 2 for l in sentence_lengths) / len(sentence_lengths)
                # 方差越小，越可能是AI写的
                if variance < 100:
                    uniformity_score = 20
                elif variance < 400:
                    uniformity_score = 12
                elif variance < 900:
                    uniformity_score = 6
                else:
                    uniformity_score = 2
            else:
                uniformity_score = 10
        else:
            uniformity_score = 5

        # ---- 维度3：词汇多样性 ----
        words = re.findall(r'[\u4e00-\u9fff]', text)
        if len(words) > 20:
            unique_ratio = len(set(words)) / len(words)
            # AI文本词汇多样性通常较低（0.3-0.5），人类写作通常更高
            if unique_ratio < 0.25:
                diversity_score = 20
            elif unique_ratio < 0.35:
                diversity_score = 14
            elif unique_ratio < 0.45:
                diversity_score = 8
            else:
                diversity_score = 2
        else:
            diversity_score = 10

        # ---- 维度4：标点符号模式 ----
        comma_count = text.count("，") + text.count(",")
        period_count = text.count("。") + text.count(".")
        # AI倾向使用更多逗号
        if period_count > 0:
            comma_ratio = comma_count / period_count
            if comma_ratio > 4:
                punctuation_score = 10
            elif comma_ratio > 2.5:
                punctuation_score = 6
            else:
                punctuation_score = 2
        else:
            punctuation_score = 5

        # ---- 综合评分 ----
        total_score = pattern_score + uniformity_score + diversity_score + punctuation_score

        # 基于文本哈希添加一些随机性（模拟不同文本的差异）
        text_seed = int(hashlib.md5(text[:200].encode()).hexdigest()[:8], 16) % 15
        total_score += text_seed

        # 限制在0-100之间
        ai_score = min(95, max(5, total_score))
        human_score = 100 - ai_score

        # 置信度判定
        if len(text) > 500:
            confidence = "high"
        elif len(text) > 200:
            confidence = "medium"
        else:
            confidence = "low"

        # 生成详细分析
        details = [
            {"type": "metric", "label": "AI标志词汇密度", "value": f"{ai_pattern_density:.2f}", "max": "1.0"},
            {"type": "metric", "label": "句式均匀度", "value": "高" if uniformity_score > 10 else "中" if uniformity_score > 5 else "低", "max": "-"},
            {"type": "metric", "label": "词汇多样性", "value": f"{unique_ratio:.2%}" if len(words) > 20 else "样本不足", "max": "-"},
            {"type": "metric", "label": "标点模式分析", "value": "AI倾向" if punctuation_score > 5 else "正常", "max": "-"},
        ]

        # 生成建议
        suggestions = []
        if ai_score > 60:
            suggestions.append("本文AI生成可能性较高，建议增加个人观点和实际案例")
            suggestions.append("可尝试使用AI降重改写功能降低AI痕迹")
        elif ai_score > 30:
            suggestions.append("部分段落可能由AI辅助生成，建议人工润色")
            suggestions.append("增加个人独特表达可进一步提升原创性")
        else:
            suggestions.append("文本整体呈现较高的原创特征")
        suggestions.append("检测结果仅供参考，最终以学校官方系统为准")

        return {
            "ai_score": round(ai_score, 1),
            "human_score": round(human_score, 1),
            "confidence": confidence,
            "details": details,
            "suggestions": suggestions,
            "method": "simulation",
        }
