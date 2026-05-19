"""
============================================================
启动脚本 - 最简单的运行方式
直接运行: python run.py
============================================================
"""

from app import app

if __name__ == "__main__":
    print("=" * 60)
    print("  AI查重+论文重复率检测系统")
    print("  正在启动服务器...")
    print("  本地访问: http://localhost:5000")
    print("  按 Ctrl+C 停止服务")
    print("=" * 60)
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True,
    )
