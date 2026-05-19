"""
工具模块初始化
"""
from .helpers import count_chinese_words, text_hash, allowed_file, safe_filename
from .helpers import truncate_text, format_file_size, clean_old_upload_files, validate_text_content
from .decorators import login_required, guest_only, json_response
from .database import db
