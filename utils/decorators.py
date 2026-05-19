"""
装饰器工具 - 登录验证、管理员权限等
"""

from functools import wraps
from flask import session, redirect, url_for, flash, request, jsonify


def login_required(f):
    """
    登录验证装饰器
    用于保护需要登录才能访问的路由
    未登录用户重定向到登录页面
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            # 如果是AJAX请求，返回JSON错误
            if request.headers.get("X-Requested-With") == "XMLHttpRequest" or \
               request.content_type == "application/json":
                return jsonify({"error": "请先登录", "redirect": url_for("auth.login_page")}), 401
            flash("请先登录后再使用此功能", "warning")
            return redirect(url_for("auth.login_page"))
        return f(*args, **kwargs)
    return decorated_function


def guest_only(f):
    """
    仅限未登录用户访问（如登录页、注册页）
    已登录用户重定向到首页
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" in session:
            return redirect(url_for("main.index"))
        return f(*args, **kwargs)
    return decorated_function


def json_response(f):
    """
    将返回值自动转换为JSON响应
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        result = f(*args, **kwargs)
        if isinstance(result, tuple):
            data, status_code = result
            return jsonify(data), status_code
        return jsonify(result)
    return decorated_function
