"""
============================================================
任务管理器 - 文件检测进度跟踪
支持：进度百分比、阶段状态、结果回调
============================================================
"""

import time
import threading
from datetime import datetime


class TaskManager:
    """
    内存级任务管理器（单例）
    跟踪文件检测任务的进度和状态
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tasks = {}
            cls._instance._lock = threading.Lock()
        return cls._instance

    def create_task(self, task_id: str) -> dict:
        """创建新任务"""
        with self._lock:
            task = {
                "task_id": task_id,
                "status": "pending",       # pending/uploading/parsing/detecting/done/error
                "progress": 0,             # 0-100
                "message": "等待开始...",
                "result": None,
                "created_at": datetime.now().isoformat(),
            }
            self._tasks[task_id] = task
            return task

    def update_task(self, task_id: str, status: str = None,
                    progress: int = None, message: str = None,
                    result: dict = None):
        """更新任务状态"""
        with self._lock:
            if task_id in self._tasks:
                task = self._tasks[task_id]
                if status is not None:
                    task["status"] = status
                if progress is not None:
                    task["progress"] = progress
                if message is not None:
                    task["message"] = message
                if result is not None:
                    task["result"] = result

    def get_task(self, task_id: str) -> dict | None:
        """获取任务状态"""
        with self._lock:
            return self._tasks.get(task_id)

    def cleanup_old_tasks(self, max_age_seconds: int = 3600):
        """清理过期任务"""
        with self._lock:
            now = datetime.now()
            expired = []
            for tid, task in self._tasks.items():
                created = datetime.fromisoformat(task["created_at"])
                if (now - created).total_seconds() > max_age_seconds:
                    expired.append(tid)
            for tid in expired:
                del self._tasks[tid]


# 全局实例
task_manager = TaskManager()
