# P7 OCR + DeepSeek 低成本方案

## 目标

采用低成本、可替换的两段式链路：

```text
纠纷截图 -> OCR 提取中文文本 -> DeepSeek 文本推理 -> 结构化证据 / 风险评分 / 申诉文本
```

## 配置项

```text
AI_PROVIDER=deepseek
DEEPSEEK_API_KEY=replace_with_key
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_API_BASE=https://api.deepseek.com

OCR_PROVIDER=external
OCR_API_URL=https://your-ocr-service.example.com/ocr
OCR_API_TOKEN=replace_with_optional_token
OCR_REQUIRE_REAL=1
OCR_MIN_TEXT_CHARS=20
```

## 行为规则

- `AI_PROVIDER=auto`：优先使用 DeepSeek，但前提是已配置 `DEEPSEEK_API_KEY` 且 OCR 已提取到文本；否则有 OpenAI key 时使用 OpenAI；都没有时使用演示/规则兜底。
- `AI_PROVIDER=deepseek`：强制使用 DeepSeek；如果没有 OCR 文本，不会让 DeepSeek 编造结果。
- `AI_PROVIDER=openai`：强制使用 OpenAI Vision / Responses API。
- OCR 可先接外部 API，后续再替换为 PaddleOCR 服务。

## 验证项

1. `/api/runtime` 中 `ai.deepseek_configured=true`。
2. `/api/runtime` 中 `ocr.external_configured=true`。
3. 上传真实截图后，OCR 审计区显示 `真实 OCR`。
4. AI Trace 中最终判断由 DeepSeek 输出。
5. 申诉文本不出现截图中不存在的订单号、物流号或时间。

## 当前状态

本阶段完成代码兼容，未内置任何密钥。上线前需要在服务器 PM2 环境配置 DeepSeek key 和 OCR 服务地址。
