# 自有服务器部署说明

目标访问地址：

```text
https://top.tejarvis.info/ecommerce-dispute-tool/
```

## 1. DNS 配置

在域名解析后台添加：

```text
主机记录：top
记录类型：A
记录值：你的服务器公网 IP
TTL：默认
```

## 2. 服务器环境

建议 Ubuntu / Debian 服务器，已安装 Nginx、Python 3、Git、Node.js、npm。

```bash
sudo apt update
sudo apt install -y nginx git python3 python3-venv python3-pip nodejs npm
sudo npm install -g pm2
```

## 3. 拉取项目

```bash
cd /var/www
git clone https://github.com/lpqq18/ecommerce-dispute-tool.git
cd ecommerce-dispute-tool
```

如果目录已存在：

```bash
cd /var/www/ecommerce-dispute-tool
git pull origin main
```

## 4. 安装 Python 依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 5. 启动服务

先修改 `deploy/ecosystem.config.cjs` 里的：

```text
ADMIN_TOKEN=change-this-admin-token
```

如需真实 AI / OCR，再补充：

```text
AI_PROVIDER=deepseek
DEEPSEEK_API_KEY=你的 DeepSeek Key
DEEPSEEK_MODEL=deepseek-chat
OPENAI_API_KEY=你的 OpenAI Key
OCR_PROVIDER=external
OCR_API_URL=你的 OCR 服务地址
OCR_API_TOKEN=你的 OCR Token
OCR_REQUIRE_REAL=1
OCR_MIN_TEXT_CHARS=20
```

启动：

```bash
pm2 start deploy/ecosystem.config.cjs
pm2 save
pm2 startup
```

检查：

```bash
pm2 status
curl http://127.0.0.1:4173/
```

## 6. Nginx 配置

把 `deploy/ecommerce-dispute-tool.nginx.conf` 的内容加入 `top.tejarvis.info` 的 Nginx server 块中。

示例：

```nginx
server {
    listen 80;
    server_name top.tejarvis.info;

    location = /ecommerce-dispute-tool {
        return 301 /ecommerce-dispute-tool/;
    }

    location ^~ /ecommerce-dispute-tool/ {
        proxy_pass http://127.0.0.1:4173/;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Prefix /ecommerce-dispute-tool;
        proxy_read_timeout 300s;
        client_max_body_size 30m;
    }
}
```

重载：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## 7. HTTPS

如果服务器使用宝塔面板，在网站设置里为 `top.tejarvis.info` 申请 Let's Encrypt 证书。

如果使用命令行：

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d top.tejarvis.info
```

## 8. 验证

```bash
curl -I https://top.tejarvis.info/ecommerce-dispute-tool/
curl https://top.tejarvis.info/ecommerce-dispute-tool/api/runtime
```

浏览器打开：

```text
https://top.tejarvis.info/ecommerce-dispute-tool/
```

后台日志页：

```text
https://top.tejarvis.info/ecommerce-dispute-tool/admin/logs
```

## 9. 后续更新

```bash
cd /var/www/ecommerce-dispute-tool
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
pm2 restart ecommerce-dispute-tool
```
