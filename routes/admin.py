"""
============================================================
DeepSeek API 快速配置与测试工具
在浏览器访问 /admin/deepseek-test 即可测试连接
============================================================
"""

from flask import Blueprint, jsonify, request, render_template
from config import config
from utils.decorators import login_required

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/deepseek-test")
@login_required
def deepseek_test_page():
    """DeepSeek连接测试页面"""
    return render_template("admin/deepseek_test.html", config=config)


@admin_bp.route("/api/deepseek-test", methods=["POST"])
@login_required
def api_deepseek_test():
    """
    测试DeepSeek连接
    发送一条简短测试消息，验证API密钥是否有效
    """
    from services.api_client import DeepSeekClient

    if not DeepSeekClient.is_configured():
        return jsonify({
            "success": False,
            "message": "DeepSeek API密钥未配置，请在 .env 中设置 DEEPSEEK_API_KEY",
            "help": "前往 https://platform.deepseek.com 注册并获取密钥"
        })

    success, content, error = DeepSeekClient.chat(
        messages=[{"role": "user", "content": "请用中文回复：你好，世界！"}],
        max_tokens=50
    )

    if success:
        return jsonify({
            "success": True,
            "message": "DeepSeek连接成功！",
            "response": content,
            "config_status": "✅ 已配置",
        })
    else:
        return jsonify({
            "success": False,
            "message": f"DeepSeek连接失败：{error}",
            "config_status": "⚠️ 密钥可能无效",
            "help": "请检查 .env 中 DEEPSEEK_API_KEY 是否正确"
        })


@admin_bp.route("/api/config-status")
@login_required
def api_config_status():
    """查看所有API配置状态"""
    from services.api_client import DeepSeekClient, AIDetectionAPIClient, PlagiarismAPIClient
    from services.payment import PaymentService

    return jsonify({
        "payments": {
            "channel": PaymentService.get_active_channel(),
            "xorpay_configured": bool(config.XORPAY_APP_ID and config.XORPAY_API_SECRET),
        },
        "deepseek": {
            "configured": DeepSeekClient.is_configured(),
            "label": "AI降重改写",
            "price": f"¥{config.CREDIT_PRICE_PER_K}/千字",
        },
        "ai_detection": {
            "configured": AIDetectionAPIClient.is_configured(),
            "label": "AI生成检测",
            "price": f"¥{config.CREDIT_PRICE_PER_K}/千字",
        },
        "plagiarism": {
            "configured": PlagiarismAPIClient.is_configured(),
            "label": "全网查重",
            "price": f"¥{config.CREDIT_PRICE_PER_K}/千字",
        },
        "pricing": {
            "free_quota": config.FREE_QUOTA_WORDS,
            "member_price": config.MEMBER_MONTHLY_PRICE,
            "credit_price": config.CREDIT_PRICE_PER_K,
            "packages": config.RECHARGE_PACKAGES,
        }
    })
