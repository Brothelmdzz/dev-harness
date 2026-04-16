"""
配置解析 — 统一 _parse_simple_yaml / load_dev_config / limits（2→1）
"""
from pathlib import Path

def parse_simple_yaml(text):
    """极简 YAML 解析器 — 仅支持顶层和一层嵌套的 key: value"""
    result = {}
    current_section = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent == 0 and ":" in stripped:
            key, _, val = stripped.partition(":")
            val = val.strip().strip('"').strip("'")
            if val:
                result[key.strip()] = val
            else:
                current_section = key.strip()
                result[current_section] = {}
        elif indent > 0 and current_section and ":" in stripped:
            key, _, val = stripped.partition(":")
            val = val.strip().strip('"').strip("'")
            result[current_section][key.strip()] = val
    return result

def load_dev_config(project_root):
    """加载 .claude/dev-config.yml，返回 dict（文件不存在返回空 dict）"""
    cfg_path = Path(project_root) / ".claude" / "dev-config.yml"
    if not cfg_path.exists():
        return {}
    try:
        return parse_simple_yaml(cfg_path.read_text(encoding="utf-8"))
    except OSError:
        return {}

__all__ = ["parse_simple_yaml", "load_dev_config"]
