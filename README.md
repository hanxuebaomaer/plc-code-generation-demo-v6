# 工业PLC代码生成与验证平台 Demo v7

本项目为单服务、单端口的公网部署版本。FastAPI 同时托管前端静态资源和后端接口，部署完成后只需分享一个网址即可访问。

## 本版改进

- 强化需求约束：模型生成前会把设备、输入输出、时序、故障和参数整理为覆盖清单；
- 生成结果经过需求一致性检查，发现跑题、过短或缺项时由模型定向修正一次；
- PID、三电机顺序启动等复杂工况要求输出完整变量、定时器或状态及保护逻辑；
- 仅在模型服务异常、输出截断或连续不合格时使用按工况区分的本地安全输出；
- 复用 HTTP 长连接并关闭推理思考模式，缩短模型服务响应时间；
- 对相同的成功需求启用短期内存缓存，重复演示可快速返回；
- “检测项”和“验证结果总览”均为六项，并保持一一对应。

## 主要功能

- 自然语言需求生成 IEC 61131-3 Structured Text（ST）代码；
- 普通问候正常回复，不强制输出代码；
- 代码复制和 .st 文件导出；
- 语法、POU结构、输入输出变量、命名、逻辑一致性和规范符合性检查；
- 典型工况示例与稳定的本地辅助检查；
- /health 健康检查；
- Docker、Render、Railway 和普通云服务器部署。

注意：验证功能属于结构与逻辑辅助检查，不等同于目标PLC平台的编译、仿真或现场安全验证。

## 目录

    20260815_demo_v7/
    ├── main.py
    ├── llm_client.py
    ├── validator_fallback.py
    ├── static/
    │   ├── index.html
    │   ├── styles.css
    │   └── app.js
    ├── requirements.txt
    ├── .env.example
    ├── Dockerfile
    ├── docker-compose.yml
    ├── render.yaml
    ├── .dockerignore
    ├── .gitignore
    ├── run_demo_windows.bat
    └── README.md

## 模型服务配置

项目调用 OpenAI-compatible Chat Completions 接口。密钥只通过本地 .env 或部署平台环境变量提供，仓库中不得保存真实密钥。

    LLM_API_BASE=https://your-model-service.example/v1
    LLM_API_KEY=在本地或部署平台填写
    LLM_MODEL=your-model-name
    LLM_TIMEOUT_SECONDS=60
    LLM_CODE_MAX_TOKENS=3800
    LLM_DISABLE_THINKING=true
    GENERATION_CACHE_TTL_SECONDS=3600
    GENERATION_CACHE_MAX_ENTRIES=64
    LOG_LEVEL=INFO

以后切换自有模型时，只需替换 LLM_API_BASE、LLM_API_KEY 和 LLM_MODEL，前端无需修改。

## 本地 Windows 运行

1. 安装 Python 3.12 64位，并勾选 Add Python to PATH；
2. 将 .env.example 复制为 .env，填写模型服务配置；
3. 双击 run_demo_windows.bat；
4. 浏览器访问 http://127.0.0.1:8000。

脚本会自动创建 .venv、安装依赖并启动服务。

手动启动：

    py -3.12 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install -r requirements.txt
    python -m uvicorn main:app --host 0.0.0.0 --port 8000

## Docker 运行

    cp .env.example .env
    docker compose up --build -d

访问 http://localhost:8000，健康检查：

    curl http://localhost:8000/health

## Render 部署

1. 将项目推送到 GitHub/GitLab，确认 .env 未提交；
2. Render 选择 New → Blueprint，连接仓库；
3. Render 读取根目录 render.yaml；
4. 在 Render 环境变量中填写 LLM_API_BASE、LLM_API_KEY 和 LLM_MODEL；
5. 等待构建、部署及 /health 检查通过；
6. Render 会生成 https://服务名称.onrender.com 公网网址。

也可新建 Web Service，Runtime 选择 Docker，健康检查路径填写 /health。Dockerfile 中的启动命令为：

    python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}

免费实例可能在空闲后休眠，首次访问需要等待唤醒。正式演示前建议提前打开网址预热；如需稳定在线，可选用付费实例。

## Railway 部署

1. 选择 Deploy from GitHub repo；
2. Railway 会识别根目录 Dockerfile；
3. 在 Variables 中填写模型环境变量；
4. 在 Settings → Networking → Public Networking 点击 Generate Domain；
5. 获得可分享的 up.railway.app 地址。

## 云服务器部署

    docker compose up --build -d

服务器应具有公网IP并开放相应端口。正式环境建议使用 Nginx/Caddy 反向代理到容器端口并配置 HTTPS。

## 健康检查

正常响应包含：

    {
      "status": "ok",
      "service": "plc-code-generation-demo",
      "version": "7.0.0",
      "llm_configured": true
    }

## 安全说明

- 不要将 .env 或 API Key 提交到 Git；
- 公网开放后，访问者的生成和验证操作会消耗模型额度；
- 演示结束后可关闭服务、增加访问控制或轮换密钥。
