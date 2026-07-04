from __future__ import annotations

import re
from collections import Counter


CASE_TYPE_KEYWORDS = {
    "恶意差评": ["差评", "评价", "投诉", "曝光", "威胁", "不给", "不处理就", "一星", "差评见"],
    "货不对板": ["货不对板", "不一样", "不符", "规格", "尺码", "颜色", "型号", "sku", "假货", "实物", "详情页"],
    "退款争议": ["退款", "退货", "仅退款", "售后", "平台介入", "拒绝退款", "同意退款", "退回"],
    "物流异常": ["物流异常", "停滞", "丢件", "延误", "派送失败", "拒收", "揽收", "运输中", "无更新", "卡住"],
    "未收到货纠纷": ["没收到", "未收到", "没有收到", "没拿到", "收不到", "没看见包裹", "没收到货"],
}

SELLER_KEYWORDS = ["商家", "卖家", "客服", "已发货", "物流显示", "查询", "催件", "补发", "拒绝", "同意", "提供"]
BUYER_KEYWORDS = ["买家", "用户", "客户", "我没", "我没有", "我要", "退款", "投诉", "差评"]

TIME_PATTERN = re.compile(
    r"(\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?(?:\s+\d{1,2}:\d{2})?|\d{1,2}[-/.月]\d{1,2}日?(?:\s+\d{1,2}:\d{2})?|\d{1,2}:\d{2})"
)


def build_rule_based_result(images: list[dict], ocr_result: dict) -> dict:
    text = collect_text(ocr_result)
    lines = split_lines(text)
    filename_text = " ".join(str(item.get("filename") or "") for item in images + (ocr_result.get("images") or []))
    corpus = f"{filename_text}\n{text}".lower()

    dispute_type = classify_dispute(corpus)
    chat_records = extract_chat_records(lines)
    user_claims = extract_user_claims(lines, dispute_type)
    seller_actions = extract_seller_actions(lines)
    timestamps = extract_timestamps(text)
    order_status = detect_order_status(corpus)
    logistics_status = detect_logistics_status(corpus)
    completeness = evidence_completeness(corpus, dispute_type)
    conflict_checks = build_conflicts(corpus, user_claims, dispute_type, completeness)
    dispute_risk = score_dispute_risk(dispute_type, conflict_checks, completeness)
    appeal_win = score_appeal_win(dispute_type, conflict_checks, completeness)
    judgement = judgement_direction(appeal_win, completeness, conflict_checks)
    gaps = evidence_gaps(completeness, dispute_type)
    evidence_order = evidence_priority(dispute_type)
    summary = dispute_summary(dispute_type, conflict_checks, order_status, logistics_status)
    judgement_reason = judgement_reason_text(judgement, appeal_win, completeness, conflict_checks)

    return {
        "demo_mode": False,
        "rule_based": True,
        "ocr_mode": ocr_result.get("provider") or "unknown",
        "dispute_type": dispute_type,
        "structured_evidence": {
            "order_status": order_status,
            "logistics_status": logistics_status,
            "user_claims": user_claims,
            "seller_actions": seller_actions,
            "timestamps": timestamps,
        },
        "extracted_records": {
            "chat_records": chat_records,
            "ocr_text_preview": text[:3000],
        },
        "timeline": build_timeline(dispute_type, timestamps, order_status, logistics_status, user_claims),
        "risk_score": dispute_risk,
        "dispute_risk_score": dispute_risk,
        "appeal_win_score": appeal_win,
        "score_explanation": score_explanation(dispute_risk, appeal_win, completeness, conflict_checks),
        "risk_reasons": risk_reasons(dispute_type, conflict_checks, completeness),
        "judgement_direction": judgement,
        "judgement_reason": judgement_reason,
        "evidence_completeness": completeness,
        "evidence_weight_rules": evidence_weights(dispute_type, completeness),
        "conflict_checks": conflict_checks,
        "conflict_summary": conflict_summary(conflict_checks),
        "recommendation": recommendation_text(judgement, gaps),
        "malicious_likelihood": malicious_likelihood(dispute_type, conflict_checks),
        "suggested_strategy": suggested_strategy(dispute_type, evidence_order, gaps),
        "evidence_gaps": gaps,
        "dispute_summary": summary,
        "appeal_text": appeal_text(summary, evidence_order, judgement, gaps),
        "evidence_order": evidence_order,
    }


def collect_text(ocr_result: dict) -> str:
    chunks = []
    if ocr_result.get("text"):
        chunks.append(str(ocr_result["text"]))
    for image in ocr_result.get("images") or []:
        if image.get("text"):
            chunks.append(str(image["text"]))
        for block in image.get("blocks") or []:
            if block.get("text"):
                chunks.append(str(block["text"]))
    return "\n".join(chunks).strip()


def split_lines(text: str) -> list[str]:
    lines = [re.sub(r"\s+", " ", item).strip() for item in re.split(r"[\r\n]+", text or "")]
    return [item for item in lines if item]


def classify_dispute(corpus: str) -> str:
    scores = Counter()
    for case_type, keywords in CASE_TYPE_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in corpus:
                scores[case_type] += 1
    if "签收" in corpus and any(item in corpus for item in ["没收到", "未收到", "没有收到"]):
        scores["未收到货纠纷"] += 3
    if scores:
        return scores.most_common(1)[0][0]
    return "无法判断"


def extract_chat_records(lines: list[str]) -> list[dict]:
    records = []
    for line in lines[:80]:
        role = ""
        if any(keyword in line for keyword in SELLER_KEYWORDS):
            role = "seller"
        if any(keyword in line for keyword in BUYER_KEYWORDS):
            role = "buyer" if role != "seller" else role
        if not role:
            continue
        records.append({"role": role, "content": line, "timestamp": first_match(TIME_PATTERN, line)})
    return records[:30]


def extract_user_claims(lines: list[str], dispute_type: str) -> list[str]:
    patterns = {
        "未收到货纠纷": ["没收到", "未收到", "没有收到", "没拿到"],
        "货不对板": ["不一样", "不符", "货不对板", "规格", "颜色", "尺码"],
        "退款争议": ["退款", "退货", "仅退款", "售后"],
        "恶意差评": ["差评", "投诉", "曝光", "不处理就"],
        "物流异常": ["延误", "停滞", "物流异常", "无更新", "丢件"],
    }.get(dispute_type, [])
    claims = []
    for line in lines:
        if any(pattern in line for pattern in patterns) or any(pattern in line for pattern in ["我要退款", "平台介入", "投诉"]):
            claims.append(line)
    return dedupe(claims)[:8] or ["OCR 文本中未明确识别买家主张"]


def extract_seller_actions(lines: list[str]) -> list[str]:
    patterns = ["已发货", "物流显示", "签收", "提供", "查询", "催件", "补发", "拒绝", "同意", "处理"]
    actions = [line for line in lines if any(pattern in line for pattern in patterns)]
    return dedupe(actions)[:8] or ["OCR 文本中未明确识别商家动作"]


def extract_timestamps(text: str) -> list[str]:
    return dedupe(match.group(1) for match in TIME_PATTERN.finditer(text or ""))[:12]


def detect_order_status(corpus: str) -> str:
    if any(item in corpus for item in ["已完成", "交易成功"]):
        return "订单状态：已完成/交易成功"
    if any(item in corpus for item in ["已付款", "付款成功", "买家已付款"]):
        return "订单状态：已付款"
    if any(item in corpus for item in ["已发货", "卖家已发货", "发货"]):
        return "订单状态：已发货"
    return "订单状态：OCR 文本中未明确识别"


def detect_logistics_status(corpus: str) -> str:
    if has_signed_delivery(corpus):
        return "物流状态：已签收/已送达"
    if any(item in corpus for item in ["暂未签收", "未签收", "未送达"]):
        return "物流状态：暂未签收"
    if any(item in corpus for item in ["派送", "派件"]):
        return "物流状态：派送中"
    if any(item in corpus for item in ["运输中", "揽收", "已揽件", "在途"]):
        return "物流状态：运输中"
    if any(item in corpus for item in ["异常", "停滞", "丢件", "延误"]):
        return "物流状态：存在异常/延误"
    return "物流状态：OCR 文本中未明确识别"


def evidence_completeness(corpus: str, dispute_type: str) -> dict:
    order = any(item in corpus for item in ["订单", "订单号", "交易", "付款", "已发货", "已完成"])
    logistics = any(item in corpus for item in ["物流", "快递", "运单", "单号", "签收", "派送", "揽收", "运输"])
    chat = any(item in corpus for item in ["买家", "卖家", "客服", "商家", "退款", "没收到", "差评", "投诉"])
    product = any(item in corpus for item in ["商品", "规格", "sku", "颜色", "尺码", "详情页", "实物"])
    refund = any(item in corpus for item in ["退款", "退货", "售后", "平台介入", "仅退款"])
    flags = [order, logistics, chat, product if dispute_type == "货不对板" else True, refund if dispute_type == "退款争议" else True]
    score = int(sum(1 for item in flags if item) / len(flags) * 100)
    missing = []
    if not order:
        missing.append("缺少订单号、付款状态或订单详情证据")
    if dispute_type in ("未收到货纠纷", "物流异常") and not logistics:
        missing.append("缺少物流轨迹、运单号或签收状态证据")
    if not chat:
        missing.append("缺少聊天记录或买家主张证据")
    if dispute_type == "货不对板" and not product:
        missing.append("缺少商品规格、详情页或实物对比证据")
    if dispute_type == "退款争议" and not refund:
        missing.append("缺少退款/退货/售后流程证据")
    return {
        "overall_score": score,
        "order_evidence": order,
        "logistics_evidence": logistics,
        "chat_evidence": chat,
        "product_spec_evidence": product,
        "refund_process_evidence": refund,
        "missing_items": missing,
        "summary": "证据完整度较高。" if score >= 75 else "证据仍存在关键缺口，需补充后再提交申诉。",
    }


def build_conflicts(corpus: str, claims: list[str], dispute_type: str, completeness: dict) -> list[dict]:
    conflicts = []
    not_received = any(item in corpus for item in ["没收到", "未收到", "没有收到", "没拿到"])
    signed = has_signed_delivery(corpus)
    if not_received and signed:
        conflicts.append(
            {
                "claim": "买家声称未收到货",
                "objective_evidence": "OCR 文本识别到物流已签收/签收相关信息",
                "conflict_level": "high",
                "conclusion": "买家主张与物流签收状态存在明显冲突，应优先提交物流签收证明。",
            }
        )
    if dispute_type == "退款争议" and any(item in corpus for item in ["仅退款", "退款"]) and signed:
        conflicts.append(
            {
                "claim": "买家申请退款/仅退款",
                "objective_evidence": "OCR 文本识别到签收或履约信息",
                "conflict_level": "medium",
                "conclusion": "需要进一步核对退货物流与售后节点，避免仅凭签收直接判断。",
            }
        )
    if dispute_type == "退款争议" and any(item in corpus for item in ["超时未处理", "同意退款", "商家超时"]):
        conflicts.append(
            {
                "claim": "买家申请退款或平台售后",
                "objective_evidence": "OCR 文本识别到商家超时未处理或已同意退款",
                "conflict_level": "none",
                "conclusion": "当前售后节点更支持买家退款方向，商家申诉胜率应保持保守。",
            }
        )
    if dispute_type == "恶意差评" and any(item in corpus for item in ["不处理就", "不给就", "差评", "曝光"]):
        conflicts.append(
            {
                "claim": "买家以差评、投诉或曝光施压",
                "objective_evidence": "OCR 文本识别到差评/投诉威胁相关表达",
                "conflict_level": "high",
                "conclusion": "存在疑似恶意差评风险，应保留完整聊天上下文和售后处理记录。",
            }
        )
    if dispute_type == "货不对板" and any(item in corpus for item in ["不一样", "不符", "货不对板"]) and any(
        item in corpus for item in ["sku 与买家选择一致", "sku与买家选择一致", "规格与实物照片一致", "详情页规格与实物照片一致", "一致"]
    ):
        conflicts.append(
            {
                "claim": "买家主张货不对板或商品规格不符",
                "objective_evidence": "OCR 文本识别到 SKU、详情页规格或实物对比一致",
                "conflict_level": "medium",
                "conclusion": "买家主张与商家规格/SKU 一致性证据存在冲突，可作为申诉依据。",
            }
        )
    if not conflicts:
        conflicts.append(
            {
                "claim": claims[0] if claims else "OCR 文本中未明确识别买家主张",
                "objective_evidence": "当前 OCR 文本未发现足够强的客观冲突凭证",
                "conflict_level": "low" if completeness.get("overall_score", 0) >= 70 else "medium",
                "conclusion": "暂未发现高强度矛盾，建议补充关键截图后再判断。",
            }
        )
    return conflicts


def score_dispute_risk(dispute_type: str, conflicts: list[dict], completeness: dict) -> int:
    base = 35 if dispute_type == "无法判断" else 50
    if any(item["conflict_level"] == "high" for item in conflicts):
        base += 28
    elif any(item["conflict_level"] == "medium" for item in conflicts):
        base += 14
    if completeness.get("overall_score", 0) < 60:
        base += 8
    return clamp(base)


def score_appeal_win(dispute_type: str, conflicts: list[dict], completeness: dict) -> int:
    score = int(completeness.get("overall_score", 0) * 0.55) + 20
    if any("超时未处理" in item.get("objective_evidence", "") or "已同意退款" in item.get("objective_evidence", "") for item in conflicts):
        score -= 35
    if any(item["conflict_level"] == "high" for item in conflicts):
        score += 18
    elif any(item["conflict_level"] == "medium" for item in conflicts):
        score += 8
    if dispute_type == "无法判断":
        score -= 25
    return clamp(score)


def judgement_direction(appeal_win: int, completeness: dict, conflicts: list[dict]) -> str:
    if any("更支持买家退款方向" in item.get("conclusion", "") for item in conflicts):
        return "support_buyer"
    if completeness.get("overall_score", 0) < 45:
        return "insufficient_evidence"
    if appeal_win >= 68 and any(item["conflict_level"] in ("high", "medium") for item in conflicts):
        return "support_seller"
    if appeal_win < 45:
        return "support_buyer"
    return "insufficient_evidence"


def evidence_gaps(completeness: dict, dispute_type: str) -> list[str]:
    gaps = list(completeness.get("missing_items") or [])
    if dispute_type == "无法判断":
        gaps.append("OCR 文本不足以判断纠纷类型，建议补充聊天、订单、物流或售后截图")
    return dedupe(gaps)


def evidence_priority(dispute_type: str) -> list[str]:
    return {
        "未收到货纠纷": ["物流签收证明", "订单发货记录", "买家聊天记录", "平台售后/投诉页面"],
        "货不对板": ["商品详情页/规格参数", "实物照片或对比图", "SKU/发货记录", "聊天记录"],
        "退款争议": ["退款/售后节点", "退货物流", "订单签收/拒收状态", "聊天记录"],
        "恶意差评": ["聊天威胁语句", "评价截图", "售后处理记录", "订单/物流履约证明"],
        "物流异常": ["物流异常节点", "停滞时间", "快递官方轨迹", "商家催查记录"],
    }.get(dispute_type, ["聊天记录", "订单详情", "物流凭证", "售后页面"])


def build_timeline(dispute_type: str, timestamps: list[str], order_status: str, logistics_status: str, claims: list[str]) -> list[dict]:
    timeline = []
    if timestamps:
        for index, item in enumerate(timestamps[:6]):
            timeline.append({"time": item, "event": f"OCR 识别到时间节点 {index + 1}", "evidence": "OCR 原始文本"})
    timeline.extend(
        [
            {"time": "待核实", "event": order_status, "evidence": "订单/交易截图 OCR"},
            {"time": "待核实", "event": logistics_status, "evidence": "物流截图 OCR"},
            {"time": "待核实", "event": f"识别纠纷类型：{dispute_type}", "evidence": claims[0] if claims else "OCR 文本"},
        ]
    )
    return timeline[:8]


def evidence_weights(dispute_type: str, completeness: dict) -> list[dict]:
    priorities = evidence_priority(dispute_type)
    present_map = {
        "物流": completeness.get("logistics_evidence"),
        "订单": completeness.get("order_evidence"),
        "聊天": completeness.get("chat_evidence"),
        "商品": completeness.get("product_spec_evidence"),
        "规格": completeness.get("product_spec_evidence"),
        "退款": completeness.get("refund_process_evidence"),
        "售后": completeness.get("refund_process_evidence"),
    }
    weights = [95, 84, 72, 60]
    result = []
    for index, name in enumerate(priorities):
        present = any(value for key, value in present_map.items() if key in name)
        result.append({"evidence_type": name, "weight": weights[min(index, len(weights) - 1)], "reason": "按当前纠纷类型的证据优先级排序。", "present": bool(present)})
    return result


def dispute_summary(dispute_type: str, conflicts: list[dict], order_status: str, logistics_status: str) -> str:
    return f"系统基于 OCR 文本初步识别为「{dispute_type}」。{order_status}；{logistics_status}。{conflict_summary(conflicts)}"


def score_explanation(risk: int, appeal: int, completeness: dict, conflicts: list[dict]) -> str:
    return f"纠纷风险分 {risk}，申诉胜率分 {appeal}。证据完整度 {completeness.get('overall_score', 0)}。{conflict_summary(conflicts)}"


def risk_reasons(dispute_type: str, conflicts: list[dict], completeness: dict) -> list[str]:
    reasons = [item["conclusion"] for item in conflicts]
    if completeness.get("missing_items"):
        reasons.append("证据存在缺口：" + "；".join(completeness["missing_items"][:3]))
    if dispute_type == "无法判断":
        reasons.append("OCR 文本无法稳定归类，当前判断应保持保守。")
    return dedupe(reasons)


def conflict_summary(conflicts: list[dict]) -> str:
    levels = Counter(item.get("conflict_level", "none") for item in conflicts)
    if levels.get("high"):
        return f"识别到 {levels['high']} 条高强度冲突。"
    if levels.get("medium"):
        return f"识别到 {levels['medium']} 条中等冲突。"
    return "暂未发现高强度冲突。"


def judgement_reason_text(judgement: str, appeal_win: int, completeness: dict, conflicts: list[dict]) -> str:
    if judgement == "support_seller":
        return f"当前证据较支持商家申诉，申诉胜率 {appeal_win}，且存在可用于申诉的客观矛盾。"
    if judgement == "support_buyer":
        return f"当前证据不足以支持商家，申诉胜率 {appeal_win}，建议优先补充证据。"
    return f"当前证据完整度 {completeness.get('overall_score', 0)}，暂不足以形成稳定结论。"


def recommendation_text(judgement: str, gaps: list[str]) -> str:
    if judgement == "support_seller":
        return "建议发起平台申诉，并按证据权重顺序提交材料。"
    if gaps:
        return "建议先补充关键证据后再申诉：" + "；".join(gaps[:3])
    return "建议人工复核 OCR 文本与截图原件后再提交。"


def malicious_likelihood(dispute_type: str, conflicts: list[dict]) -> str:
    if dispute_type == "恶意差评" or any(item["conflict_level"] == "high" for item in conflicts):
        return "中高风险：存在疑似恶意或强冲突特征。"
    return "低到中风险：暂未发现强恶意特征。"


def suggested_strategy(dispute_type: str, evidence_order: list[str], gaps: list[str]) -> str:
    strategy = "建议提交顺序：" + "、".join(evidence_order[:4]) + "。"
    if gaps:
        strategy += " 同时补充：" + "；".join(gaps[:3]) + "。"
    return strategy


def appeal_text(summary: str, evidence_order: list[str], judgement: str, gaps: list[str]) -> str:
    lines = ["尊敬的平台：", "", summary, "", "具体证据如下："]
    lines.extend(f"{index}. {item}" for index, item in enumerate(evidence_order, start=1))
    lines.append("")
    if judgement == "support_seller":
        lines.append("基于上述证据，请平台核实买家主张与客观凭证之间的不一致，并保护商家正常履约权益。")
    else:
        lines.append("当前材料仍存在证据缺口，建议补充后再提交正式申诉。")
    if gaps:
        lines.append("待补充证据：" + "；".join(gaps[:3]))
    return "\n".join(lines)


def first_match(pattern, text: str) -> str:
    match = pattern.search(text or "")
    return match.group(1) if match else ""


def dedupe(values) -> list[str]:
    seen = set()
    result = []
    for value in values:
        item = str(value).strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def clamp(value: int) -> int:
    return max(0, min(100, int(value)))


def has_signed_delivery(corpus: str) -> bool:
    if any(item in corpus for item in ["暂未签收", "未签收", "没有签收", "未送达", "尚未签收"]):
        return False
    return any(item in corpus for item in ["已签收", "签收成功", "本人签收", "门卫签收", "已送达"])
