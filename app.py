"""
============================================================
AI查重+论文重复率检测系统 - 主应用入口
Flask应用工厂模式，统一管理所有配置和蓝图注册
============================================================
"""

import os
import sys
from datetime import timedelta
from flask import Flask

# 将项目根目录加入Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import config


def create_app():
    """
    创建Flask应用实例（工厂模式）
    集中完成：配置加载、蓝图注册、错误处理、定时任务
    """
    app = Flask(__name__)

    # ==================== 加载配置 ====================
    app.config.from_object(config)
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH
    app.config["UPLOAD_FOLDER"] = config.UPLOAD_FOLDER

    # 设置session过期时间（7天）
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)

    # 确保必要目录存在
    os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(__file__), "data"), exist_ok=True)

    # ==================== 注册蓝图 ====================
    from routes.auth import auth_bp
    from routes.detect import detect_bp
    from routes.user import user_bp
    from routes.main import main_bp
    from routes.admin import admin_bp

    app.register_blueprint(main_bp)       # 主页面路由（首页、关于、免责）
    app.register_blueprint(auth_bp)       # 认证路由（登录、注册）
    app.register_blueprint(detect_bp)     # 检测路由（文本检测、文件检测）
    app.register_blueprint(user_bp)       # 用户路由（用户中心、会员）
    app.register_blueprint(admin_bp)      # 管理路由（DeepSeek测试、配置状态）

    # ==================== 全局上下文注入 ====================
    @app.context_processor
    def inject_globals():
        """
        向所有模板注入全局变量
        方便模板中直接使用站点配置
        """
        from flask import session
        from utils.database import db

        user_data = None
        if "user_id" in session:
            user_data = db.get_user_by_id(session["user_id"])

        return {
            "site_name": config.SITE_NAME,
            "site_description": config.SITE_DESCRIPTION,
            "site_domain": config.SITE_DOMAIN,
            "contact_email": config.CONTACT_EMAIL,
            "current_user_data": user_data,
            "announcement": config.ANNOUNCEMENT_TEXT if config.ANNOUNCEMENT_ENABLED else "",
            "free_quota_words": config.FREE_QUOTA_WORDS,
            "member_monthly_price": config.MEMBER_MONTHLY_PRICE,
            "member_monthly_quota": config.MEMBER_MONTHLY_QUOTA,
        }

    # ==================== 启动定时清理任务 ====================
    _setup_cleanup_scheduler(app)

    # ==================== 初始化数据库 ====================
    from utils.database import db as database
    # 触发数据库初始化（创建表和索引）
    _ = database.db_path

    return app


def _setup_cleanup_scheduler(app):
    """
    设置定时清理任务
    定期清理过期的上传文件和检测记录
    """
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from utils.helpers import clean_old_upload_files

        scheduler = BackgroundScheduler()

        @scheduler.scheduled_job("interval", hours=1, id="cleanup_files")
        def cleanup_job():
            """每小时清理一次过期文件"""
            with app.app_context():
                try:
                    clean_old_upload_files(
                        app.config["UPLOAD_FOLDER"],
                        max_age_hours=config.FILE_CLEANUP_SECONDS / 3600
                    )
                    from utils.database import db
                    db.delete_old_records(hours=72)  # 72小时后清理检测记录
                except Exception:
                    pass  # 静默处理清理异常

        scheduler.start()
    except ImportError:
        # APScheduler未安装时跳过（不影响核心功能）
        pass


# 创建应用实例（供gunicorn等WSGI服务器使用）
app = create_app()

# ==================== 直接运行入口 ====================
if __name__ == "__main__":
    # 生产环境：从环境变量读取端口，关闭debug
    import os
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0").lower() in ("1", "true", "yes")

    print("=" * 60)
    print(f"  {config.SITE_NAME} - 启动中...")
    print(f"  访问地址: http://localhost:{port}")
    print(f"  免费额度: {config.FREE_QUOTA_WORDS}字/新用户")
    print(f"  会员价格: {config.MEMBER_MONTHLY_PRICE}元/月")
    print("=" * 60)
    app.run(
        host="0.0.0.0",
        port=port,
        debug=debug,
    )
