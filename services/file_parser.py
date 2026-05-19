"""
文件解析服务
支持Word(.docx)和PDF文件的内容提取

注意：
- 用户上传的文件仅在检测期间暂存，检测完成后自动删除
- 不持久化存储用户文稿，保护隐私
"""

import os
import traceback
from config import config


class FileParser:
    """
    文件解析器
    支持格式：.docx (Word), .pdf (PDF), .txt (纯文本)
    """

    # 支持的文件类型
    SUPPORTED_EXTENSIONS = {"docx", "pdf", "txt", "doc"}

    @classmethod
    def parse(cls, filepath: str, original_filename: str) -> dict:
        """
        解析上传的文件，提取文本内容

        参数:
            filepath: 文件的临时存储路径
            original_filename: 原始文件名

        返回:
            dict: {
                "success": bool,
                "text": str,          # 提取的文本内容
                "word_count": int,    # 字数和
                "error": str,         # 错误信息（如有）
                "file_type": str,     # 文件类型
            }
        """
        # 获取文件扩展名
        ext = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else ""

        if ext not in cls.SUPPORTED_EXTENSIONS:
            return {
                "success": False,
                "text": "",
                "word_count": 0,
                "error": f"不支持的文件格式：.{ext}，请上传 .docx / .pdf / .txt 文件",
                "file_type": ext,
            }

        try:
            if ext == "docx":
                return cls._parse_docx(filepath, original_filename)
            elif ext == "pdf":
                return cls._parse_pdf(filepath, original_filename)
            elif ext in ("txt", "doc"):
                return cls._parse_txt(filepath, original_filename)
        except Exception as e:
            traceback.print_exc()
            return {
                "success": False,
                "text": "",
                "word_count": 0,
                "error": f"文件解析失败：{str(e)}，请确认文件未损坏",
                "file_type": ext,
            }

    @classmethod
    def _parse_docx(cls, filepath: str, filename: str) -> dict:
        """
        解析Word文档(.docx)
        使用python-docx库提取段落文本
        """
        try:
            from docx import Document
        except ImportError:
            return {
                "success": False, "text": "", "word_count": 0,
                "error": "缺少python-docx依赖，请运行: pip install python-docx",
                "file_type": "docx",
            }

        doc = Document(filepath)
        paragraphs = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                paragraphs.append(text)

        # 也提取表格中的文本
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    text = cell.text.strip()
                    if text:
                        paragraphs.append(text)

        full_text = "\n".join(paragraphs)

        if not full_text.strip():
            return {
                "success": False, "text": "", "word_count": 0,
                "error": "文档内容为空，请检查文件",
                "file_type": "docx",
            }

        from utils.helpers import count_chinese_words
        word_count = count_chinese_words(full_text)

        return {
            "success": True,
            "text": full_text,
            "word_count": word_count,
            "error": "",
            "file_type": "docx",
        }

    @classmethod
    def _parse_pdf(cls, filepath: str, filename: str) -> dict:
        """
        解析PDF文档
        使用PyPDF2库提取文本
        """
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            return {
                "success": False, "text": "", "word_count": 0,
                "error": "缺少PyPDF2依赖，请运行: pip install PyPDF2",
                "file_type": "pdf",
            }

        try:
            reader = PdfReader(filepath)
            pages_text = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text.strip())

            full_text = "\n".join(pages_text)

            if not full_text.strip():
                return {
                    "success": False, "text": "", "word_count": 0,
                    "error": "PDF内容为空或为扫描版图片PDF（无法提取文字），请上传可选中文字的PDF",
                    "file_type": "pdf",
                }

            from utils.helpers import count_chinese_words
            word_count = count_chinese_words(full_text)

            return {
                "success": True,
                "text": full_text,
                "word_count": word_count,
                "error": "",
                "file_type": "pdf",
            }
        except Exception as e:
            return {
                "success": False, "text": "", "word_count": 0,
                "error": f"PDF解析异常：{str(e)}",
                "file_type": "pdf",
            }

    @classmethod
    def _parse_txt(cls, filepath: str, filename: str) -> dict:
        """
        解析纯文本文件(.txt)
        尝试多种编码方式读取
        """
        # 尝试不同编码读取
        encodings = ["utf-8", "gbk", "gb2312", "latin-1"]
        full_text = ""

        for encoding in encodings:
            try:
                with open(filepath, "r", encoding=encoding) as f:
                    full_text = f.read()
                break
            except (UnicodeDecodeError, UnicodeError):
                continue

        if not full_text.strip():
            return {
                "success": False, "text": "", "word_count": 0,
                "error": "文件内容为空或编码不支持",
                "file_type": "txt",
            }

        from utils.helpers import count_chinese_words
        word_count = count_chinese_words(full_text)

        return {
            "success": True,
            "text": full_text,
            "word_count": word_count,
            "error": "",
            "file_type": "txt",
        }
