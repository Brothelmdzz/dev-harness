# Python 测试指引

## 测试命令
```bash
pytest -v
```

## 单测定位
```bash
pytest tests/test_xxx.py -v -k "test_specific_function"
```

## 覆盖率
```bash
pytest --cov=src --cov-report=term-missing
```

## 常见问题
- import 报错 → 确认 `pip install -e .` 或 `PYTHONPATH` 设置
- fixture 未找到 → 检查 `conftest.py` 位置
- async 测试 → 需要 `pytest-asyncio` 且标记 `@pytest.mark.asyncio`
