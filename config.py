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
    # 新用户首次检测免费
    FIRST_DETECTION_FREE = os.getenv("FIRST_DETECTION_FREE", "true").lower() in ("1","true","yes")

    # 降低AI率 / 降低查重率 定价
    REDUCE_AI_FIRST_PRICE = float(os.getenv("REDUCE_AI_FIRST_PRICE", 2.0))         # 首次降低AI率 ¥2
    REDUCE_PLAGIARISM_FIRST_PRICE = float(os.getenv("REDUCE_PLAGIARISM_FIRST_PRICE", 2.0))  # 首次降查重 ¥2
    REDUCE_PRICE_PER_K = float(os.getenv("REDUCE_PRICE_PER_K", 0.5))                # 后续0.5元/千字
    REDUCE_MAX_CHARS = int(os.getenv("REDUCE_MAX_CHARS", 100000))                     # 单次最多100000字

    # 单次最大检测字数
    MAX_DETECTION_WORDS = int(os.getenv("MAX_DETECTION_WORDS", 100000))

    # 文件自动清理时间（秒）
    FILE_CLEANUP_SECONDS = int(os.getenv("FILE_CLEANUP_HOURS", 1)) * 3600

    # ==================== 充值额度配置（元/千字） ====================
    # 基础单价：0.5元/1000字
    CREDIT_PRICE_PER_K = float(os.getenv("CREDIT_PRICE_PER_K", 0.5))
    
    # 充值套餐（金额 → 字数）
    RECHARGE_PACKAGES = [
        {"amount": 5.0,   "words": 10000,  "label": "¥5 = 1万字",   "badge": "入门"},
        {"amount": 10.0,  "words": 20000,  "label": "¥10 = 2万字",  "badge": "实惠"},
        {"amount": 20.0,  "words": 50000,  "label": "¥20 = 5万字",  "badge": "推荐"},
        {"amount": 50.0,  "words": 150000, "label": "¥50 = 15万字", "badge": "超值"},
        {"amount": 100.0, "words": 300000, "label": "¥100 = 30万字","badge": "囤货"},
    ]

    # ==================== 会员配置 ====================
    MEMBER_MONTHLY_PRICE = float(os.getenv("MEMBER_MONTHLY_PRICE", 19.9))
    MEMBER_MONTHLY_QUOTA = int(os.getenv("MEMBER_MONTHLY_QUOTA", 50000))
    MEMBER_FREE_REWRITES = int(os.getenv("MEMBER_FREE_REWRITES", 3))  # 会员每月免费改写次数

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

    # 打印支付配置状态（部署调试用）
    @classmethod
    def print_payment_status(cls):
        import sys
        if cls.XORPAY_APP_ID and cls.XORPAY_API_SECRET:
            print(f"[PAYMENT] xorpay已配置 aid={cls.XORPAY_APP_ID}", file=sys.stderr)
        else:
            print(f"[PAYMENT] xorpay未配置, app_id={'SET' if cls.XORPAY_APP_ID else 'EMPTY'}, secret={'SET' if cls.XORPAY_API_SECRET else 'EMPTY'}", file=sys.stderr)

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
    ANNOUNCEMENT_TEXT = "🎉 首次双检测<strong>免费</strong>+加赠5000字！降低AI率首次仅<strong>¥2</strong>！邀请好友注册送<strong>10000字</strong>！"
    ANNOUNCEMENT_ENABLED = True

    # 广告位内容
    AD_SLOT_1_HTML = '<div class="ad-placeholder">广告位招租 | 联系：{email}</div>'.format(email=CONTACT_EMAIL)
    AD_SLOT_2_HTML = '<div class="ad-placeholder">广告位招租 | 联系：{email}</div>'.format(email=CONTACT_EMAIL)


# 导出配置实例
config = Config()
