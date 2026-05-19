"""
主页面路由 - 首页、关于、免责声明
"""

from flask import Blueprint, render_template, session, jsonify
from config import config
from utils.database import db
from services.billing import BillingService

main_bp = Blueprint("main", __name__)


@main_bp.route("/health")
def health():
    """轻量健康检查端点（供外部保活服务调用，几字节响应）"""
    return jsonify({"status": "ok"}), 200, {"Cache-Control": "no-cache"}


@main_bp.route("/")
def index():
    """首页"""
    user = None
    quota_info = None
    if "user_id" in session:
        user = db.get_user_by_id(session["user_id"])
        if user:
            quota_info = BillingService.get_available_quota(user)

    return render_template(
        "index.html",
        user=user,
        quota_info=quota_info,
        config=config,
    )


@main_bp.route("/about")
def about():
    """关于我们页面"""
    return render_template("about.html", config=config)


@main_bp.route("/disclaimer")
def disclaimer():
    """免责声明页面"""
    return render_template("disclaimer.html", config=config)


@main_bp.route("/privacy")
def privacy():
    """隐私政策页面"""
    return render_template("privacy.html", config=config)


@main_bp.route("/terms")
def terms():
    """服务条款页面"""
    return render_template("terms.html", config=config)


@main_bp.route("/tools")
def tools_page():
    """AI辅助工具页面（降重、润色、修正、优化）"""
    user = None
    if "user_id" in session:
        user = db.get_user_by_id(session["user_id"])
    return render_template("tools.html", user=user, config=config)


@main_bp.errorhandler(404)
def page_not_found(e):
    """404页面"""
    return render_template("404.html", config=config), 404


@main_bp.errorhandler(500)
def server_error(e):
    """500页面"""
    return render_template("500.html", config=config), 500
