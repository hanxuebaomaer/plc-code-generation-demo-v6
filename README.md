# 工业代码工作台 · Demo v9

面向轨道交通控制场景的 ST / C++17 代码生成与辅助审查演示。单个 FastAPI 服务托管网页与接口，无需 Node.js。源码包不包含模型密钥。

## v9 更新

- 桌面三栏工作台：左侧需求、中间代码、右侧代码验证。去掉大幅宣传区，适配 1366×768 等常见电脑尺寸；长代码、需求和审查详情在各面板内部滚动。
- 保留六个场景、文本与文件导入、ST/C++切换、流式生成、复制、导出、重新验证、停止处理等功能。
- 生成提示强化状态机、跨周期闭锁、互斥、数值边界和停止优先级。
- 遇到可确定修正的缺陷，最多追加两轮代码改进及独立复核，无问题时不增加调用。仅在检查没有新增退步且问题数量减少时采用修正结果；否则保留原代码及真实结论。
- 检测项保留六项且与结果一一对应。审查聚焦原需求，不把未做编译或可选功能当作源码缺陷。需求依据按3—5组简要说明，建议仅列需要修改或确认的事项。
- 通过项的依据默认收起，问题优先展示；所有返回的检查依据仍可展开查看。不会为了展示把真实问题改成“通过”。

“初步通过”仅指本次结构规则与模型静态辅助审查未发现问题，不保证工程正确率，不代表编译、仿真、车辆测试或安全认证通过。本 Demo 不连接真实车辆。

## 在线部署

v9 应使用独立的 `demo-v9` 分支和新的 Web Service，不覆盖原 v8 服务。公网地址以新服务面板实际分配的网址为准。

### Render

1. 将本目录文件上传至专用于 v9 的仓库或分支，确保 Dockerfile 在根目录。
2. 在 Render 新建 Web Service，选择 v9 分支、Docker、服务名称 `industrial-code-demo-v9`（如重名则调整）。
3. 实例按需求选择 Free；本项目不会自动购买付费套餐。区域可选择 Ohio，按账户当前可选项为准。
4. 在服务环境变量配置 `LLM_API_BASE`、`LLM_API_KEY`、`LLM_MODEL`。地址使用模型的兼容 Chat Completions 地址，通常以 `/v1` 结尾。密钥只保存在服务器，不提交到Git。
5. 建议设置 `JOB_TIMEOUT_SECONDS=360`、`LLM_CODE_MAX_TOKENS=6000`、`LLM_DISABLE_THINKING=true`。健康检查 `/health`，由平台设置 PORT。
6. 部署成为 Live 后，打开服务面板显示的 HTTPS 网址，再测试生成和验证。

也可使用 `render.yaml` 创建 Blueprint，配置相同环境变量。Free 可能因闲置而休眠，首次访问要等待唤醒；正式演示如需持续运行，由账户所有者按平台现行价格自行选择付费实例。公网生成会消耗模型账户额度，请关注使用量。

### Railway / 自有云服务器

Railway：创建独立项目，连接 v9 分支，使用 Dockerfile；配置三个模型环境变量和 `/health` 健康检查，在 Networking 生成公网域名。费用及试用资格以平台控制台为准。

云服务器：复制 `.env.example` 为 `.env`，配置模型后运行 `docker compose up -d --build`。使用域名与 HTTPS 反向代理指向8000端口。对流式接口关闭代理缓冲（如 Nginx `proxy_buffering off`），读取超时大于360秒。不要暴露环境文件、在URL中放密钥或关闭证书校验。生产用途应增加身份认证与更严格的入口限流。

## 本地 Windows

安装 Python 3.12 64位及 Python Launcher。双击 `run_demo_windows.bat` 会验证版本并创建 `.venv`、安装依赖，随后打开 `http://127.0.0.1:8000`。

首次运行会从 `.env.example` 创建本地 `.env`，需要填写服务器模型配置。没有配置时仅提供严格匹配的有限离线参考示例，不会用无关模板代替输入需求。已有不匹配的虚拟环境不会被自动删除。

如果手动运行：

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

容器启动命令为：

```sh
python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
```

## 使用

1. 选择操作端判断、机车方向控制、撒砂控制、机车停放制动、里程计算、轮缘润滑及测试中的场景，或编辑自己的需求。
2. 也可导入 TXT、DOCX、文字型PDF及代码文本，最大2MB、提取文字不超过20000字符。扫描PDF不做OCR，文件只在内存解析，不保存原文件。
3. 选择 ST 或 C++17，点击“生成并验证”。中间同步展示代码，右侧展示处理过程、六项检查和最终结论。
4. 生成遇到可修正项时自动改进并复核，最多两轮。审查结果始终绑定最终代码；中途变更需求或语言会使旧结果失效。
5. 完整代码可复制或导出 `.st` / `.cpp`。点击“重新验证”只审查当前代码，不修改代码。
6. 需求对应与修改建议默认简要呈现，点击标题可展开；问题项不会被隐藏为通过。

## 接口及约束

|接口|功能|
|---|---|
|GET /health|版本、配置就绪状态，不返回密钥及供应商信息|
|GET /api/scenarios|六类示例需求|
|POST /api/import-file|提取文件文字|
|POST /api/generate-stream|流式生成、同步检查、必要时改进、最终审查|
|POST /api/validate-stream|仅流式审查当前代码|
|POST /api/generate-code|兼容非流式生成接口|
|POST /api/validate-code|兼容非流式审查接口|

请求参数使用 `requirement`、`language`（`st`/`cpp`），验证增加 `code`。SSE包含stage/delta/code/checks/notice/chat/error/done；有自动改进时可收到第二个code事件，以最后一个完整code及匹配code_id的报告为准。

生成缓存按完整需求及语言隔离，最多32项、有效1小时。模型断流、审查失败、超时会保留准确状态，不伪造通过。默认同源，无需CORS通配符。模型及导入内容一律作为数据处理，不执行生成代码。

## 测试及设计参考

```sh
python -m unittest discover -s tests -v
```

验证记录见 `TESTING.md`。包括接口、上传、异常路径、真实模型流程和界面尺寸检查。实际代码仍需目标编译器及仿真环境复核。

界面参考 [Ant Design Layout](https://ant.design/components/layout/) 的工作区分层及 [shadcn/ui Sidebar](https://ui.shadcn.com/docs/components/sidebar) 的紧凑组件组织，自行编写HTML/CSS/SVG，未引入外部CDN、商标资源或框架运行时。保持原项目轻量单服务部署。
