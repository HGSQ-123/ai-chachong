"""
用户中心路由 - 检测历史、报告查看、会员管理
"""

import json
import math
from flask import Blueprint, render_template, request, session, jsonify, redirect, url_for, flash
from config import config
from utils.database import db
from utils.decorators import login_required
from services.billing import BillingService

user_bp = Blueprint("user", __name__, url_prefix="/user")

# 内存订单追踪 { order_id: {"paid": bool, "user_id": int, "amount": float} }
_paid_orders = {}


@user_bp.route("/center")
@login_required
def user_center():
    """用户中心页面"""
    user_id = session["user_id"]
    user = db.get_user_by_id(user_id)
    if not user:
        session.clear()
        return redirect(url_for("auth.login_page"))

    # 获取检测记录
    records_raw = db.get_user_detection_records(user_id, limit=30)
    records = []
    for r in records_raw:
        rec = dict(r)
        report_data = rec.get("report_data")
        if isinstance(report_data, str):
            try:
                report_data = json.loads(report_data)
            except json.JSONDecodeError:
                report_data = {}
        rec["report_data"] = report_data
        records.append(rec)

    # 获取额度信息
    quota_info = BillingService.get_available_quota(user)

    # 获取统计信息
    stats = db.get_user_stats(user_id)

    # 获取邀请裂变统计
    referral_stats = db.get_referral_stats(user_id)

    # 获取计费记录
    billing_records = db.get_user_billing_records(user_id, limit=20)

    return render_template(
        "user_center.html",
        user=user,
        records=records,
        quota_info=quota_info,
        stats=stats,
        referral_stats=referral_stats,
        billing_records=billing_records,
        config=config,
    )


@user_bp.route("/api/quota")
@login_required
def api_get_quota():
    """获取用户额度信息API"""
    user = db.get_user_by_id(session["user_id"])
    if not user:
        return jsonify({"success": False, "message": "用户不存在"}), 404

    quota_info = BillingService.get_available_quota(user)
    return jsonify({
        "success": True,
        "quota": quota_info,
        "free_limit": config.DAILY_FREE_DETECTIONS,
        "member_limit": config.MEMBER_MONTHLY_QUOTA,
    })


@user_bp.route("/api/records")
@login_required
def api_get_records():
    """获取检测记录API（分页）"""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    offset = (page - 1) * per_page

    records_raw = db.get_user_detection_records(
        session["user_id"], limit=per_page, offset=offset
    )

    records = []
    for r in records_raw:
        rec = dict(r)
        report_data = rec.get("report_data")
        if isinstance(report_data, str):
            try:
                report_data = json.loads(report_data)
            except json.JSONDecodeError:
                report_data = {}
        rec["report_data"] = report_data
        records.append(rec)

    return jsonify({"success": True, "records": records, "page": page})


@user_bp.route("/member")
def member_page():
    """会员充值页面"""
    user = None
    quota_info = None
    if "user_id" in session:
        user = db.get_user_by_id(session["user_id"])
        if user:
            quota_info = BillingService.get_available_quota(user)

    return render_template(
        "pricing.html",
        user=user,
        quota_info=quota_info,
        config=config,
    )


@user_bp.route("/api/purchase-member", methods=["POST"])
@login_required
def api_purchase_member():
    """
    购买会员API（接入支付）
    步骤：
    1. 创建支付订单 → 返回二维码/支付链接
    2. 前端展示二维码，用户扫码支付
    3. 支付平台回调 → 自动开通会员
    """
    from services.payment import PaymentService

    user_id = session["user_id"]
    amount = config.MEMBER_MONTHLY_PRICE
    description = f"{config.SITE_NAME} - 会员月卡"

    # 创建支付订单
    order = PaymentService.create_order(
        user_id=user_id,
        amount=amount,
        description=description,
        order_type="member",
    )

    if not order["success"]:
        return jsonify({"success": False, "message": "创建订单失败，请重试"}), 500

    # 注册订单追踪
    _paid_orders[order["order_id"]] = {"paid": False, "user_id": user_id, "amount": amount}

    return jsonify({
        "success": True,
        "message": "订单已创建",
        "order": {
            "order_id": order["order_id"],
            "amount": order["amount"],
            "qr_code": order["qr_code"],
            "pay_url": order["pay_url"],
            "channel": order["channel"],
        },
    })


@user_bp.route("/api/purchase-credits", methods=["POST"])
@login_required
def api_purchase_credits():
    """
    购买充值额度API
    请求: {"package_index": 0-4}
    0=¥0.49/1千字 1=¥5/1.02万字 2=¥10/2.04万字 3=¥20/4.08万字 4=¥50/10.2万字 5=¥100/20.4万字
    """
    from services.payment import PaymentService

    data = request.get_json() or {}
    pkg_index = data.get("package_index", 0)
    
    packages = config.RECHARGE_PACKAGES
    if pkg_index < 0 or pkg_index >= len(packages):
        return jsonify({"success": False, "message": "无效的充值套餐"}), 400

    pkg = packages[pkg_index]
    user_id = session["user_id"]
    
    # 创建支付订单
    order = PaymentService.create_order(
        user_id=user_id,
        amount=pkg["amount"],
        description=f"{config.SITE_NAME} - {pkg['label']}",
        order_type="recharge",
    )

    if not order["success"]:
        return jsonify({"success": False, "message": "创建订单失败"}), 500

    # 注册订单追踪（初始未支付）
    _paid_orders[order["order_id"]] = {"paid": False, "user_id": user_id, "amount": pkg["amount"]}

    return jsonify({
        "success": True,
        "message": "订单已创建",
        "order": {
            "order_id": order["order_id"],
            "amount": order["amount"],
            "qr_code": order["qr_code"],
            "pay_url": order["pay_url"],
            "channel": order["channel"],
        },
        "package": pkg,
    })


@user_bp.route("/api/pay-mock-confirm")
def api_pay_mock_confirm():
    """
    模拟支付确认（测试用）
    实际生产中由支付平台回调
    """
    order_id = request.args.get("order_id", "")
    user_id = request.args.get("user_id", 0, type=int)
    amount = request.args.get("amount", 0, type=float)
    order_type = request.args.get("order_type", "member")

    if not order_id or not user_id:
        return jsonify({"success": False, "message": "参数错误"}), 400

    if order_type == "recharge":
        # 找到对应套餐
        pkg_index = 0
        for i, pkg in enumerate(config.RECHARGE_PACKAGES):
            if abs(pkg["amount"] - amount) < 0.01:
                pkg_index = i
                break
        result = BillingService.purchase_credits(user_id, pkg_index)
    else:
        result = BillingService.purchase_member(user_id)

    if result["success"]:
        # 标记订单已支付
        if order_id:
            _paid_orders[order_id] = {"paid": True, "user_id": user_id, "amount": amount}
        return jsonify({
            "success": True,
            "message": result.get("message", "支付成功！"),
            "amount": amount,
        })
    else:
        return jsonify({"success": False, "message": result.get("message", "开通失败")}), 500


@user_bp.route("/api/check-pay")
def api_check_pay():
    """
    查询支付订单是否已完成
    GET ?order_id=xxx
    """
    order_id = request.args.get("order_id", "")
    if not order_id:
        return jsonify({"success": False, "message": "缺少订单号"}), 400

    # 检查内存订单追踪
    if order_id in _paid_orders and _paid_orders[order_id].get("paid"):
        return jsonify({"success": True, "message": "支付成功！"})

    return jsonify({"success": False, "message": "未检测到支付记录，请确认已扫码付款"})


@user_bp.route("/api/pay-callback/<channel>", methods=["POST"])
def api_pay_callback(channel):
    """
    支付平台回调接口
    xorpay/微信/支付宝 支付成功后POST到此地址
    """
    from services.payment import PaymentService

    if channel == "xorpay":
        callback_data = request.form.to_dict()
    elif channel == "wechat":
        callback_data = request.get_json(force=True, silent=True) or {}
    elif channel == "alipay":
        callback_data = request.form.to_dict()
    else:
        return "FAIL", 400

    # 验证回调
    result = PaymentService.verify_callback(callback_data)

    if result["success"]:
        uid = result["user_id"]
        amt = result["amount"]
        oid = result.get("order_id", "")
        
        # 标记订单已支付
        if oid and oid in _paid_orders:
            _paid_orders[oid]["paid"] = True
        
        # 判断订单类型：根据金额匹配套餐
        matched = False
        for i, pkg in enumerate(config.RECHARGE_PACKAGES):
            if abs(pkg["amount"] - amt) < 0.01:
                BillingService.purchase_credits(uid, i)
                matched = True
                break
        if not matched:
            # 非充值套餐，按会员处理
            BillingService.purchase_member(uid)

        if channel == "wechat":
            return '<xml><return_code>SUCCESS</return_code></xml>', 200
        elif channel == "xorpay":
            return "ok", 200
        else:
            return "success", 200
    else:
        return "FAIL", 400


@user_bp.route("/api/task-status/<task_id>")
def api_task_status(task_id):
    """查询异步任务状态"""
    from services.task_manager import task_manager
    task = task_manager.get_task(task_id)
    if not task:
        return jsonify({"success": False, "message": "任务不存在"}), 404
    return jsonify({"success": True, "task": task})


@user_bp.route("/api/ai-rewrite", methods=["POST"])
def api_ai_rewrite():
    """
    AI改写接口（DeepSeek驱动）
    计费：首次免费 → 会员每月免费3次 → 后续按Pro版计费
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "请提供文本内容"}), 400

        text = data.get("text", "").strip()
        action = data.get("action", "rewrite")

        if not text:
            return jsonify({"success": False, "message": "请输入要处理的文本"}), 400
        if len(text) < 10:
            return jsonify({"success": False, "message": "文本过短，至少需要10个字符"}), 400
        if len(text) > config.REDUCE_MAX_CHARS:
            return jsonify({"success": False, "message": f"单次最多{config.REDUCE_MAX_CHARS}字符"}), 400

        # ========== 计费 ==========
        user_id = session.get("user_id")
        billing_label = ""
        if not user_id:
            return jsonify({"success": False, "message": "请先登录", "need_login": True}), 401

        user = db.get_user_by_id(user_id)
        billing_info = _calc_rewrite_cost(user, len(text))

        if billing_info["type"] == "insufficient":
            return jsonify(billing_info), 402

        # ========== 异步执行改写 ==========
        import uuid, threading
        task_id = str(uuid.uuid4())[:8]
        from services.task_manager import task_manager
        task_manager.create_task(task_id)
        task_manager.update_task(task_id, status="processing", progress=10, message="开始改写...")

        def run_rewrite():
            from services.api_client import DeepSeekClient
            if DeepSeekClient.is_configured():
                success, rt, suggs, err = DeepSeekClient.rewrite(text, action)
                if success:
                    _apply_rewrite_billing(user_id, billing_info, text, rt, action, 'deepseek')
                    task_manager.update_task(task_id, status="done", progress=100,
                        result={"success": True, "result_text": rt, "suggestions": suggs,
                                "action": action, "method": "deepseek", "billing": billing_info})
                    return
            rt, suggs = _simulate_ai_rewrite(text, action)
            _apply_rewrite_billing(user_id, billing_info, text, rt, action, 'simulation')
            task_manager.update_task(task_id, status="done", progress=100,
                result={"success": True, "result_text": rt, "suggestions": suggs,
                        "action": action, "method": "simulation", "billing": billing_info})

        threading.Thread(target=run_rewrite, daemon=True).start()
        return jsonify({"success": True, "task_id": task_id, "message": "改写已开始，请稍候..."})

    except Exception as e:
        return jsonify({"success": False, "message": f"处理失败：{str(e)}"}), 500


def _calc_rewrite_cost(user: dict, char_count: int) -> dict:
    """计算改写费用"""
    from datetime import datetime
    quota = BillingService.get_available_quota(user)

    # 1. 首次改写免费
    from utils.database import db
    if db.is_first_reduce_ai(user["id"]) and db.is_first_reduce_plagiarism(user["id"]):
        return {"type": "first", "cost": 0, "label": "首次免费改写", "words": 0}

    # 2. 会员免费改写
    if quota["is_member"]:
        reset_str = user.get("member_rewrite_reset") if user else None
        count = user.get("member_rewrite_count", 0) if user else 0
        if reset_str:
            try:
                from datetime import datetime as dt
                reset_dt = dt.strptime(reset_str, "%Y-%m-%d")
                if dt.now().month != reset_dt.month:
                    count = 0
            except ValueError:
                pass
        if count < config.MEMBER_FREE_REWRITES:
            return {"type": "member_free", "cost": 0, "label": f"会员免费改写({count+1}/{config.MEMBER_FREE_REWRITES})", "words": 0}

    # 3. 按字数扣费
    k = math.ceil(char_count / 1000)
    cost_words = k * 1000
    total = quota["total_remaining"]
    if total < cost_words:
        need = cost_words - total
        need_k = math.ceil(need / 1000)
        return {
            "success": False, "need_recharge": True, "type": "insufficient",
            "message": f"额度不足，还需{need}字（约¥{need_k * config.CREDIT_PRICE_PER_K:.2f}），请先充值",
            "available": total, "needed": cost_words,
        }
    return {"type": "normal", "cost": round(k * config.REDUCE_PRICE_PER_K, 2), "words": cost_words, "label": f"改写 {k}千字 ¥{round(k * config.REDUCE_PRICE_PER_K, 2)}"}


def _apply_rewrite_billing(user_id: int, info: dict, original_text: str = "", result_text: str = "", action: str = "rewrite", method: str = "simulation"):
    """执行改写计费 + 保存历史"""
    from utils.database import db
    billing_type = info["type"]
    billing_cost = info["cost"]
    
    if billing_type == "first":
        db.increment_reduce_ai(user_id)
        db.increment_reduce_plagiarism(user_id)
        db.create_billing_record(user_id, billing_cost, 0, "rewrite_first", info["label"])
    elif billing_type == "member_free":
        with db.get_connection() as conn:
            conn.execute("UPDATE users SET member_rewrite_count=member_rewrite_count+1, member_rewrite_reset=? WHERE id=?",
                        (__import__('datetime').datetime.now().strftime("%Y-%m-%d"), user_id))
        db.create_billing_record(user_id, 0, 0, "rewrite_member_free", info["label"])
    elif billing_type == "normal":
        db.deduct_credits(user_id, info["words"])
        db.create_billing_record(user_id, billing_cost, info["words"], "rewrite", info["label"])
    
    # 保存改写历史（截前500字）
    if original_text:
        db.create_rewrite_record(user_id, original_text[:500], result_text[:500],
                                 len(original_text), action, method, billing_type, billing_cost)


def _simulate_ai_rewrite(text: str, action: str) -> tuple:
    """
    本地模拟AI处理（DeepSeek未配置时的降级方案）
    返回 (result_text, suggestions)
    """
    import hashlib
    import random

    text_seed = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
    random.seed(text_seed)

    if action == "rewrite":
        result_text = f"【改写版】{text}"
        suggestions = [
            "已对原文进行同义替换和句式重组（模拟算法）",
            "建议接入DeepSeek API获得真实降重效果",
            "改写后可再次检测确认降重效果",
        ]
    elif action == "polish":
        result_text = f"【润色版】{text}"
        suggestions = [
            "已优化词语搭配和语句流畅度（模拟算法）",
            "建议接入DeepSeek API获得真实润色效果",
        ]
    elif action == "fix":
        result_text = f"【修正版】{text}"
        suggestions = [
            "已检查并修正常见语病（模拟算法）",
            "建议接入DeepSeek API获得真实修正效果",
        ]
    elif action == "optimize":
        result_text = f"【优化版】{text}"
        suggestions = [
            "已优化句式结构（模拟算法）",
            "建议接入DeepSeek API获得真实优化效果",
        ]
    else:
        result_text = text
        suggestions = []

    random.seed()
    return result_text, suggestions


# ==================== 邀请裂变API ====================

@user_bp.route("/api/referral-stats")
@login_required
def api_referral_stats():
    """获取邀请裂变统计"""
    stats = db.get_referral_stats(session["user_id"])
    stats["invite_link"] = f"{config.SITE_DOMAIN}/auth/register?ref={stats.get('referral_code', '')}"
    return jsonify({"success": True, "stats": stats})


@user_bp.route("/invite")
@login_required
def invite_page():
    """邀请好友页面"""
    user = db.get_user_by_id(session["user_id"])
    referral_stats = db.get_referral_stats(session["user_id"])
    referral_stats["invite_link"] = f"{config.SITE_DOMAIN}/auth/register?ref={referral_stats.get('referral_code', '')}"
    return render_template("invite.html", user=user, referral_stats=referral_stats, config=config)
