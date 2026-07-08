# P7 免费 OCR + 本地规则推理方案

## 目标

采用不依赖付费推理 API 的免费链路：

```text
纠纷截图 -> RapidOCR 本地识别 -> 本地规则推理 -> 结构化证据 / 风险评分 / 申诉文本
```

## 服务器配置

```text
AI_PROVIDER=rules
OCR_PROVIDER=rapidocr
OCR_REQUIRE_REAL=1
OCR_MIN_TEXT_CHARS=20
```

## 行为规则

- `AI_PROVIDER=rules`：强制使用本地规则推理，不调用 DeepSeek/OpenAI。
- `OCR_PROVIDER=rapidocr`：使用服务器本地开源 OCR，不需要外部 OCR key。
- OCR 识别不到足够文本时，Case 会失败并写入系统日志，避免空图生成误导结论。
- 后续如果要增强效果，可以再接 DeepSeek/OpenAI/百度 OCR，但不是当前必需项。

## 验证项

1. `/api/runtime` 中 `ocr.provider=rapidocr`。
2. `/api/runtime` 中 `ai.active_provider=rules`。
3. 上传测试截图后，OCR 审计区显示 `真实 OCR`。
4. 结果页能生成纠纷类型、风险评分、申诉胜率、证据缺口和申诉文本。

## 当前状态

RapidOCR 已部署在服务器虚拟环境中，规则推理不需要任何 API Key。
