"""
检测记录与计费记录数据模型
"""

from datetime import datetime
import json


class DetectionRecord:
    """
    检测记录模型
    - text_hash: 原文哈希（用于去重，不存储原文）
    - word_count: 检测字数
    - ai_score: AI生成率得分（0-100）
    - plagiarism_score: 重复率得分（0-100）
    - report_data: 完整报告JSON数据
    - file_name: 上传的原始文件名（如有）
    """

    def __init__(self, user_id, text_hash, word_count, ai_score, plagiarism_score,
                 report_data, record_id=None, file_name=None, status="completed",
                 created_at=None):
        self.id = record_id
        self.user_id = user_id
        self.text_hash = text_hash
        self.word_count = word_count
        self.ai_score = ai_score
        self.plagiarism_score = plagiarism_score
        self.report_data = report_data  # dict类型，存储完整报告
        self.file_name = file_name
        self.status = status  # pending, processing, completed, failed
        self.created_at = created_at or datetime.now()

    def to_dict(self) -> dict:
        """序列化为字典"""
        report = self.report_data
        if isinstance(report, str):
            try:
                report = json.loads(report)
            except (json.JSONDecodeError, TypeError):
                report = {}

        return {
            "id": self.id,
            "user_id": self.user_id,
            "word_count": self.word_count,
            "ai_score": round(self.ai_score, 1) if self.ai_score else 0,
            "plagiarism_score": round(self.plagiarism_score, 1) if self.plagiarism_score else 0,
            "original_score": round(100 - max(self.ai_score or 0, self.plagiarism_score or 0), 1),
            "report_data": report,
            "file_name": self.file_name,
            "status": self.status,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else None,
        }


class BillingRecord:
    """
    计费记录模型
    - amount: 消费金额（元）
    - word_count: 购买/消费的字数
    - transaction_type: free_quota(免费额度) / paid(付费) / member(会员额度) / recharge(充值)
    """

    def __init__(self, user_id, amount, word_count, transaction_type,
                 record_id=None, description="", created_at=None):
        self.id = record_id
        self.user_id = user_id
        self.amount = amount
        self.word_count = word_count
        self.transaction_type = transaction_type
        self.description = description
        self.created_at = created_at or datetime.now()

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "amount": self.amount,
            "word_count": self.word_count,
            "transaction_type": self.transaction_type,
            "description": self.description,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else None,
        }
