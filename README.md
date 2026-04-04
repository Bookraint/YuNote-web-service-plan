# YuNote 网页化落地步骤

本文档整理自本地 YuNote（Python 桌面应用）改为网页服务时的目标架构、实施顺序与运维要点。转录使用 **ElevenLabs**，总结使用 **Qwen**（与桌面端相同，经 OpenAI 兼容接口，如 SiliconCloud 等，见 `app/common/config.py`）。

---

## 一、目标架构（摘要）

| 层级 | 建议 |
|------|------|
| 客户端 | 浏览器 SPA 或轻量前端；上传音频、查看进度、展示/下载转录与总结 |
| API | Python **FastAPI**（或 Starlette）：REST，可选 **SSE** / **WebSocket** 推送进度 |
| 后台任务 | 转录与长文总结耗时长，使用 **异步队列**（Celery+Redis、RQ、Arq 等）与 Web 进程分离 |
| 存储 | 开发期可沿用「笔记目录 + `meta.json`」思路；上线建议 **对象存储** + **数据库**（PostgreSQL / SQLite）记录任务状态 |

**数据流**：音频上传 → 队列 → `transcribe`（ElevenLabs）→ 转录文本 → `Summarizer`（Qwen）→ Markdown 总结 → 持久化并返回前端。

**与现有代码关系**：复用 `app/core/asr/transcribe`、`ChunkedASR`、`app/core/summary/summarizer` 等；将桌面 `cfg` 替换为服务端环境变量；**ElevenLabs 建议改为官方 API Key 调用**（密钥仅服务端持有）。

---

## 二、代码与工程（仓库内要做的事）

1. **抽离桌面依赖**：Web 端不引入 PySide/Qt；转录与总结可被 HTTP 或 Worker 直接调用。
2. **ElevenLabs**：接入官方 **Speech-to-Text**（`xi-api-key` 等），与现有分块/限流逻辑对齐。
3. **Qwen**：配置 OpenAI 兼容的 `base_url`、`api_key`、`model`（如 DashScope）。
4. **Web 层**：实现上传、创建任务 ID、查询状态、（可选）流式进度、下载转录与总结。
5. **长任务模型**：选择后台队列或单进程 BackgroundTasks；大文件需超时、重试与临时文件清理。
6. **持久化**：任务状态与用户（若有多用户）写入数据库；文件落盘或对象存储。
7. **可观测性**：请求 ID、外部 API 错误码、队列失败重试与日志。

---

## 三、账号与外部服务（复用本地已有配置）

网页服务侧不必重新「找一套新平台」，与桌面版对齐即可：**密钥与模型名沿用你在 YuNote 里已经填好的值**，上线时改为从服务端环境变量或密钥管理读取（与 `app/common/config.py` 中的项一一对应）。

1. **ElevenLabs（转录）**  
   - 桌面端配置项见 `Config`：`elevenlabs_model_id`（默认 `scribe_v1`）、`elevenlabs_diarize`、`elevenlabs_tag_audio_events`（`app/common/config.py` 中 `[ElevenLabs]` 段）。  
   - 本地已生效的值在 **`YuNote/AppData/settings.json`**（随应用数据目录可能略有不同）。  
   - Web 服务实现时：把这些字段映射为环境变量（或等价配置），并继续走现有 `TranscribeConfig` → `ElevenLabsASR` / 分块逻辑；若日后改为官方 API Key 鉴权，仍复用同一套「模型 ID + diarize + 分块/限流」语义。

2. **Qwen / OpenAI 兼容 LLM（总结）**  
   - 桌面端由 `llm_service` 选择供应商，`TaskFactory._get_llm_config()` 汇总为 `(base_url, api_key, model)` 写入 `SummaryConfig`（见 `app/core/task_factory.py`）。  
   - 若你本地已用 **SiliconCloud** 跑 Qwen，对应 `silicon_cloud_api_base`、`silicon_cloud_api_key`、`silicon_cloud_model`（默认 `Qwen/Qwen2.5-7B-Instruct` 与 `https://api.siliconflow.cn/v1`）；若用 **OpenAI 兼容** 其它端点，则对应 `openai_*` 或其它已选服务的键。  
   - Web 端同样：**直接复用这三元组**，无需为「网页版」单独再申请一套账号（除非你想隔离配额）。

3. **域名**（若公网访问）：购买域名并配置 HTTPS 证书（与本地代码无绑定，单独准备即可）。

---

## 四、部署与用户场景（大陆用户 · 微信内打开 · 不备案）

**前提**：主要用户在大陆；**不办理 ICP 备案**；计划在**微信聊天中直接发链接**让用户打开。

**常见做法**：

- **服务器**：放在**境外**（香港、新加坡、日本等），域名解析到该主机，全站 **HTTPS**。避免使用「必须备案才能公网访问」的**大陆机房建站**方案（除非改策略）。
- **线路**：优先对大陆访问较友好的机房或线路，减少「打不开、一直加载」。
- **微信内体验**：页面需**移动端适配**；避免混合内容（HTTP/HTTPS 混用）、过多跳转；控制首屏体积。
- **业务链路上的注意**：ElevenLabs 多在境外，应用机放在**香港/新加坡**往往有利于调外网 API；Qwen 所用网关若在境内，需从境外机**实测**调用稳定性与时延。

**合规提示**：是否备案与是否仍需隐私政策、用户协议等无必然绑定；若对公众提供录音转写服务，建议按实际情况准备基本说明文件。

---

## 五、上线与安全 Checklist

- [ ] API Key 仅服务端配置（环境变量或密钥管理），不入库、不下发浏览器。
- [ ] HTTPS、CORS 仅允许自有前端域名（若分离部署）。
- [ ] 上传限流与单用户/全站配额，防止滥用第三方 API。
- [ ] 大文件：分片上传、大小上限、弱网重试（微信内网络差异大）。
- [ ] 日志与告警：进程存活、队列积压、磁盘空间、5xx。
- [ ] 备份策略（数据库与重要对象存储）。

---

## 六、建议实施顺序

1. **本地跑通**：环境变量配置 ElevenLabs + Qwen，无 UI 调用现有 `transcribe` → `Summarizer` 全链路。
2. **接入官方 ElevenLabs 密钥方式**，并做集成测试（含长音频、分块）。
3. **实现 FastAPI（或等价）+ 最小任务状态存储**，再视负载加入队列。
4. **选境外主机与域名**，手机微信实测打开链接、上传与进度。
5. **限流、监控、备份** 再随流量逐步加强。

---

## 七、参考：仓库内相关路径

- 转录入口：`app/core/asr/transcribe.py`
- ElevenLabs：`app/core/asr/elevenlabs.py`（上线前应对照官方 API 调整鉴权方式）
- 总结：`app/core/summary/summarizer.py`
- 任务配置：`app/core/task_factory.py`、`app/core/entities.py`

---

## 八、本仓库：自定义场景 Prompt

打开网页后点右上角 **「场景 Prompt」**，可在线编辑四套模板并保存，**下次总结立即使用**（无需重启）。亦可直接改磁盘上的 **`prompts/summary_*.md`**；或通过环境变量 **`PROMPTS_DIR`** 指向自定义目录。模板中必须包含占位符 **`{{transcript}}`**。详见 **`prompts/README.md`**。

---

*文档为规划说明，具体接口与配置以各服务商最新文档为准。*
