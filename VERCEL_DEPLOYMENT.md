# Vercel 部署说明

## 部署结论

当前项目可以部署到 Vercel。

项目结构已调整为：

- 静态前端：`index.html`、`app.js`、`styles.css`
- Vercel Python API：`api/analyze.py`
- 本地后端兼容入口：`server.py`
- Vercel 配置：`vercel.json`

## Vercel 项目配置参数

在 Vercel 导入 GitHub 仓库后，使用以下配置：

| 配置项 | 参数 |
|---|---|
| Framework Preset | Other |
| Build Command | `npm run build` |
| Output Directory | `dist` |
| Install Command | 留空或使用 Vercel 默认 |
| Root Directory | 项目根目录 |
| Node.js Version | 18 或以上 |
| Python Runtime | Vercel 自动根据 `api/analyze.py` 与 `requirements.txt` 识别 |

## 环境变量

基础演示模式不需要配置真实 OCR Key。未配置 `OPENAI_API_KEY` 时，系统会自动使用本地演示模式。

如需真实 OCR / Vision 分析，请在 Vercel 项目设置中添加：

| Key | Value | 必填 |
|---|---|---|
| `OPENAI_API_KEY` | 你的 OpenAI API Key | 真实 OCR 模式必填 |
| `OPENAI_MODEL` | `gpt-4o-mini` | 可选 |

不建议在 Vercel 配置：

| Key | 原因 |
|---|---|
| `HOST` | Vercel Serverless 不需要长驻监听地址 |
| `PORT` | Vercel Serverless 不需要手动指定端口 |

## GitHub 导入部署流程

1. 打开 Vercel Dashboard。
2. 点击 `Add New Project`。
3. 选择 GitHub 仓库：`lpqq18/ecommerce-dispute-tool`。
4. Framework Preset 选择 `Other`。
5. 确认 Build Command 为 `npm run build`。
6. 确认 Output Directory 为 `dist`。
7. 如需真实 OCR，在 Environment Variables 添加 `OPENAI_API_KEY`。
8. 点击 `Deploy`。

## 本地部署前自检

```bash
npm run build
python -m py_compile server.py api/analyze.py
```

通过后应看到：

- `dist/index.html`
- `dist/app.js`
- `dist/styles.css`
- `dist/server.py`
- `dist/requirements.txt`

## API 路径

前端当前调用：

```text
/api/analyze
```

Vercel 对应入口：

```text
api/analyze.py
```

请求方式：

```text
POST multipart/form-data
字段名：images
数量：1-5 张
格式：PNG / JPG / WebP
```

## 注意事项

1. Vercel Function 是无状态函数，不适合保存用户上传文件。当前项目没有文件存储，符合 MVP 要求。
2. 图片总大小限制仍由后端控制为 25MB，但真实部署还会受 Vercel 请求大小和函数执行时长限制影响。
3. 真实 OCR 模式下，请重点观察函数执行时间；如图片过大或 OCR 调用过慢，可能需要压缩图片或升级 Vercel 函数时长配置。
4. `dist/` 是构建产物，已被 `.gitignore` 排除，Vercel 会在部署时重新运行 `npm run build` 生成。
