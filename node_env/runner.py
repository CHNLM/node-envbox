"""后台执行与日志总线。

核心原则：所有 npm/node 命令与耗时操作都通过 Worker 放进 QThread 执行，
避免界面假死；日志通过 Bus 信号跨线程安全推送。
"""

from PySide6.QtCore import QObject, QThread, Signal


class Bus(QObject):
    """全局信号总线：日志、状态、页面刷新。"""
    log = Signal(str, str)          # (text, level: info/ok/warn/error)
    refresh_requested = Signal(str)  # page key, e.g. "mirrors"


bus = Bus()


class Worker(QThread):
    """在后台线程执行 fn(*args, **kwargs)，结果/异常经信号回主线程。"""

    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, *args, parent=None, **kwargs):
        super().__init__(parent)
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            result = self._fn(*self._args, **self._kwargs)
            self.finished_ok.emit(result)
        except Exception as e:  # noqa: BLE001 - 兜底，不允许异常逃逸到线程外
            self.failed.emit(f"{type(e).__name__}: {e}")


class TaskRunner:
    """页面持有的执行器：自动把函数丢到后台线程，避免重复代码。"""

    def __init__(self, on_done=None, on_error=None):
        self._worker = None
        self._on_done = on_done
        self._on_error = on_error

    @staticmethod
    def _default_error(msg):
        """默认错误处理：写入日志总线，避免后台异常被静默吞掉。"""
        bus.log.emit(f"[后台任务] 执行失败：{msg}", "error")

    def run(self, fn, *args, **kwargs):
        self._worker = Worker(fn, *args, parent=None, **kwargs)
        if self._on_done is not None:
            self._worker.finished_ok.connect(self._on_done)
        # 未显式提供 on_error 时接入默认回调，避免异常静默失效
        err = self._on_error or self._default_error
        self._worker.failed.connect(err)
        self._worker.start()

    def is_running(self):
        return self._worker is not None and self._worker.isRunning()
