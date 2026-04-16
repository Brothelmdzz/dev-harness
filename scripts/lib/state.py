"""
状态管理 — 统一 load_state / save_state / load_and_update_state / session index
"""
import json
import os
from pathlib import Path

from .compat import FileLock
from .utils import now_iso

# ==================== State 文件操作 ====================

def load_state(state_file):
    """加载 harness-state.json，文件不存在返回 None"""
    state_file = Path(state_file)
    if not state_file.exists():
        return None
    try:
        lock = FileLock(str(state_file) + ".lock", timeout=5)
        with lock:
            return json.loads(state_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

def save_state(state_file, state):
    """原子化写入 state（先写 .tmp 再 os.replace）"""
    state_file = Path(state_file)
    state["updated_at"] = now_iso()
    tmp_file = state_file.with_suffix(".json.tmp")
    lock = FileLock(str(state_file) + ".lock", timeout=5)
    with lock:
        tmp_file.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(str(tmp_file), str(state_file))

def load_and_update_state(state_file, updater_fn):
    """原子化 read-modify-write：锁内读取、更新、写入，防止 TOCTOU 竞态。

    Args:
        state_file: harness-state.json 路径
        updater_fn: 接收 state dict，原地修改，返回 None 或新 state

    Returns:
        更新后的 state dict
    """
    state_file = Path(state_file)
    lock = FileLock(str(state_file) + ".lock", timeout=5)
    with lock:
        state = json.loads(state_file.read_text(encoding="utf-8"))
        result = updater_fn(state)
        if result is not None:
            state = result
        state["updated_at"] = now_iso()
        tmp_file = state_file.with_suffix(".json.tmp")
        tmp_file.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(str(tmp_file), str(state_file))
    return state

# ==================== Session Index ====================

SESSION_INDEX = Path.home() / ".claude" / "dev-harness-sessions.json"

def load_session_index():
    """加载中央 session 索引"""
    if SESSION_INDEX.exists():
        try:
            return json.loads(SESSION_INDEX.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}

def save_session_index(index):
    """写入中央 session 索引（含文件权限保护）"""
    SESSION_INDEX.parent.mkdir(parents=True, exist_ok=True)
    SESSION_INDEX.write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if os.name != "nt":
        try:
            os.chmod(SESSION_INDEX, 0o600)
        except OSError:
            pass

def load_and_update_session_index(updater_fn):
    """原子化更新 session 索引（P2-3: 加锁防并行 lost update）"""
    lock = FileLock(str(SESSION_INDEX) + ".lock", timeout=5)
    with lock:
        index = load_session_index()
        result = updater_fn(index)
        if result is not None:
            index = result
        save_session_index(index)
    return index

__all__ = [
    "load_state", "save_state", "load_and_update_state",
    "load_session_index", "save_session_index", "load_and_update_session_index",
    "SESSION_INDEX",
]
