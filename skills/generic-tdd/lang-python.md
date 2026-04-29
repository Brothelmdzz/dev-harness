# Python TDD 指引

## 测试命令
```bash
pytest tests/test_xxx.py -v
pytest -v  # 全量
```

## RED 阶段
在 `tests/` 下创建测试文件：
```python
def test_create_user_returns_user():
    result = create_user("alice")
    assert result.name == "alice"
```

## GREEN 阶段
在 `src/` 下写最小实现让测试通过。

## 框架注意
- FastAPI: 用 `TestClient` 做 API 测试
- Django: 用 `TestCase` + `override_settings`
- async: 用 `pytest-asyncio` + `@pytest.mark.asyncio`
