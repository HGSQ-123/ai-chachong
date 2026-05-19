"""
============================================================
生产环境启动脚本（0成本部署用）
用法: python start.py
============================================================
"""

import os
import sys

# 确保项目根目录在Python路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app

if __name__ == "__main__":
    # 从环境变量读取端口，默认5000
    port = int(os.environ.get("PORT", 5000))

    print("=" * 60)
    print("  AI查重检测平台 - 生产模式")
    print(f"  端口: {port}")
    print(f"  访问: http://localhost:{port}")
    print("=" * 60)

    # 生产模式：关闭debug，监听所有IP
    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
    )
