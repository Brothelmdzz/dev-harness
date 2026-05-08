# 部署流程（示例）

> 这是一份**示例文件**。请按你们实际的部署方式改写。
> Last verified: 2026-05-08

## 适用范围

本文档描述生产环境部署流程。预发 / 测试环境流程见 `staging-deployment.md`（按需新增）。

## 前置条件

- [ ] 已通过 PR review（详见 `.claude/runbooks/pre-deploy-check.md`）
- [ ] 测试环境验证通过
- [ ] 已通知 #release-notify 频道

## 步骤

### 1. 构建镜像

```bash
# 在仓库根
docker build -t myapp:$(git rev-parse --short HEAD) .
```

**失败处理**：
- 构建失败 → 检查 `Dockerfile` 与 `package.json` 依赖
- OOM → 调高 Docker 内存到 8G

### 2. 推送到镜像仓库

```bash
docker tag myapp:$(git rev-parse --short HEAD) registry.example.com/myapp:latest
docker push registry.example.com/myapp:latest
```

**失败处理**：
- 401 → `docker login registry.example.com`
- 网络超时 → 重试或换镜像源

### 3. 触发部署

```bash
kubectl set image deployment/myapp myapp=registry.example.com/myapp:latest
kubectl rollout status deployment/myapp
```

**失败处理**：
- rollout 卡住 → `kubectl describe pod` 看具体错误
- ImagePullBackOff → 检查 imagePullSecret

### 4. 验证

```bash
curl -f https://myapp.example.com/health
```

预期响应：`{ "status": "ok", "version": "..." }`

**失败处理**：见 `runbooks/incident-response.md`

### 5. 回滚（如有问题）

```bash
kubectl rollout undo deployment/myapp
```

回滚后通知 #release-notify + 立即创建 incident issue。

## 常见坑（请贡献到 pitfall-journal.jsonl）

- ❗ 部署后 5 分钟内不要做第二次部署 —— 新旧 pod 共存期间数据库迁移可能冲突
- ❗ Friday 16:00 后禁止部署（避免周末值班压力）

## 链接

- [`runbooks/incident-response.md`](../runbooks/incident-response.md)
- [`pitfall-journal.jsonl`](../pitfall-journal.jsonl)
