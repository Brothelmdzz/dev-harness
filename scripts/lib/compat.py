"""
filelock 兼容层 — 统一 FileLock 降级逻辑（4→1）
"""
import sys

HAS_FILELOCK = False

try:
    from filelock import FileLock
    HAS_FILELOCK = True
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

def require_filelock(context="parallel execution"):
    """并行模式前调用：filelock 缺失时抛异常阻断，防止并发写入损坏 state"""
    if not HAS_FILELOCK:
        raise RuntimeError(
            f"filelock 未安装，无法安全执行 {context}。"
            f"运行: pip install filelock"
        )

__all__ = ["FileLock", "HAS_FILELOCK", "require_filelock"]
