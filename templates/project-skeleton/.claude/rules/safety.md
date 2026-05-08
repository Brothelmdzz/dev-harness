# 安全纪律（约束层示例）

> 这是一份**示例文件**。安全规则尤其要求**反例免疫格式**——模型见过反例才不会写出反例。
> 参考腾讯 *Harness Engineering* 的"反例免疫"思路。

## 规则 1：禁止字符串拼接 SQL

**补偿的缺口**：模型生成数据库查询时，遇到动态字段会习惯用模板字符串拼接，直接写出 SQL 注入漏洞。

**❌ 反例**：
```typescript
const userId = req.query.id
const sql = `SELECT * FROM users WHERE id = '${userId}'`
db.query(sql)
```

**✅ 正例**：参数化查询
```typescript
const userId = req.query.id
db.query('SELECT * FROM users WHERE id = ?', [userId])
// 或 ORM
userRepo.findOne({ where: { id: userId } })
```

**边界 / 例外**：
- 表名 / 列名是动态的（罕见场景）：必须白名单校验，禁止直接拼接

---

## 规则 2：用户输入禁止直接渲染到 HTML

**补偿的缺口**：模型在前端代码中遇到展示用户内容时，倾向 `dangerouslySetInnerHTML` 或 `v-html`，直接写出 XSS 漏洞。

**❌ 反例**：
```tsx
<div dangerouslySetInnerHTML={{ __html: userBio }} />
```

**✅ 正例**：
```tsx
<div>{userBio}</div>
// 必须 HTML 时用 sanitizer
import DOMPurify from 'dompurify'
<div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(userBio) }} />
```

---

## 规则 3：密钥 / Token / 密码禁止入仓

**补偿的缺口**：模型生成示例配置时会用真实密钥占位（"sk-xxxxx"），如果用户没替换就 commit。

**❌ 反例**：
```yaml
# config.yml
api_key: sk-1234567890abcdef
db_password: supersecret123
```

**✅ 正例**：
```yaml
# config.yml.example  ← .gitignore 排除真实文件
api_key: ${API_KEY}
db_password: ${DB_PASSWORD}
```

**配套**：
- `.gitignore` 排除 `.env` / `*.secret` / `config.yml`
- pre-commit hook 用 `gitleaks` 或 `detect-secrets` 扫描
- 定期审计 git history（`git log -p | grep -i "api_key\|password"`）

---

## 规则 4：权限校验必须在服务端

**补偿的缺口**：模型生成 CRUD 时容易只在前端判断 `if (user.role === 'admin')`，但后端接口实际不校验。

**❌ 反例**：
```typescript
// 前端
{user.role === 'admin' && <DeleteButton onClick={() => fetchDeleteApi(id)} />}

// 后端
app.delete('/api/users/:id', (req, res) => {
  userService.delete(req.params.id)  // ← 没校验！
  res.send({ ok: true })
})
```

**✅ 正例**：前端 + 后端**双重**校验，后端是真权威
```typescript
// 后端
app.delete('/api/users/:id', requireRole('admin'), (req, res) => {
  userService.delete(req.params.id)
  res.send({ ok: true })
})
```

---

## 规则 5：第三方依赖必须锁版本

**补偿的缺口**：模型生成 `package.json` 时倾向用 `^` 或 `~` 范围版本，长期会导致 supply chain 攻击或不可重现构建。

**❌ 反例**：
```json
{ "dependencies": { "axios": "^1.0.0" } }
```

**✅ 正例**：
```json
{ "dependencies": { "axios": "1.6.5" } }
```
配合 `package-lock.json` / `pnpm-lock.yaml` / `yarn.lock` **必须 commit**。

**边界 / 例外**：
- 内部库可以用 `*`（受私有 registry 保护）
- 安全补丁版本（patch）可以放宽到 `~1.6.x`
