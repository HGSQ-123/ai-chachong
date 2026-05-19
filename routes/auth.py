"""
认证路由 - 注册、登录、登出、忘记密码
支持：手机号注册 / 邮箱注册 / 验证码 / 忘记密码
"""

import random
import time
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from utils.database import db
from models.user import User
from utils.decorators import guest_only, login_required

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

# 内存验证码存储 { phone_or_email: {"code":"123456","expires":timestamp} }
_verify_codes = {}


def _generate_code(length=6) -> str:
    """生成数字验证码"""
    return ''.join(random.choices('0123456789', k=length))


def _store_code(account: str) -> str:
    """存储验证码并返回"""
    code = _generate_code()
    _verify_codes[account] = {"code": code, "expires": time.time() + 600}
    return code


def _verify_code(account: str, code: str) -> bool:
    """验证验证码"""
    data = _verify_codes.get(account)
    if not data:
        return False
    if time.time() > data["expires"]:
        del _verify_codes[account]
        return False
    if data["code"] != code:
        return False
    del _verify_codes[account]
    return True


@auth_bp.route("/login", methods=["GET"])
@guest_only
def login_page():
    """登录页面"""
    return render_template("login.html")


@auth_bp.route("/register", methods=["GET"])
@guest_only
def register_page():
    """注册页面"""
    return render_template("register.html")


@auth_bp.route("/forgot-password")
def forgot_password_page():
    """忘记密码页面"""
    return render_template("login.html", forgot_mode=True)


@auth_bp.route("/api/send-code", methods=["POST"])
def api_send_code():
    """
    发送验证码（手机或邮箱）
    当前模式：直接返回验证码（演示）
    生产模式：接入阿里云/腾讯云短信服务
    """
    try:
        data = request.get_json() or {}
        account = data.get("account", "").strip()
        if not account:
            return jsonify({"success": False, "message": "请输入手机号或邮箱"}), 400

        # 60秒内不能重复发送
        existing = _verify_codes.get(account)
        if existing and time.time() - (existing["expires"] - 600) < 60:
            return jsonify({"success": False, "message": "请60秒后再试"}), 429

        code = _store_code(account)

        # TODO: 生产环境接入真实短信/邮件服务
        # 阿里云短信: https://www.aliyun.com/product/sms
        # 腾讯云短信: https://cloud.tencent.com/product/sms
        # 演示模式：直接返回验证码
        return jsonify({
            "success": True,
            "message": f"验证码已发送（演示模式验证码：{code}）",
            "code": code,  # 生产环境请删除此行
        })

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@auth_bp.route("/api/login", methods=["POST"])
def api_login():
    """
    登录（支持用户名/手机号/邮箱 + 密码）
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "请提供登录信息"}), 400

        account = data.get("username", "").strip() or data.get("account", "").strip()
        password = data.get("password", "")

        if not account or not password:
            return jsonify({"success": False, "message": "账号和密码不能为空"}), 400

        # 尝试按用户名/邮箱/手机号查找
        user = (db.get_user_by_username(account) or
                db.get_user_by_email(account) or
                db.get_user_by_phone(account))

        if not user:
            return jsonify({"success": False, "message": "账号或密码错误"}), 401

        user_obj = User(
            username=user["username"],
            email=user["email"],
            password_hash=user["password_hash"],
            user_id=user["id"],
            free_quota_used=user.get("free_quota_used", 0),
            is_member=bool(user.get("is_member")),
        )
        if not user_obj.check_password(password):
            return jsonify({"success": False, "message": "账号或密码错误"}), 401

        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session.permanent = True

        return jsonify({
            "success": True,
            "message": "登录成功",
            "redirect": url_for("main.index"),
        })

    except Exception as e:
        return jsonify({"success": False, "message": f"登录失败：{str(e)}"}), 500


@auth_bp.route("/api/register", methods=["POST"])
def api_register():
    """
    注册（支持手机号或邮箱 + 验证码）
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "请提供注册信息"}), 400

        username = data.get("username", "").strip()
        account = data.get("email", "").strip() or data.get("phone", "").strip()
        password = data.get("password", "")
        password_confirm = data.get("password_confirm", "")
        code = data.get("code", "").strip()
        ref_code = data.get("ref_code", "").strip()

        # 判断注册方式
        is_phone = account and account.isdigit() and len(account) == 11
        is_email = account and "@" in account

        if not username or not account or not password:
            return jsonify({"success": False, "message": "请填写所有必填字段"}), 400

        if len(username) < 2 or len(username) > 20:
            return jsonify({"success": False, "message": "用户名长度2-20个字符"}), 400

        if len(password) < 6:
            return jsonify({"success": False, "message": "密码至少6位"}), 400

        if password != password_confirm:
            return jsonify({"success": False, "message": "两次密码不一致"}), 400

        if not is_phone and not is_email:
            return jsonify({"success": False, "message": "请输入正确的手机号或邮箱"}), 400

        # 验证验证码
        if not _verify_code(account, code):
            return jsonify({"success": False, "message": "验证码错误或已过期"}), 400

        # 查重
        if db.get_user_by_username(username):
            return jsonify({"success": False, "message": "该用户名已被注册"}), 409

        if is_phone and db.get_user_by_phone(account):
            return jsonify({"success": False, "message": "该手机号已被注册"}), 409

        if is_email and db.get_user_by_email(account):
            return jsonify({"success": False, "message": "该邮箱已被注册"}), 409

        # 处理邀请码
        referred_by = None
        if ref_code:
            inviter = db.get_user_by_referral_code(ref_code)
            referred_by = inviter["id"] if inviter else None

        # 生成邀请码
        import string
        user_code = username[:8] + ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))

        # 创建用户
        password_hash = User.hash_password(password)
        email_val = account if is_email else f"{account}@phone.user"
        phone_val = account if is_phone else ""

        user_id = db.create_user(username, email_val, password_hash,
                                 referral_code=user_code, referred_by=referred_by,
                                 phone=phone_val)
        if not user_id:
            return jsonify({"success": False, "message": "注册失败"}), 500

        # 邀请奖励
        invite_bonus = ""
        if referred_by:
            db.claim_referral_reward(user_id, reward_words=500)
            invite_bonus = " + 邀请奖励500字"

        session["user_id"] = user_id
        session["username"] = username
        session.permanent = True

        from config import config
        return jsonify({
            "success": True,
            "message": f"注册成功！首次检测免费{invite_bonus}",
            "redirect": url_for("main.index"),
            "referral_code": user_code,
        })

    except Exception as e:
        return jsonify({"success": False, "message": f"注册失败：{str(e)}"}), 500


@auth_bp.route("/api/reset-password", methods=["POST"])
def api_reset_password():
    """
    忘记密码 - 通过手机/邮箱验证码重置
    """
    try:
        data = request.get_json() or {}
        account = data.get("account", "").strip()
        code = data.get("code", "").strip()
        new_password = data.get("password", "").strip()

        if not account or not code or not new_password:
            return jsonify({"success": False, "message": "请填写所有字段"}), 400

        if len(new_password) < 6:
            return jsonify({"success": False, "message": "新密码至少6位"}), 400

        # 验证验证码
        if not _verify_code(account, code):
            return jsonify({"success": False, "message": "验证码错误或已过期"}), 400

        # 查找用户
        user = (db.get_user_by_email(account) or
                db.get_user_by_phone(account) or
                db.get_user_by_username(account))
        if not user:
            return jsonify({"success": False, "message": "账号不存在"}), 404

        # 更新密码
        new_hash = User.hash_password(new_password)
        db.update_user_password(user["id"], new_hash)

        return jsonify({"success": True, "message": "密码重置成功，请登录"})

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("已成功退出登录", "info")
    return redirect(url_for("main.index"))

