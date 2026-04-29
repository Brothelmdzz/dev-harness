# Java TDD 指引

## 测试命令
```bash
# 运行指定测试类
./gradlew test --tests "com.example.XxxTest"
# 全量
./gradlew test
```

## RED 阶段
在 `src/test/java/` 下创建测试类，用 JUnit 5 + AssertJ：
```java
@Test
void should_return_user_when_valid_id() {
    assertThat(service.findById(1L)).isNotNull();
}
```

## GREEN 阶段
在 `src/main/java/` 下写最小实现让测试通过。

## 框架注意
- Spring Boot: 用 `@MockBean` 隔离依赖，避免 `@SpringBootTest` 全启动
- JPA: 测试用 `@DataJpaTest` + H2
