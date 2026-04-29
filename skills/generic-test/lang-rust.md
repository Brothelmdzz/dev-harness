# Rust 测试指引

## 测试命令
```bash
cargo test
```

## 单测定位
```bash
cargo test test_auth -- --exact
cargo test -p my-crate
```

## 覆盖率
```bash
cargo install cargo-tarpaulin
cargo tarpaulin --out Html
```

## 常见问题
- 编译慢 → `cargo test --no-run` 先编译再跑
- doc test 失败 → 检查 `///` 注释中的代码块
- async 测试 → 需要 `#[tokio::test]` 宏
