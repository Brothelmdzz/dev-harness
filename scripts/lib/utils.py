"""
时间/通用工具函数 — 统一 now_iso / parse_iso / elapsed_seconds（散落多文件→1）
"""
from datetime import datetime, timezone

def now_iso():
    """当前 UTC 时间 ISO 格式"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def now_utc():
    """当前 UTC datetime 对象"""
    return datetime.now(timezone.utc)

def parse_iso(s):
    """解析 ISO 时间字符串，失败返回 None"""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None

def elapsed_seconds(iso_str):
    """从 ISO 时间到当前 UTC 的秒数"""
    t = parse_iso(iso_str)
    if not t:
        return 0
    return (now_utc() - t).total_seconds()

__all__ = ["now_iso", "now_utc", "parse_iso", "elapsed_seconds"]
