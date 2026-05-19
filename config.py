"""
============================================================
配置中心 - 所有可调参数集中管理
修改此文件即可一键调整价格、额度、API等所有配置
============================================================
"""

import os

# 安全加载.env（不存在则跳过，使用环境变量）
try:
    from dotenv import load_dotenv
    load_dotenv()
except (ImportError, Exception):
    pass  # 生产环境通过Render dashboard设置环境变量


class Config:
    """应用主配置类"""

    # ==================== Flask基础配置 ====================
    SECRET_KEY = os.getenv("SECRET_KEY", "default-secret-key-change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///data/detection.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False  # 关闭追踪以节省内存

    # ==================== 文件上传配置 ====================
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_UPLOAD_SIZE_MB", 20)) * 1024 * 1024  # 字节
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
    ALLOWED_EXTENSIONS = {"doc", "docx", "pdf", "txt"}  # 允许上传的文件类型

    # ==================== 业务配置 ====================
    # 新用户免费额度（字数）
    FREE_QUOTA_WORDS = int(os.getenv("FREE_QUOTA_WORDS", 5000))

    # 单次最大检测字数
    MAX_DETECTION_WORDS = int(os.getenv("MAX_DETECTION_WORDS", 50000))

    # 文件自动清理时间（秒）
    FILE_CLEANUP_SECONDS = int(os.getenv("FILE_CLEANUP_HOURS", 1)) * 3600

    # ==================== 阶梯价格配置（元/千字） ====================
    PRICING_TIERS = [
        {
            "max_words": int(os.getenv("PRICE_TIER_1_LIMIT", 5000)),
            "price_per_k": float(os.getenv("PRICE_TIER_1_PRICE", 1.5)),
            "label": "5,000字以内",
        },
        {
            "max_words": int(os.getenv("PRICE_TIER_2_LIMIT", 20000)),
            "price_per_k": float(os.getenv("PRICE_TIER_2_PRICE", 1.2)),
            "label": "5,001-20,000字",
        },
        {
            "max_words": float("inf"),
            "price_per_k": float(os.getenv("PRICE_TIER_3_PRICE", 0.9)),
            "label": "20,000字以上",
        },
    ]

    # AI检测单独定价（仅AI生成率，不含查重）
    AI_DETECTION_PRICE = float(os.getenv("AI_DETECTION_PRICE", 1.4))

    # AI降重改写定价
    AI_REWRITE_PRICE = float(os.getenv("AI_REWRITE_PRICE", 5.0))

    # ==================== 会员配置 ====================
    MEMBER_MONTHLY_PRICE = float(os.getenv("MEMBER_MONTHLY_PRICE", 19.9))
    MEMBER_MONTHLY_QUOTA = int(os.getenv("MEMBER_MONTHLY_QUOTA", 50000))

    # ==================== 第三方API配置 ====================
    # DeepSeek大模型（AI降重改写）- 留空则使用模拟算法
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

    # AI检测API（留空则使用内置模拟算法）
    AI_DETECTION_API_KEY = os.getenv("AI_DETECTION_API_KEY", "")
    AI_DETECTION_API_URL = os.getenv("AI_DETECTION_API_URL", "")

    # 全网查重API（留空则使用内置模拟算法）
    PLAGIARISM_API_KEY = os.getenv("PLAGIARISM_API_KEY", "")
    PLAGIARISM_API_URL = os.getenv("PLAGIARISM_API_URL", "")

    # ==================== 支付配置 ====================
    # xorpay 个人支付（优先，无需营业执照）
    XORPAY_APP_ID = os.getenv("XORPAY_APP_ID", "")
    XORPAY_API_SECRET = os.getenv("XORPAY_API_SECRET", "")

    # 微信支付（可选，需营业执照）
    WECHAT_APP_ID = os.getenv("WECHAT_APP_ID", "")
    WECHAT_MCH_ID = os.getenv("WECHAT_MCH_ID", "")
    WECHAT_API_KEY = os.getenv("WECHAT_API_KEY", "")

    # 支付宝（可选，需营业执照）
    ALIPAY_APP_ID = os.getenv("ALIPAY_APP_ID", "")
    ALIPAY_PRIVATE_KEY = os.getenv("ALIPAY_PRIVATE_KEY", "")
    ALIPAY_PUBLIC_KEY = os.getenv("ALIPAY_PUBLIC_KEY", "")

    # ==================== 站点信息 ====================
    SITE_NAME = os.getenv("SITE_NAME", "AI查重检测平台")
    SITE_DESCRIPTION = os.getenv("SITE_DESCRIPTION", "专业AI生成率检测与论文重复率查重平台")
    SITE_DOMAIN = os.getenv("SITE_DOMAIN", "http://localhost:5000")
    CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "support@aichachong.com")

    # ==================== 广告位配置 ====================
    # 公告内容（支持HTML）
    ANNOUNCEMENT_TEXT = "🎉 新用户注册即送<strong>5000字</strong>免费检测额度！邀请好友再送1000字！"
    ANNOUNCEMENT_ENABLED = True

    # 广告位内容
    AD_SLOT_1_HTML = '<div class="ad-placeholder">广告位招租 | 联系：{email}</div>'.format(email=CONTACT_EMAIL)
    AD_SLOT_2_HTML = '<div class="ad-placeholder">广告位招租 | 联系：{email}</div>'.format(email=CONTACT_EMAIL)


# 导出配置实例
config = Config()
