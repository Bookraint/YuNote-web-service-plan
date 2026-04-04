# 场景总结 Prompt（用户可改）

总结阶段会按网页里选的「场景」读取本目录下对应 Markdown 文件，把转录正文注入占位符 **`{{transcript}}`** 后发给 LLM。

**推荐**：在网页右上角点 **「场景 Prompt」**，在线编辑四套模板并保存，**立即生效**（无需重启服务）。本目录下的文件与网页保存内容一致，也可直接用编辑器改文件。

| 文件名 | 对应场景 |
|--------|----------|
| `summary_general.md` | 通用 |
| `summary_meeting.md` | 会议 |
| `summary_lecture.md` | 课程 |
| `summary_interview.md` | 访谈 |

## 怎么改

1. 直接编辑上表中的文件（保持文件名不变）。
2. 模板里必须保留 **`{{transcript}}`**，程序会把转录全文替换到这里。
3. 改完后**重启** `python run_web.py` 生效（服务启动时读文件）。

## 换一整套目录（部署到服务器时）

在 `.env` 里设置：

```env
PROMPTS_DIR=/path/to/your/prompts
```

该目录下仍需包含上述四个文件名。留空则使用本项目自带的 `prompts/` 目录。
