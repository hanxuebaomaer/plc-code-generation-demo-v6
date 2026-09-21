# 工业代码工作台 Demo v8

独立的多语言代码生成与辅助审查演示项目。基于 v7 的 FastAPI 单服务部署方式扩展，旧目录与旧服务无需修改。

## 已部署的 v8 演示

- 公网网址：[https://industrial-code-demo-v8.onrender.com/](https://industrial-code-demo-v8.onrender.com/)
- 发布日期：2026-09-21；服务独立于旧站，运行版本为 8.0.0。
- 部署源码位于现有仓库的独立 `demo-v8` 分支；旧站继续使用 `main` 分支。
- 当前使用 Render Free、Ohio 区域；空闲后可能休眠，首次打开请等待唤醒。公开访问会消耗服务器模型额度。
- 已核验页面访问、六类场景的 ST/C++ 生成与辅助审查、普通问候和文本文件导入。检查记录见 `TESTING.md`。

## 本次升级

- 全新工作台界面：轨道交通场景、需求输入、代码输出、处理流程、检测项及需求对应证据。
- 六类可编辑示例：操作端判断、机车方向控制、撒砂控制、机车停放制动、里程计算、轮缘润滑及测试。
- 文本输入，以及 TXT / Markdown / 代码文本 / DOCX / 文字型 PDF 导入。2 MB、20000 字符限制；PDF 不超过30页。扫描图片不做 OCR，旧 DOC 请另存。
- ST 和 C++17 两种语言。复制、导出 `.st` 或 `.cpp`，代码生成时持续返回内容。
- 边生成边做增量结构检查，完整代码返回后做结构检查与模型辅助需求审查。显示依据及修改建议，不显示内部推理过程。
- 需求或语言修改立即使旧代码及旧检查失效；取消或断流不把半截代码当成完整结果。
- 优先使用服务器配置的在线模型。只有操作端判断、里程计算的**原样内置需求**支持离线参考；修改过的需求绝不按单个关键词套用不相关模板。

## 验证范围

本系统是离线演示工具，不连接真实车辆。界面“初步通过”仅表示规则或模型审查在相应项中未发现问题，**不等同于编译、动态仿真、生成准确率测定、实车测试或安全认证**。运行环境、硬件接口、厂商 ST 扩展和实际安全要求仍需工程人员确认。

C++ 以独立控制类及 update 周期接口为目标，不默认提供 main，不运行用户代码。生成的 ST 和 C++ 均需在目标工具链中另行编译与测试。

## 本地运行（Windows，Python 3.12 64位）

1. 将本目录完整解压。
2. 将 `.env.example` 复制为 `.env`，填写三个服务器模型配置。真实密钥不得进入仓库、压缩包或浏览器代码。
3. 双击 `run_demo_windows.bat`。脚本固定检查 Python 3.12 64位、创建独立环境、安装依赖并在服务就绪后打开浏览器。
4. 本地网址默认 `http://127.0.0.1:8000/`，本机地址不能发给其他电脑作为公网网址。

也可手动运行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
```

## 服务器配置

| 变量 | 含义 |
| --- | --- |
| LLM_API_BASE | 兼容 Chat Completions 的地址前缀；必要时含 `/v1` |
| LLM_API_KEY | 服务器密钥，仅在托管平台环境变量内填写 |
| LLM_MODEL | 该服务支持的模型名 |
| LLM_CODE_MAX_TOKENS | 代码输出上限，默认6000，可设2000–12000；不是固定代码行数 |
| LLM_TIMEOUT_SECONDS | 上游单次读取等待上限，默认90秒 |
| LLM_DISABLE_THINKING | 默认true，兼容服务不接受扩展参数时自动去除重试 |
| ALLOW_FALLBACK | 默认true，只对完全匹配的内置参考需求启用 |
| MAX_CONCURRENT_JOBS | 单进程同时生成/审查数量，默认4 |
| JOB_TIMEOUT_SECONDS | 单任务总时限，默认240秒 |
| REQUESTS_PER_MINUTE | 单来源请求上限，默认30；代理环境建议在入口另设限流 |
| ALLOWED_ORIGINS | 同源部署默认留空，无需开放跨域 |
| PORT | 托管平台提供的端口，默认8000 |

配置检查只表明参数齐全，不证明上游模型此刻在线。公开健康接口不返回模型名称、地址或密钥。

## Render 新建独立公网服务

不要覆盖旧服务，也不要向旧服务正在自动部署的分支直接推送。

1. 将本目录内的源文件提交到**新仓库或独立 v8 分支**，确认根目录有 Dockerfile、requirements.txt、main.py、static/。
2. Render 新建 Web Service，连接该仓库/分支，Runtime选择Docker；也可从本目录的 `render.yaml` 创建 Blueprint。
3. 服务名使用中性 Demo 名称，例如 `industrial-code-demo-v8`，若占用则添加短后缀。模板默认Ohio和Free，创建时以账户可选项为准。
4. 在新服务 Environment 填写 LLM_API_BASE、LLM_API_KEY、LLM_MODEL。不要将环境文件上传到GitHub。
5. Health Check Path 为 `/health`。Dockerfile 已包含启动命令：

```sh
python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
```

6. 部署为 Live 后，打开该服务面板显示的 HTTPS `onrender.com` 地址。本文开头列出了本次已发布并核验的地址；如果自行创建另一项服务，应以新服务面板实际分配的网址为准。
7. 检查 `/health` 返回 version `8.0.0`；测试 ST、C++、文件导入和完整审查。确认旧网址仍是原版本。

免费服务可能休眠，首次访问需要等待唤醒，亦受额度/资源约束。正式演示可由账户所有人选择合适的付费实例，费用及配额以平台当前控制台为准；本项目不自动购买或升级实例。

参考官方部署说明：https://render.com/docs/web-services

## Railway / 云服务器 Docker

Railway：新建项目并连接独立 v8 仓库或分支，使用根目录 Dockerfile；配置三个模型环境变量，将健康检查设为 `/health`，在 Networking 中生成公共域名。使用平台分配的 PORT，不要复用旧服务资源。收费与试用资格以当前控制台为准。

云服务器：配置 `.env` 后运行 `docker compose up -d --build`。将反向代理指向8000端口，配置域名及HTTPS证书，对流式接口关闭代理缓冲（Nginx `proxy_buffering off`），读取超时应大于240秒。对公网入口设置适当限流，避免滥用消耗模型额度。不要关闭证书校验或将密钥放进URL。

## 接口

| 接口 | 用途 |
| --- | --- |
| GET /health | 存活检查，版本及配置就绪标志 |
| GET /api/scenarios | 六类中性场景需求 |
| POST /api/import-file | multipart file，返回提取文本及导入提示 |
| POST /api/generate-stream | requirement + language(st/cpp)，SSE 代码/检查/阶段事件 |
| POST /api/validate-stream | requirement + language + code，SSE 审查事件 |
| POST /api/generate-code | 非流式兼容接口，完整代码及报告 |
| POST /api/validate-code | 非流式统一六项报告 |

SSE 事件：stage、delta、code、checks、notice、chat、error、done。delta 是暂存代码片段；只有 code 事件代表完整代码。检查的六个固定 id 在前后端一一对应。验证结果绑定代码摘要，旧任务不能覆盖新需求的结果。

代码缓存仅复用相同语言和相同完整需求，保留1小时，最多32项；变更参数、大小写或语言不会错用旧结果。上传文档仅在内存中提取，原文件不保存；生成结果缓存是进程内内存，不是持久化数据库。

## 测试与维护

```sh
python -m unittest discover -s tests -v
```

测试包括语言隔离、ST成对结构、C++结构、流式顺序、断流保护、模型失败行为、六项对应、上传边界和中断处理。测试不以模型自评替代真实编译或安全测试。

源码不依赖外部前端 CDN，静态资源由同一个 FastAPI 服务托管。视觉参考成熟组件式工作台布局，使用独立编写的 HTML/CSS/SVG，无第三方品牌图形。

本项目保留 V7 的单服务架构、兼容调用接口和模型配置方式，新增分层结构检查、文件解析和可追踪的流式流水线。旧项目保持不变。
