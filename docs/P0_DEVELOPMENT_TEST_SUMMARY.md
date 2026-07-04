# P0 开发与测试留档：真实 OCR 接入通道

日期：2026-07-03

## 1. 开发目标

P0 的目标是让系统从“只跑演示流程”升级为“具备真实 OCR 接入能力”的案件分析底座。

本阶段不要求真实 OCR 准确率达标，重点验证：

- OCR 能作为独立模块接入
- Case 能保存 OCR 原始结果
- Trace 能记录 OCR 步骤
- OCR 失败能让 Case 可定位、可排错
- 未配置真实 OCR 时，系统必须明确显示演示兜底，不能假装识别成功

## 2. 开发内容

### 2.1 新增可插拔 OCR 层

新增文件：

- `ocr_service.py`

支持三种模式：

- `OCR_PROVIDER=external`：调用外部 OCR API
- `OCR_PROVIDER=paddle`：本地 PaddleOCR
- `OCR_PROVIDER=demo/auto`：演示兜底

OCR 输出统一为：

```json
{
  "provider": "external-or-paddle-or-demo",
  "real_ocr": true,
  "images": [
    {
      "filename": "chat.png",
      "blocks": [
        {
          "text": "买家：我没有收到货",
          "confidence": 0.98,
          "bbox": [10, 20, 180, 60]
        }
      ],
      "text": "..."
    }
  ],
  "warnings": [],
  "duration_ms": 120,
  "summary": "OCR 解析完成..."
}
```

### 2.2 Case 保存 OCR 结果

修改文件：

- `case_store.py`

新增字段：

```json
{
  "ocr_result": null
}
```

新增能力：

- `set_case_ocr(case_id, ocr_result)`

### 2.3 后端分析链路接入 OCR

修改文件：

- `server.py`
- `api/analyze.py`

分析流程调整为：

```text
上传图片
-> 创建 Case
-> OCR 解析
-> 写入 Case.ocr_result
-> 写入 OCR Trace
-> AI / 演示分析
-> 写入结果
```

如未配置 `OPENAI_API_KEY`，系统继续使用演示分析，但会把 OCR 模式写入结果。

### 2.4 前端新增 OCR 审计区

修改文件：

- `index.html`
- `app.js`
- `styles.css`

新增「OCR 原始结果」模块，展示：

- OCR provider
- 是否真实 OCR
- 图片数量
- 文本块数量
- OCR 警告
- 每张图识别文本

### 2.5 配置和部署说明

修改文件：

- `.env.example`
- `README.md`
- `VERCEL_DEPLOYMENT.md`

新增配置：

```text
OCR_PROVIDER=external
OCR_API_URL=https://your-ocr-service.example.com/ocr
OCR_API_TOKEN=optional
OCR_TIMEOUT_SECONDS=60
```

## 3. 测试情况

### 3.1 执行测试

已执行：

```text
python -m py_compile server.py case_store.py ocr_service.py api/analyze.py
node --check app.js
npm run build
```

结果：全部通过。

### 3.2 后端专项测试

| 测试项 | 结果 | 说明 |
|---|---:|---|
| 外部 OCR API 接入 | 通过 | 使用 mock OCR 服务验证真实 OCR 通道 |
| OCR 文本块标准化 | 通过 | `blocks/text/confidence/bbox` 可标准化 |
| Case 保存 OCR 结果 | 通过 | `ocr_result` 正确写入 Case |
| OCR Trace 写入 | 通过 | Trace 中包含 OCR 步骤 |
| OCR 失败处理 | 通过 | 外部 OCR 返回 500 时，Case 变为 failed |
| `/api/analyze` 兼容接口 | 通过 | 返回 `ocr_result` |
| `/case/analyze` 完整流程 | 通过 | Case 创建、异步分析、Trace 写入正常 |

### 3.3 前端检查

| 测试项 | 结果 |
|---|---:|
| OCR 审计区 DOM 存在 | 通过 |
| `renderOcrAudit` 渲染函数存在 | 通过 |
| OCR 样式存在 | 通过 |
| 构建产物包含 OCR 相关文件 | 通过 |

## 4. 评估结论

P0 达标。

当前系统已经具备真实 OCR 的接入口，并且能把 OCR 结果纳入 Case、Trace、结果页和日志链路。

需要注意：

- 当前尚未验证真实 PaddleOCR / 真实生产 OCR 的识别准确率
- 当前默认无 OCR 配置时仍是演示兜底
- Vercel 上不建议直接跑 PaddleOCR，推荐外部 OCR 微服务

## 5. 是否可进入下一阶段

可以进入下一阶段。

建议下一阶段重点：

- 将分析流程节点化
- 支持节点级 Trace
- 支持失败重试
- 明确 Case 状态流转
