# 电商纠纷证据包助手

E-commerce Dispute Evidence Pack Copilot MVP。

用户上传聊天记录、订单详情、物流凭证、商品规格或售后截图后，系统生成：

- 证据结构化
- 法证时间线
- 纠纷风险分
- 申诉胜率分
- 判决方向
- 证据权重与冲突检测
- 平台申诉文本

## 当前状态

- 默认不接真实 OCR，未配置 `OPENAI_API_KEY` 时使用本地演示模式。
- 已加入证据缺字段评分护栏：关键字段缺失时会限制申诉胜率，避免“证据不清但胜率过高”。
- 已完成 80 张截图式噪声样本回归测试。
- V1.1 已升级为 Case 驱动工作台：每次上传都会生成 Case，并记录 AI Trace、用户行为日志、系统日志和 AI 推理日志。
- `/cases` 与 `/logs/*` 已支持 `limit` / `offset` 分页参数。
- 如公开部署，请配置 `ADMIN_TOKEN` 保护日志接口；未配置时默认本地开放，方便开发测试。

## 本地启动

```powershell
python server.py
```

打开：

```text
http://127.0.0.1:4173
```

## 服务器启动

```powershell
pip install -r requirements.txt
$env:HOST="0.0.0.0"
$env:PORT="4173"
python server.py
```

如需真实 OCR / Vision 分析，请参考 `.env.example`，在本机或部署平台的环境变量面板中配置 `OPENAI_API_KEY` 与 `OPENAI_MODEL`。

公开访问前建议额外配置：

```text
ADMIN_TOKEN=自定义后台访问令牌
```

线上长期保存 Case 历史时，不建议使用默认 JSON 存储。Vercel 环境应接入 Vercel KV、Postgres、Supabase 等持久化数据库。

## Vercel 部署

项目已包含 `vercel.json` 与 `api/analyze.py`，可以作为静态前端 + Python Serverless API 部署到 Vercel。

详细配置见：`VERCEL_DEPLOYMENT.md`

## 核心文件

- `server.py`：后端接口、演示模式、OpenAI Vision 调用、评分护栏
- `case_store.py`：本地 Case、Trace 与三层日志存储
- `index.html`：上传页、流水线页、结果页结构
- `app.js`：上传交互、接口调用、结果渲染、复制申诉文本
- `styles.css`：中文法务控制台 UI 样式
- `api/analyze.py`：Vercel Python API 入口
- `vercel.json`：Vercel 构建、输出目录与函数配置
- `VERCEL_DEPLOYMENT.md`：Vercel 部署说明
- `qa_outputs/ocr_noise_guardrail_summary.md`：最新 QA 回归汇总
