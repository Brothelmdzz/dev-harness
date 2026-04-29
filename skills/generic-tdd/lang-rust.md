# Rust TDD 指引

## 测试命令
```bash
cargo test test_create_user -- --exact
cargo test  # 全量
```

## RED 阶段
在源文件底部或 `tests/` 目录写测试：
```rust
#[test]
fn test_create_user_returns_user() {
    let user = create_user("alice");
    assert_eq!(user.name, "alice");
}
```

## GREEN 阶段
在同模块写最小实现让测试通过。

## 框架注意
- `#[cfg(test)] mod tests {}` 放同文件
- async 测试用 `#[tokio::test]`
- 集成测试放 `tests/` 目录
