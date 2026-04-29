# Go TDD 指引

## 测试命令
```bash
go test ./pkg/auth -run TestCreateUser -v
go test ./...  # 全量
```

## RED 阶段
在同包 `_test.go` 文件中写测试：
```go
func TestCreateUser_ReturnsUser(t *testing.T) {
    user := CreateUser("alice")
    assert.Equal(t, "alice", user.Name)
}
```

## GREEN 阶段
在同包源文件写最小实现。

## 框架注意
- table-driven tests 适合批量场景
- `testify/assert` 比原生 `if` 检查更可读
- 竞态检测: `go test -race`
