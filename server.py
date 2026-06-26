from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
import base64
from email.parser import BytesParser
from email.policy import default as email_policy
import json
import os
import re

try:
    import requests
except ImportError:
    requests = None


HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "4173"))
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
MAX_IMAGES = 5
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


CASE_TYPES = ["未收到货纠纷", "货不对板", "退款争议", "恶意差评", "物流异常", "无法判断"]
JUDGEMENTS = ["support_buyer", "support_seller", "insufficient_evidence"]


def json_dumps(value):
    return json.dumps(value, ensure_ascii=False)


def response_schema():
    item_text = {"type": "string"}
    weighted_evidence_item = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "evidence_type": {"type": "string"},
            "weight": {"type": "integer", "minimum": 0, "maximum": 100},
            "reason": {"type": "string"},
            "present": {"type": "boolean"},
        },
        "required": ["evidence_type", "weight", "reason", "present"],
    }
    conflict_item = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "claim": {"type": "string"},
            "objective_evidence": {"type": "string"},
            "conflict_level": {"type": "string", "enum": ["none", "low", "medium", "high"]},
            "conclusion": {"type": "string"},
        },
        "required": ["claim", "objective_evidence", "conflict_level", "conclusion"],
    }
    timeline_item = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "time": {"type": "string"},
            "event": {"type": "string"},
            "evidence": {"type": "string"},
        },
        "required": ["time", "event", "evidence"],
    }
    structured = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "order_status": {"type": "string"},
            "logistics_status": {"type": "string"},
            "user_claims": {"type": "array", "items": item_text},
            "seller_actions": {"type": "array", "items": item_text},
            "timestamps": {"type": "array", "items": item_text},
        },
        "required": ["order_status", "logistics_status", "user_claims", "seller_actions", "timestamps"],
    }
    completeness = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "overall_score": {"type": "integer", "minimum": 0, "maximum": 100},
            "order_evidence": {"type": "boolean"},
            "logistics_evidence": {"type": "boolean"},
            "chat_evidence": {"type": "boolean"},
            "product_spec_evidence": {"type": "boolean"},
            "refund_process_evidence": {"type": "boolean"},
            "missing_items": {"type": "array", "items": item_text},
            "summary": {"type": "string"},
        },
        "required": [
            "overall_score",
            "order_evidence",
            "logistics_evidence",
            "chat_evidence",
            "product_spec_evidence",
            "refund_process_evidence",
            "missing_items",
            "summary",
        ],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "dispute_type": {"type": "string", "enum": CASE_TYPES},
            "structured_evidence": structured,
            "timeline": {"type": "array", "items": timeline_item},
            "risk_score": {"type": "integer", "minimum": 0, "maximum": 100},
            "dispute_risk_score": {"type": "integer", "minimum": 0, "maximum": 100},
            "appeal_win_score": {"type": "integer", "minimum": 0, "maximum": 100},
            "score_explanation": {"type": "string"},
            "risk_reasons": {"type": "array", "items": item_text},
            "judgement_direction": {"type": "string", "enum": JUDGEMENTS},
            "judgement_reason": {"type": "string"},
            "evidence_completeness": completeness,
            "evidence_weight_rules": {"type": "array", "items": weighted_evidence_item},
            "conflict_checks": {"type": "array", "items": conflict_item},
            "conflict_summary": {"type": "string"},
            "recommendation": {"type": "string"},
            "malicious_likelihood": {"type": "string"},
            "suggested_strategy": {"type": "string"},
            "evidence_gaps": {"type": "array", "items": item_text},
            "dispute_summary": {"type": "string"},
            "appeal_text": {"type": "string"},
            "evidence_order": {"type": "array", "items": item_text},
        },
        "required": [
            "dispute_type",
            "structured_evidence",
            "timeline",
            "risk_score",
            "dispute_risk_score",
            "appeal_win_score",
            "score_explanation",
            "risk_reasons",
            "judgement_direction",
            "judgement_reason",
            "evidence_completeness",
            "evidence_weight_rules",
            "conflict_checks",
            "conflict_summary",
            "recommendation",
            "malicious_likelihood",
            "suggested_strategy",
            "evidence_gaps",
            "dispute_summary",
            "appeal_text",
            "evidence_order",
        ],
    }


def build_prompt():
    return """
你是电商纠纷证据推理分析员，不是客服机器人。
请从用户上传的聊天截图、订单截图、物流截图、商品规格截图、售后截图中提取证据，并生成平台申诉材料。

纠纷类型只能从以下 5 类中选择：
1. 未收到货纠纷
2. 货不对板
3. 退款争议
4. 恶意差评
5. 物流异常
无法判断时填“无法判断”。

请完成：
1. OCR 并提取聊天内容、时间信息、订单状态、物流状态、用户主张、商家动作。
2. 重建时间线，尽量包括下单、发货、签收、投诉、退款申请、差评、退货物流、异常物流节点。
3. 输出两个评分：
   - dispute_risk_score：纠纷风险分，0-100，分数越高表示争议或恶意风险越高。
   - appeal_win_score：申诉胜率分，0-100，分数越高表示当前证据越支持商家申诉。
   - risk_score 为兼容旧版字段，可等于 dispute_risk_score。
4. 输出判决方向：
   - support_buyer：证据更支持买家
   - support_seller：证据更支持商家
   - insufficient_evidence：关键证据不足，暂不能判断
5. 输出证据完整度，分别判断订单证据、物流证据、聊天证据、商品规格证据、退款流程证据是否存在，并给出完整度分数。
6. 输出证据权重规则命中情况：每条证据类型给出 weight、present、reason。
7. 输出冲突检测：对“用户主张”和“客观凭证”逐条比对，给出 none/low/medium/high 冲突等级。
8. 生成正式、简洁、可直接复制的平台申诉文本。

证据优先级规则：
- 未收到货纠纷：优先物流签收证明、订单发货记录、聊天记录。
- 货不对板：优先商品详情页/规格参数、实物照片、SKU/发货记录、聊天记录。
- 退款争议：优先退款节点、退货物流、签收/拒收状态、平台售后页。
- 恶意差评：优先聊天威胁语句、评价截图、售后处理记录。
- 物流异常：优先物流异常节点、停滞时间、快递官方轨迹、商家催查记录。

重要要求：
- 不要编造截图中不存在的订单号、姓名、物流单号。
- 如证据缺失，请在 evidence_gaps 和 evidence_completeness.missing_items 中说明。
- 冲突检测必须明确说明：用户主张是什么、客观凭证是什么、二者是否冲突。
- 风险高不等于申诉胜率高。若买家恶意风险高且商家证据完整，dispute_risk_score 和 appeal_win_score 可以同时较高。
- appeal_text 使用中文，语气正式，适合淘宝/拼多多/抖音小商家提交平台。
- 只返回符合 schema 的 JSON。
""".strip()


def demo_result(images):
    file_count = len(images)
    file_names = [item.get("filename") or f"截图 {index + 1}" for index, item in enumerate(images)]
    return {
        "demo_mode": True,
        "dispute_type": "未收到货纠纷",
        "structured_evidence": {
            "order_status": "演示数据：订单已付款并已发货，等待接入真实视觉模型后自动识别截图内容。",
            "logistics_status": "演示数据：物流显示疑似已签收，但当前未做真实 OCR。",
            "user_claims": ["买家声称未收到货", "要求退款或平台介入"],
            "seller_actions": ["商家已上传聊天、订单或物流截图", f"本次共接收 {file_count} 张证据图片"],
            "timestamps": ["时间待补：真实模式下将从截图中提取聊天时间、发货时间、签收时间"],
        },
        "timeline": [
            {"time": "时间待补", "event": "用户上传证据组件", "evidence": "、".join(file_names[:3])},
            {"time": "时间待补", "event": "系统识别纠纷类型为未收到货方向", "evidence": "演示模式下用于验证页面流程与信息架构。"},
            {"time": "时间待补", "event": "生成风险评分、判决方向与申诉材料", "evidence": "接入 OPENAI_API_KEY 后，此处会替换为真实图片识别结论。"},
        ],
        "risk_score": 72,
        "dispute_risk_score": 72,
        "appeal_win_score": 81,
        "score_explanation": "演示模式：纠纷风险较高，因为买家主张与物流状态可能冲突；申诉胜率较高，因为假设商家已具备物流签收与订单发货证据。",
        "risk_reasons": [
            "演示推演：买家主张与物流签收状态可能存在冲突。",
            "演示推演：当前证据链包含多张截图，但未验证是否覆盖订单号、签收时间与聊天上下文。",
            "演示推演：如平台要求官方物流凭证，应优先补充签收页或物流详情页。",
        ],
        "judgement_direction": "support_seller",
        "judgement_reason": "演示模式下假设物流签收证据强于买家单方陈述，因此暂建议支持商家；真实模式会按截图内容重新判断。",
        "evidence_completeness": {
            "overall_score": 68,
            "order_evidence": True,
            "logistics_evidence": True,
            "chat_evidence": True,
            "product_spec_evidence": False,
            "refund_process_evidence": False,
            "missing_items": ["真实 OCR 未启用，无法确认订单号和签收时间", "未提供平台售后节点截图"],
            "summary": "演示模式：基础证据链可跑通，但真实申诉仍需要确认订单、物流与聊天内容是否同一订单。",
        },
        "evidence_weight_rules": [
            {"evidence_type": "物流签收证明", "weight": 95, "reason": "未收到货纠纷中，物流签收是最强客观凭证。", "present": True},
            {"evidence_type": "订单发货记录", "weight": 82, "reason": "证明商家已按订单履约发货。", "present": True},
            {"evidence_type": "买家聊天记录", "weight": 68, "reason": "用于确认买家主张和投诉时间。", "present": True},
            {"evidence_type": "平台售后节点", "weight": 54, "reason": "用于确认退款或投诉是否超时、重复。", "present": False},
        ],
        "conflict_checks": [
            {
                "claim": "买家声称未收到货",
                "objective_evidence": "演示数据假设物流存在已签收记录",
                "conflict_level": "high",
                "conclusion": "买家主张与物流签收状态存在高强度冲突，应优先提交物流签收凭证。",
            },
            {
                "claim": "买家要求退款或平台介入",
                "objective_evidence": "当前未识别到平台售后节点截图",
                "conflict_level": "medium",
                "conclusion": "退款节点证据不足，建议补充售后详情页。",
            },
        ],
        "conflict_summary": "演示模式下识别到 1 条高冲突：未收到货主张与物流签收状态冲突。",
        "recommendation": "建议先按演示结果检查页面流程、复制动作和结果结构；接入真实 API 后再验证识别准确率。",
        "malicious_likelihood": "演示模式：中高风险，仅用于流程测试。",
        "suggested_strategy": "优先提交物流签收证明和订单发货记录，再提交聊天记录作为用户主张的辅助证据。",
        "evidence_gaps": ["真实 OCR 尚未启用，不能确认截图里的订单号、时间和物流状态。", "建议后续增加证据类型手动标注，以提升真实分析稳定性。"],
        "dispute_summary": "【演示模式】本订单疑似存在“物流已签收但用户声称未收到”的纠纷场景。当前结果用于验证产品流程，不代表真实申诉结论。",
        "appeal_text": """尊敬的平台：

商家就该订单提交纠纷申诉材料如下。

根据现有证据，本订单已完成发货流程，且用户反馈与物流状态之间可能存在不一致。为便于平台核实，商家已整理并提交以下材料：
1. 订单/发货记录截图
2. 物流轨迹或签收证明截图
3. 买家聊天记录截图

请平台结合订单状态、物流记录及聊天内容进行核实。如物流信息确认已签收，恳请平台驳回不合理退款或投诉请求，并保护商家正常权益。

说明：当前为演示模式文本，接入真实识别后将根据截图内容自动生成更精确的申诉材料。""",
        "evidence_order": ["物流签收证明或物流详情截图", "订单发货记录/订单详情截图", "买家聊天记录截图", "退款/投诉页面截图"],
    }


def extract_output_text(payload):
    if payload.get("output_text"):
        return payload["output_text"]
    chunks = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in ("output_text", "text"):
                chunks.append(content.get("text", ""))
    return "".join(chunks)


def extract_json(text):
    if not text:
        raise ValueError("AI 没有返回可解析内容")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def clamp_score(value, fallback=0):
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return fallback


def normalize_result_scores(result):
    completeness = result.get("evidence_completeness") or {}
    missing_items = completeness.get("missing_items") or []
    missing_text = " ".join(str(item) for item in missing_items)
    present_flags = {
        "订单证据": bool(completeness.get("order_evidence")),
        "物流证据": bool(completeness.get("logistics_evidence")),
        "聊天证据": bool(completeness.get("chat_evidence")),
        "商品规格证据": bool(completeness.get("product_spec_evidence")),
        "退款流程证据": bool(completeness.get("refund_process_evidence")),
    }
    completeness_score = clamp_score(completeness.get("overall_score"), 0)
    dispute_type = result.get("dispute_type") or "无法判断"
    dispute_risk = clamp_score(result.get("dispute_risk_score", result.get("risk_score")), 0)
    appeal_win = clamp_score(result.get("appeal_win_score"), 0)

    caps = [100]
    cap_reasons = []

    def missing_any(*keywords):
        return any(keyword in missing_text for keyword in keywords)

    if completeness_score < 45:
        caps.append(45)
        cap_reasons.append("证据完整度低于45%，申诉胜率封顶45分")
    elif completeness_score < 65:
        caps.append(65)
        cap_reasons.append("证据完整度低于65%，申诉胜率封顶65分")
    elif completeness_score < 75 and missing_items:
        caps.append(72)
        cap_reasons.append("证据完整度低于75%且存在缺失字段，申诉胜率封顶72分")

    if not present_flags["订单证据"]:
        caps.append(60)
        cap_reasons.append("缺少订单证据")
    if dispute_type == "物流异常" and missing_any("订单号", "订单编号", "order_id"):
        caps.append(48)
        cap_reasons.append("物流异常案件缺少订单号")
    elif missing_any("订单号", "订单编号", "付款时间", "下单时间", "order_id", "order_time"):
        caps.append(60)
        cap_reasons.append("订单关键字段缺失")
    if dispute_type in ("未收到货纠纷", "物流异常") and not present_flags["物流证据"]:
        caps.append(55)
        cap_reasons.append("该类型缺少物流证据")
    if dispute_type == "物流异常" and missing_any("物流", "运单", "单号", "签收", "揽收", "派送", "tracking", "logistics", "signature"):
        caps.append(48)
        cap_reasons.append("物流异常案件缺少物流关键字段")
    elif dispute_type == "未收到货纠纷" and missing_any("物流", "运单", "单号", "签收", "揽收", "派送", "tracking", "logistics", "signature"):
        caps.append(55)
        cap_reasons.append("物流关键字段缺失")
    if dispute_type == "物流异常" and missing_any("停滞时间", "停滞", "stagnation"):
        caps.append(40)
        cap_reasons.append("物流停滞时间字段缺失")
    elif dispute_type == "物流异常" and missing_any("时间戳", "聊天时间", "签收时间", "投诉时间", "节点时间", "时间", "timestamp"):
        caps.append(48)
        cap_reasons.append("物流异常关键时间字段缺失")
    elif missing_any("时间戳", "聊天时间", "签收时间", "投诉时间", "停滞时间", "节点时间", "时间", "timestamp", "stagnation"):
        caps.append(68)
        cap_reasons.append("关键时间字段缺失")
    if dispute_type == "货不对板" and not present_flags["商品规格证据"]:
        caps.append(55)
        cap_reasons.append("货不对板缺少商品规格/实物证据")
    if dispute_type == "货不对板" and missing_any("规格", "SKU", "商品", "实物", "对比", "sku", "spec", "product", "photo", "comparison"):
        caps.append(55)
        cap_reasons.append("货不对板关键对比字段缺失")
    if dispute_type == "退款争议" and not present_flags["退款流程证据"]:
        caps.append(60)
        cap_reasons.append("退款争议缺少退款流程证据")
    if dispute_type == "退款争议" and missing_any("退款", "退货", "售后", "平台介入", "审核", "refund", "return"):
        caps.append(60)
        cap_reasons.append("退款流程关键字段缺失")
    if dispute_type == "恶意差评" and not present_flags["聊天证据"]:
        caps.append(55)
        cap_reasons.append("恶意差评缺少聊天威胁证据")
    if dispute_type == "恶意差评" and missing_any("聊天", "威胁", "差评", "评价", "threat", "review", "chat"):
        caps.append(55)
        cap_reasons.append("差评威胁关键字段缺失")
    if missing_any("用户主张", "买家主张", "投诉内容", "聊天主张", "chat_claim"):
        caps.append(65)
        cap_reasons.append("买家主张或投诉内容字段缺失")

    cap = min(caps)
    adjusted_appeal = min(appeal_win, cap)
    result["risk_score"] = dispute_risk
    result["dispute_risk_score"] = dispute_risk
    result["appeal_win_score"] = adjusted_appeal

    if adjusted_appeal < appeal_win:
        note = "评分护栏：因" + "、".join(cap_reasons[:3]) + f"，申诉胜率由 {appeal_win} 下调至 {adjusted_appeal}。"
        result["score_explanation"] = (result.get("score_explanation") or "").strip()
        result["score_explanation"] = (result["score_explanation"] + "\n" + note).strip()
        gaps = result.setdefault("evidence_gaps", [])
        if missing_items:
            for item in missing_items:
                if item not in gaps:
                    gaps.append(item)
    return result


def analyze_images(images):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return normalize_result_scores(demo_result(images))
    if requests is None:
        raise RuntimeError("当前 Python 环境缺少 requests，无法调用 OpenAI API。")

    content = [{"type": "input_text", "text": build_prompt()}]
    for image in images:
        data_url = f"data:{image['mime']};base64,{base64.b64encode(image['bytes']).decode('ascii')}"
        content.append({"type": "input_image", "image_url": data_url})

    body = {
        "model": OPENAI_MODEL,
        "input": [{"role": "user", "content": content}],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "dispute_evidence_pack",
                "schema": response_schema(),
                "strict": True,
            }
        },
    }
    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=body,
        timeout=90,
    )
    if response.status_code >= 400:
        try:
            detail = response.json()
        except Exception:
            detail = response.text
        raise RuntimeError(f"OpenAI 分析失败：{detail}")
    return normalize_result_scores(extract_json(extract_output_text(response.json())))


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".js": "application/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".html": "text/html; charset=utf-8",
    }

    def send_json(self, status, payload):
        body = json_dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_images(self):
        content_length = int(self.headers.get("Content-Length", 0) or 0)
        if content_length <= 0:
            raise ValueError("请至少上传 1 张截图。")
        if content_length > MAX_UPLOAD_BYTES:
            raise ValueError("图片总大小不能超过 25MB。")

        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            raise ValueError("请使用表单方式上传图片。")

        body = self.rfile.read(content_length)
        raw_message = (f"Content-Type: {content_type}\r\n" f"MIME-Version: 1.0\r\n\r\n").encode("utf-8") + body
        message = BytesParser(policy=email_policy).parsebytes(raw_message)
        images = []
        for part in message.iter_parts():
            if part.get_param("name", header="content-disposition") != "images":
                continue
            mime = part.get_content_type()
            if mime not in ("image/png", "image/jpeg", "image/webp"):
                raise ValueError("仅支持 PNG、JPG、WebP 图片。")
            content = part.get_payload(decode=True) or b""
            if content:
                images.append({"mime": mime, "bytes": content, "filename": part.get_filename()})

        if not images:
            raise ValueError("请至少上传 1 张截图。")
        if len(images) > MAX_IMAGES:
            raise ValueError("最多上传 5 张截图。")
        return images

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/api/analyze":
            self.send_json(404, {"error": "接口不存在"})
            return
        try:
            images = self.read_images()
            result = analyze_images(images)
            self.send_json(200, result)
        except Exception as exc:
            self.send_json(400, {"error": str(exc)})


if __name__ == "__main__":
    print(f"电商纠纷证据包助手已启动：http://{HOST}:{PORT}")
    if not os.getenv("OPENAI_API_KEY"):
        print("当前未配置 OPENAI_API_KEY，将使用本地演示模式。")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
