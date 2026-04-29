# Go 测试指引

## 测试命令
```bash
go test ./...
```

## 单测定位
```bash
go test ./pkg/auth -run TestLogin -v
```

## 覆盖率
```bash
go test ./... -coverprofile=coverage.out
go tool cover -func=coverage.out
```

## 常见问题
- 并行测试竞态 → `go test -race ./...`
- 集成测试隔离 → 用 `//go:build integration` tag
- 测试缓存 → `go clean -testcache` 强制重跑
