# Java/Gradle 测试指引

## 测试命令
```bash
./gradlew test
```

## 单测定位
```bash
./gradlew test --tests "com.example.XxxTest"
```

## 覆盖率
```bash
./gradlew jacocoTestReport
# 报告: build/reports/jacoco/test/html/index.html
```

## 常见问题
- Spring Boot 测试慢 → 用 `@SpringBootTest(webEnvironment = MOCK)` 替代完整启动
- 数据库测试 → 确认有 `@Transactional` 回滚或 H2 内存库
- Gradle daemon 卡住 → `./gradlew --stop` 后重跑
