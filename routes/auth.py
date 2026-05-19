"""
认证路由 - 注册、登录、登出
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from utils.database import db
from models.user import User
from utils.decorators import guest_only, login_required

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


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


@auth_bp.route("/api/login", methods=["POST"])
@guest_only
def api_login():
    """
    登录API接口
    接收JSON: {"username": "...", "password": "..."}
    返回JSON: {"success": bool, "message": str}
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "请提供登录信息"}), 400

        username = data.get("username", "").strip()
        password = data.get("password", "")

        if not username or not password:
            return jsonify({"success": False, "message": "用户名和密码不能为空"}), 400

        # 查找用户
        user = db.get_user_by_username(username)
        if not user:
            return jsonify({"success": False, "message": "用户名或密码错误"}), 401

        # 验证密码
        user_obj = User(
            username=user["username"],
            email=user["email"],
            password_hash=user["password_hash"],
            user_id=user["id"],
            free_quota_used=user["free_quota_used"],
            is_member=bool(user["is_member"]),
        )
        if not user_obj.check_password(password):
            return jsonify({"success": False, "message": "用户名或密码错误"}), 401

        # 登录成功，设置session
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session.permanent = True

        return jsonify({
            "success": True,
            "message": "登录成功",
            "redirect": url_for("main.index"),
            "user": {"username": user["username"], "email": user["email"]},
        })

    except Exception as e:
        return jsonify({"success": False, "message": f"登录失败：{str(e)}"}), 500


@auth_bp.route("/api/register", methods=["POST"])
@guest_only
def api_register():
    """
    注册API接口
    接收JSON: {"username": "...", "email": "...", "password": "...", "ref_code": "..."}
    ref_code可选，用于邀请裂变
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "请提供注册信息"}), 400

        username = data.get("username", "").strip()
        email = data.get("email", "").strip()
        password = data.get("password", "")
        password_confirm = data.get("password_confirm", "")
        ref_code = data.get("ref_code", "").strip()

        # 输入验证
        if not username or not email or not password:
            return jsonify({"success": False, "message": "请填写所有必填字段"}), 400

        if len(username) < 2 or len(username) > 20:
            return jsonify({"success": False, "message": "用户名长度应在2-20个字符之间"}), 400

        if len(password) < 6:
            return jsonify({"success": False, "message": "密码长度不能少于6位"}), 400

        if password != password_confirm:
            return jsonify({"success": False, "message": "两次输入的密码不一致"}), 400

        if "@" not in email or "." not in email:
            return jsonify({"success": False, "message": "请输入有效的邮箱地址"}), 400

        # 检查用户名是否已存在
        if db.get_user_by_username(username):
            return jsonify({"success": False, "message": "该用户名已被注册"}), 409

        # 检查邮箱是否已存在
        if db.get_user_by_email(email):
            return jsonify({"success": False, "message": "该邮箱已被注册"}), 409

        # 处理邀请码
        referred_by = None
        inviter_name = None
        if ref_code:
            inviter = db.get_user_by_referral_code(ref_code)
            if inviter and inviter["id"]:
                referred_by = inviter["id"]
                inviter_name = inviter["username"]

        # 生成唯一邀请码（用户名+随机4位）
        import random
        import string
        user_code = username[:8] + ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))

        # 创建用户
        password_hash = User.hash_password(password)
        user_id = db.create_user(username, email, password_hash,
                                 referral_code=user_code, referred_by=referred_by)

        if not user_id:
            return jsonify({"success": False, "message": "注册失败，请稍后重试"}), 500

        # 如果通过邀请注册，自动领取奖励
        invite_bonus = ""
        if referred_by:
            db.claim_referral_reward(user_id, reward_words=1000)
            invite_bonus = f" + 邀请奖励1000字"

        # 自动登录
        session["user_id"] = user_id
        session["username"] = username
        session.permanent = True

        from config import config
        return jsonify({
            "success": True,
            "message": f"注册成功！已赠送{config.FREE_QUOTA_WORDS}字免费额度{invite_bonus}",
            "redirect": url_for("main.index"),
            "referral_code": user_code,
        })

    except Exception as e:
        return jsonify({"success": False, "message": f"注册失败：{str(e)}"}), 500


@auth_bp.route("/logout")
def logout():
    """退出登录"""
    session.clear()
    flash("已成功退出登录", "info")
    return redirect(url_for("main.index"))


@auth_bp.route("/api/check-login")
def check_login():
    """检查登录状态（供前端AJAX调用）"""
    if "user_id" in session:
        user = db.get_user_by_id(session["user_id"])
        if user:
            return jsonify({
                "logged_in": True,
                "user": {
                    "username": user["username"],
                    "email": user["email"],
                }
            })
    return jsonify({"logged_in": False})
