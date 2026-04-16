"""
filelock 兼容层 — 统一 FileLock 降级逻辑（4→1）
"""
import sys

try:
    from filelock import FileLock
except ImportError:
    print("WARNING: filelock not installed, concurrent writes unsafe. "
          "Run: pip install filelock", file=sys.stderr)

    class FileLock:
        """无操作锁，单 Agent 场景降级使用"""
        def __init__(self, *a, **kw):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass

__all__ = ["FileLock"]
