# MCP Agent

## 打包为单文件 (pyz) 并外置 YAML 配置

本项目支持通过 `zipapp` 打包成单个 `app.pyz`，同时把 `config.yaml` 与 `workflow.yaml` 放在外部目录，类似 Spring Boot `application.yaml` 可覆盖的效果。

### 目录结构示例

```
project/
	config.yaml
	workflow.yaml
	(其它源码...)
```

### 构建步骤

运行脚本：

```
./build_pyz.sh
```

生成产物：`dist/app.pyz`

### 运行方式

1. 通过环境变量指定配置目录：
```
APP_CONFIG_DIR=/absolute/path/to/project python dist/app.pyz
```

2. 或使用参数：
```
python dist/app.pyz --config-dir=/absolute/path/to/project
```

配置目录中需要存在：
```
config.yaml
workflow.yaml
```

如果未提供，将尝试回退到打包时的项目根目录（打包脚本默认不包含这两个文件，因此通常会报缺失提示）。

### 运行后

应用启动 FastAPI 服务，默认端口 `8002`。你可以通过环境变量或修改 `main.py` 自行调整。

### 注意事项

- 依赖中含有 `pandas` 等 C 扩展，`app.pyz` 仍然依赖宿主机的 `python3` 与 ABI 兼容（构建与运行需保持 Python 主版本一致）。
- 如果需要真正跨操作系统分发，需分别在对应 OS 构建。
- 如需完全不依赖宿主 Python，请改用 PyInstaller / Nuitka，多平台分别产出。

### 重新生成锁文件

使用 `uv`：
```
uv lock
```

### 开发运行

```
uv run python main.py
```

或直接：
```
python main.py
```

（确保已安装依赖）

---

如需再添加 PyInstaller / PEX 构建流程，可提出需求。  

## 使用 Shiv 打包 (支持 C 扩展)

当依赖包含 `pandas` 等 C 扩展且仍希望生成单个可执行 zip（首次运行自动解压缓存）时，可使用 [Shiv](https://github.com/linkedin/shiv)。本仓库已提供 `build_shiv.sh`。

### 构建
```
chmod +x build_shiv.sh
./build_shiv.sh
```
生成：`dist/app-shiv.pyz`

### 运行
```
python dist/app-shiv.pyz --port 8002
```
或指定外部配置：
```
APP_CONFIG_DIR=/absolute/path/to/config python dist/app-shiv.pyz --host 0.0.0.0 --port 9000
```
配置目录需包含：`config.yaml` 与 `workflow.yaml`。

### 端口/主机自定义
- 环境变量：`APP_PORT` / `APP_HOST` 覆盖默认
- CLI 参数：`--port`、`--host` （在 `run_server.py` 中解析）

### 缓存位置
Shiv 会在第一次运行时解压到 `~/.shiv/`（默认），缓存命中后启动更快。可通过环境变量 `SHIV_ROOT` 自定义。

### 典型场景
- 内部分发，有 Python 环境
- 需要包含原生扩展又想以“单文件”交付

### 与 zipapp 差异
| 项目 | zipapp | shiv |
|------|--------|------|
| C 扩展支持 | 否 | 是（解压后运行） |
| 启动速度 | 快（直接 import） | 首次慢，后续快 |
| 额外依赖 | 无 | 需要安装 shiv |

## Docker 部署

已提供 `Dockerfile` + `Makefile` 快速构建运行镜像（使用 uv 进行依赖安装，多阶段构建，非 root 运行）。

### 构建
```
make build  # 或 docker build -t mcp-agent:latest .
```

### 运行
默认应用端口 8002：
```
make run PORT=8002 CONFIG_DIR=$(pwd)
```
上面命令会把当前目录挂载到容器 `/app/config_ext`，你可以在代码中通过 `APP_CONFIG_DIR=/app/config_ext` 来指向外部配置（若已使用该环境变量机制）。

或手动：
```
docker run --rm -p 8002:8002 -e APP_PORT=8002 -e APP_CONFIG_DIR=/app/config_ext -v $(pwd):/app/config_ext mcp-agent:latest --host 0.0.0.0 --port 8002
```

### 推送到私有仓库
```
make push REG=registry.example.com
```

### 健康检查
Dockerfile 中自带一个简单的 TCP 端口探测 `HEALTHCHECK`。若需要替换为 HTTP：
修改 Dockerfile：
```
HEALTHCHECK CMD python - <<'PY'
import urllib.request,sys,os
url=f"http://127.0.0.1:{os.environ.get('APP_PORT','8002')}/docs"
try:
	with urllib.request.urlopen(url,timeout=3) as r:
		sys.exit(0 if r.status<500 else 1)
except Exception:
	sys.exit(1)
PY
```

### 常见问题
| 问题 | 可能原因 | 解决 |
|------|----------|------|
| 容器启动后访问不到 | Host 端口没映射或进程未启动 | 检查 `-p` 参数 / 容器日志 |
| pandas 安装慢 | 缺少缓存 | 镜像构建层缓存会加速第二次构建 |
| 需要连接数据库超时 | 未配置环境变量 / 网络策略 | 设定正确的 `config.yaml` 外挂目录 |



