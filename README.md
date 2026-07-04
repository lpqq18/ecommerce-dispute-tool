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

- 默认未配置真实 OCR / Vision 时使用本地演示模式。
- P0 已加入可插拔 OCR 层：支持外部 OCR API、本地 PaddleOCR 以及演示兜底；Case 详情页会展示 OCR 原始结果。
- P1 已加入 OCR 文本结构化引擎：真实 OCR 文本可在未配置 OpenAI Key 时先走规则分析，输出纠纷类型、买家主张、商家动作、订单/物流状态、时间节点、冲突检测和申诉文本。
- P2 已加入节点化工作流：OCR、证据抽取、冲突分析、最终判断均作为独立节点执行，支持节点级 Trace、自动重试和手动重试。
- P3 已加入观测事件层：每个工作流节点都会记录 observation，可在 `/admin/logs` 中筛选“观测事件”，也可通过 `OBSERVABILITY_WEBHOOK_URL` 上报外部平台。
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

如需先接真实 OCR，可选择两种方式：

```text
# 推荐：外部 OCR 微服务，主应用通过 HTTP 调用
OCR_PROVIDER=external
OCR_API_URL=https://your-ocr-service.example.com/ocr
OCR_API_TOKEN=可选

# 本地开发：安装 PaddleOCR 后启用
OCR_PROVIDER=paddle
```

如需接入外部观测平台，可配置：

```text
OBSERVABILITY_ENABLED=1
OBSERVABILITY_WEBHOOK_URL=https://your-observability-service.example.com/events
OBSERVABILITY_WEBHOOK_TOKEN=可选
```

未配置外部地址时，观测事件仍会写入本地日志，可在 `/admin/logs` 查看。

外部 OCR 服务建议返回：

```json
{
  "images": [
    {
      "filename": "chat.png",
      "blocks": [
        { "text": "买家：我没收到货", "confidence": 0.98, "bbox": [0, 0, 100, 40] }
      ]
    }
  ]
}
```

未配置 OCR 时，系统会继续创建 Case 并走演示兜底，但 OCR 审计区会明确显示“演示兜底”。

公开访问前建议额外配置：

```text
ADMIN_TOKEN=自定义后台访问令牌
```

线上长期保存 Case 历史时，不建议使用默认 JSON 存储。Vercel 环境应接入 Vercel KV、Postgres、Supabase 等持久化数据库。

## Vercel 部署

项目已包含 `vercel.json` 与 `api/analyze.py`，可以作为静态前端 + Python Serverless API 部署到 Vercel。

详细配置见：`VERCEL_DEPLOYMENT.md`

## 核心文件

- `server.py`：后端接口、演示模式、OpenAI Vision 调用、OCR 调度、评分护栏
- `case_store.py`：本地 Case、Trace 与三层日志存储
- `ocr_service.py`：可插拔 OCR 层，支持外部 OCR API、本地 PaddleOCR 与演示兜底
- `evidence_engine.py`：P1 规则结构化引擎，将 OCR 文本转成案件事实、冲突判断与申诉材料
- `workflow_engine.py`：轻量节点工作流，负责节点执行、Trace、失败重试与状态流转
- `observability.py`：P3 观测事件层，负责节点 observation、本地观测日志与可选外部上报
- `index.html`：上传页、流水线页、结果页结构
- `app.js`：上传交互、接口调用、结果渲染、复制申诉文本
- `styles.css`：中文法务控制台 UI 样式
- `api/analyze.py`：Vercel Python API 入口
- `vercel.json`：Vercel 构建、输出目录与函数配置
- `VERCEL_DEPLOYMENT.md`：Vercel 部署说明
- `qa_outputs/ocr_noise_guardrail_summary.md`：最新 QA 回归汇总
