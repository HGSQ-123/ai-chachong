"""
============================================================
DeepSeek API 快速配置与测试工具
在浏览器访问 /admin/deepseek-test 即可测试连接
============================================================
"""

from flask import Blueprint, jsonify, request, render_template
from config import config
from utils.decorators import login_required
from utils.database import db

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


@admin_bp.route("/analytics")
def analytics_page():
    """数据统计页面"""
    return render_template("admin/analytics.html", config=config)


@admin_bp.route("/api/analytics")
def api_analytics():
    """数据统计API"""
    from utils.database import db
    from datetime import datetime, timedelta
    
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    month_start = now.replace(day=1).strftime("%Y-%m-%d")
    
    with db.get_connection() as conn:
        # 用户统计
        total_users = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
        today_users = conn.execute("SELECT COUNT(*) as c FROM users WHERE created_at >= ?", (today,)).fetchone()["c"]
        
        # 检测统计
        total_detections = conn.execute("SELECT COUNT(*) as c FROM detection_records").fetchone()["c"]
        today_detections = conn.execute("SELECT COUNT(*) as c FROM detection_records WHERE created_at >= ?", (today,)).fetchone()["c"]
        week_detections = conn.execute("SELECT COUNT(*) as c FROM detection_records WHERE created_at >= ?", (week_ago,)).fetchone()["c"]
        
        # 充值统计
        recharge_rows = conn.execute(
            "SELECT COALESCE(SUM(amount),0) as s, COUNT(*) as c FROM billing_records WHERE transaction_type IN ('recharge','member','recharge_first','rewrite_first')"
        ).fetchone()
        total_recharge = recharge_rows["s"]
        total_recharge_count = recharge_rows["c"]
        
        today_recharge = conn.execute(
            "SELECT COALESCE(SUM(amount),0) as s FROM billing_records WHERE transaction_type IN ('recharge','member','recharge_first') AND created_at >= ?", (today,)
        ).fetchone()["s"]
        
        # 每日统计（近7天）
        daily_stats = []
        for i in range(6, -1, -1):
            d = (now - timedelta(days=i)).strftime("%Y-%m-%d")
            d_users = conn.execute("SELECT COUNT(*) as c FROM users WHERE created_at >= ? AND created_at < ?", (d, d+" 23:59:59")).fetchone()["c"]
            d_detect = conn.execute("SELECT COUNT(*) as c FROM detection_records WHERE created_at >= ? AND created_at < ?", (d, d+" 23:59:59")).fetchone()["c"]
            d_recharge = conn.execute("SELECT COALESCE(SUM(amount),0) as s FROM billing_records WHERE transaction_type IN ('recharge','member','recharge_first') AND created_at >= ? AND created_at < ?", (d, d+" 23:59:59")).fetchone()["s"]
            daily_stats.append({"date": d[5:], "users": d_users, "detections": d_detect, "recharge": round(d_recharge, 2)})
        
    return jsonify({
        "total_users": total_users, "today_users": today_users,
        "total_detections": total_detections, "today_detections": today_detections, "week_detections": week_detections,
        "total_recharge": round(total_recharge, 2), "total_recharge_count": total_recharge_count, "today_recharge": round(today_recharge, 2),
        "daily": daily_stats,
    })


@admin_bp.route("/api/config-status")
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
            "free_quota": config.DAILY_FREE_DETECTIONS,
            "member_price": config.MEMBER_MONTHLY_PRICE,
            "credit_price": config.CREDIT_PRICE_PER_K,
            "packages": config.RECHARGE_PACKAGES,
        }
    })


@admin_bp.route("/api/test-xorpay")
def api_test_xorpay():
    """诊断端点：直接测试xorpPay API并返回原始响应"""
    import requests as req
    import hashlib, time
    
    result = {"xorpay_configured": bool(config.XORPAY_APP_ID and config.XORPAY_API_SECRET)}
    
    if not config.XORPAY_APP_ID or not config.XORPAY_API_SECRET:
        result["error"] = "xorpPay未配置"
        return jsonify(result)
    
    site_domain = config.SITE_DOMAIN
    if "localhost" in site_domain or "127.0.0.1" in site_domain:
        site_domain = "https://ai-chachong.onrender.com"
    
    order_id = f"XR{int(time.time())}diag"
    payload = {
        "name": "AI查重-诊断测试",
        "pay_type": "native",
        "price": "0.01",
        "order_id": order_id,
        "notify_url": f"{site_domain}/user/api/pay-callback/xorpay",
        "order_uid": "diag",
        "more": "diag",
    }
    sign_str = payload["name"] + payload["pay_type"] + payload["price"] + payload["order_id"] + payload["notify_url"]
    sign = hashlib.md5((sign_str + config.XORPAY_API_SECRET).encode()).hexdigest()
    payload["sign"] = sign
    
    api_url = f"https://xorpay.com/api/pay/{config.XORPAY_APP_ID}"
    result["request"] = {"url": api_url, "domain_used": site_domain, "order_id": order_id}
    
    try:
        r = req.post(api_url, data=payload, timeout=15)
        result["http_status"] = r.status_code
        result["response"] = r.text[:800]
        if r.status_code == 200:
            data = r.json()
            result["status"] = data.get("status")
            result["qr_available"] = bool(data.get("info", {}).get("qr") or data.get("qr"))
    except Exception as e:
        result["error"] = str(e)
    
    return jsonify(result)


@admin_bp.route("/api/db-status")
def api_db_status():
    """诊断：数据库连接状态"""
    import os
    result = {
        "turso_url": bool(os.getenv("TURSO_DB_URL")),
        "turso_token": bool(os.getenv("TURSO_AUTH_TOKEN")),
        "using_turso": getattr(db, '_turso', False),
    }
    try:
        with db.get_connection() as conn:
            cur = conn.execute("SELECT COUNT(*) as c FROM users")
            row = cur.fetchone()
            if isinstance(row, dict):
                result["user_count"] = row.get("c", 0)
            elif hasattr(row, 'keys'):
                result["user_count"] = row["c"]
            else:
                result["user_count"] = row[0] if row else 0
            result["db_ok"] = True
    except Exception as e:
        result["db_ok"] = False
        result["error"] = str(e)
    return jsonify(result)
