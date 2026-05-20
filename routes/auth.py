"""
认证路由 - 注册、登录、登出、忘记密码
支持：手机号注册 / 邮箱注册 / 验证码 / 忘记密码
"""

import random
import time
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from config import config
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


@auth_bp.route("/api/captcha")
def api_captcha():
    """生成数学图形验证码（返回图片）"""
    import io, random as rnd
    from PIL import Image, ImageDraw, ImageFont
    
    a, b = rnd.randint(1, 20), rnd.randint(1, 20)
    ops = ['+', '-', '×']
    op = rnd.choice(ops)
    if op == '+':
        ans = a + b
    elif op == '-':
        ans = max(a, b) - min(a, b)
        a, b = max(a, b), min(a, b)
    else:
        ans = a * b
    question = f"{a} {op} {b} = ?"
    session["captcha_answer"] = str(ans)

    img = Image.new('RGB', (160, 50), '#f1f5f9')
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 24)
    except Exception:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), question, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((160-tw)//2, (50-th)//2), question, fill='#1e40af', font=font)
    for _ in range(20):
        x1, y1 = rnd.randint(0, 160), rnd.randint(0, 50)
        draw.line([x1, y1, x1+8, y1+5], fill='#94a3b8', width=1)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf.getvalue(), 200, {'Content-Type': 'image/png', 'Cache-Control': 'no-cache'}

@auth_bp.route("/api/send-code", methods=["POST"])
def api_send_code():
    """
    发送验证码（手机或邮箱）
    需先通过图形验证码
    """
    try:
        data = request.get_json() or {}
        account = data.get("account", "").strip()
        captcha_code = data.get("captcha", "").strip()

        # 验证图形验证码
        if session.get("captcha_answer", "") != captcha_code:
            return jsonify({"success": False, "message": "图形验证码错误"}), 400
        session.pop("captcha_answer", None)  # 一次性

        if not account:
            return jsonify({"success": False, "message": "请输入手机号或邮箱"}), 400

        # 60秒内不能重复发送
        existing = _verify_codes.get(account)
        if existing and time.time() - (existing["expires"] - 600) < 60:
            return jsonify({"success": False, "message": "请60秒后再试"}), 429

        code = _store_code(account)

        # 判断账号类型
        is_email = "@" in account
        is_phone = account.isdigit() and len(account) == 11

        # ========== 发送验证码 ==========
        if is_email and config.SMTP_USER and config.SMTP_PASS:
            # 真实邮件发送
            try:
                _send_email(account, code)
                return jsonify({"success": True, "message": f"验证码已发送至 {account}"})
            except Exception as e:
                print(f"[EMAIL] Send failed: {e}")
                # 邮件失败回退演示模式
                return jsonify({
                    "success": True,
                    "message": f"邮件发送失败，演示模式验证码：{code}",
                    "code": code,
                })
        elif is_phone:
            # TODO: 接入短信服务
            return jsonify({
                "success": True,
                "message": f"验证码已发送（演示模式验证码：{code}）",
                "code": code,
            })
        else:
            # 演示模式
            return jsonify({
                "success": True,
                "message": f"验证码已发送（演示模式验证码：{code}）",
                "code": code,
            })

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


def _send_email(to_email: str, code: str):
    """发送验证码邮件（优先HTTP API，回退SMTP）"""
    import smtplib
    from email.mime.text import MIMEText
    from email.header import Header

    subject = f"[{config.SITE_NAME}] 验证码 {code}"
    body = f"您的验证码是：{code}\n\n有效期10分钟，请勿泄露给他人。\n\n—— {config.SITE_NAME}"

    # 方式1: Brevo HTTP API（Render友好，不依赖SMTP端口）
    brevo_key = config.BREVO_API_KEY
    if brevo_key:
        try:
            import requests as _req
            r = _req.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={
                    "api-key": brevo_key,
                    "Content-Type": "application/json",
                },
                json={
                    "sender": {"name": config.SITE_NAME, "email": config.SMTP_USER},
                    "to": [{"email": to_email}],
                    "subject": subject,
                    "textContent": body,
                },
                timeout=10,
            )
            if r.status_code in (200, 201):
                return  # 成功
            print(f"[EMAIL] Brevo API failed: {r.status_code} {r.text[:200]}")
        except Exception as e:
            print(f"[EMAIL] Brevo API error: {e}")

    # 方式2: SMTP（本地/非Render环境可用）
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = Header(subject, "utf-8")
        msg["From"] = config.SMTP_USER
        msg["To"] = to_email

        server = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=10)
        server.starttls()
        server.login(config.SMTP_USER, config.SMTP_PASS)
        server.sendmail(config.SMTP_USER, [to_email], msg.as_string())
        server.quit()
        return
    except Exception as e:
        print(f"[EMAIL] SMTP failed: {e}")

    raise Exception("All email methods failed")


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

