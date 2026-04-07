#!/usr/bin/env bash
# 自动检测项目技术栈和构建命令
# 输出 JSON: {"stack": "gradle", "build": "...", "test": "...", "lint": "..."}

detect() {
    local stack="" build="" test="" lint=""

    if [ -f "build.gradle" ] || [ -f "build.gradle.kts" ]; then
        stack="gradle"
        build="./gradlew build -x test"
        test="./gradlew test"
        lint=""
    elif [ -f "pom.xml" ]; then
        stack="maven"
        build="mvn compile -q"
        test="mvn test"
        lint="mvn checkstyle:check"
    elif [ -f "package.json" ]; then
        stack="node"
        if [ -f "bun.lockb" ]; then
            build="bun run build"
            test="bun test"
            lint="bun run lint"
        else
            build="npm run build"
            test="npm test"
            lint="npm run lint"
        fi
    elif [ -f "Cargo.toml" ]; then
        stack="rust"
        build="cargo build"
        test="cargo test"
        lint="cargo clippy"
    elif [ -f "pyproject.toml" ]; then
        stack="python"
        build="pip install -e . -q"
        test="pytest"
        lint="ruff check ."
    elif [ -f "setup.py" ]; then
        stack="python"
        build="pip install -e . -q"
        test="pytest"
        lint="ruff check ."
    elif [ -f "go.mod" ]; then
        stack="go"
        build="go build ./..."
        test="go test ./..."
        lint="golangci-lint run"
    elif [ -f "Makefile" ]; then
        stack="make"
        build="make"
        test="make test"
        lint="make lint"
    else
        stack="unknown"
        build="echo 'no build command detected'"
        test="echo 'no test command detected'"
        lint=""
    fi

    python -c "
import json, sys
print(json.dumps({'stack': sys.argv[1], 'build': sys.argv[2], 'test': sys.argv[3], 'lint': sys.argv[4]}, ensure_ascii=False))
" "$stack" "$build" "$test" "$lint"
}

detect
