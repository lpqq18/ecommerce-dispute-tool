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

## 核心文件

- `server.py`：后端接口、演示模式、OpenAI Vision 调用、评分护栏
- `index.html`：上传页、流水线页、结果页结构
- `app.js`：上传交互、接口调用、结果渲染、复制申诉文本
- `styles.css`：中文法务控制台 UI 样式
- `qa_outputs/ocr_noise_guardrail_summary.md`：最新 QA 回归汇总
