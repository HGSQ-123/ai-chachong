"""
工具函数模块
包含文本处理、哈希计算、文件验证等通用功能
"""

import hashlib
import re
import os
from datetime import datetime


def count_chinese_words(text: str) -> int:
    """
    统计中文字数（按中文字符+英文单词计算）
    中文：每个汉字算1字
    英文：每个单词算1字
    数字/标点：不计入字数
    """
    if not text or not isinstance(text, str):
        return 0
    # 统计中文字符
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    # 统计英文单词
    english_words = len(re.findall(r'[a-zA-Z]+', text))
    return chinese_chars + english_words


def text_hash(text: str) -> str:
    """计算文本的SHA256哈希值（用于去重，不存储原文）"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def allowed_file(filename: str, allowed_extensions: set) -> bool:
    """
    验证上传文件扩展名是否合法
    """
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in allowed_extensions


def safe_filename(filename: str) -> str:
    """
    生成安全的文件名（保留扩展名，添加时间戳防止冲突）
    """
    ext = filename.rsplit(".", 1)[1].lower() if "." in filename else "txt"
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    safe_name = re.sub(r'[^\w\.\-]', '_', filename.rsplit(".", 1)[0])
    return f"{safe_name}_{timestamp}.{ext}"


def truncate_text(text: str, max_length: int = 500) -> str:
    """截断文本用于预览"""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "...（内容已截断）"


def format_file_size(size_bytes: int) -> str:
    """格式化文件大小显示"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def clean_old_upload_files(upload_folder: str, max_age_hours: int = 1):
    """
    清理过期的上传文件
    检测完成后自动删除用户上传的文稿，保护隐私
    """
    if not os.path.exists(upload_folder):
        return

    now = datetime.now()
    for filename in os.listdir(upload_folder):
        filepath = os.path.join(upload_folder, filename)
        if not os.path.isfile(filepath):
            continue
        # 检查文件修改时间
        mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
        age_hours = (now - mtime).total_seconds() / 3600
        if age_hours > max_age_hours:
            try:
                os.remove(filepath)
            except OSError:
                pass  # 文件可能正在使用中，跳过


def validate_text_content(text: str) -> tuple:
    """
    验证文本内容是否合法
    返回 (is_valid, error_message)
    """
    if not text or not text.strip():
        return False, "请输入要检测的文本内容"

    # 检测违规内容关键词（示例，可扩展）
    sensitive_keywords = []  # 可在配置中添加需要拦截的关键词
    text_lower = text.lower()
    for keyword in sensitive_keywords:
        if keyword.lower() in text_lower:
            return False, f"检测到不合规内容，请检查后重试"

    return True, ""
