"""查询层脱敏：账户与证件字段默认打码。"""

from __future__ import annotations

from typing import Any

SENSITIVE_KEYS = {
    "收款方",
    "户名",
    "身份证",
    "身份证号",
    "账号",
    "银行卡账号",
    "银行账号",
    "联系方式",
    "电话",
}

RECORD_SAMPLE_FIELDS = [
    "id",
    "主题",
    "媒体",
    "row_number",
    "platform",
    "primary_platform",
    "标题",
    "发布日期",
    "文章类型",
    "发布形式",
    "媒体等级",
    "粉丝量",
    "media_match_status",
    "account_match_status",
    "processable",
    "费用",
    "url",
    "primary_link",
    "身份证",
    "账号",
    "收款方",
    "联系方式",
]


def mask_value(value: Any) -> str:
    if value is None or value == "":
        return ""
    text = str(value)
    if len(text) <= 2:
        return "*" * len(text)
    return text[0] + "*" * (len(text) - 2) + text[-1]


def redact_mapping(data: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in data.items():
        if key in SENSITIVE_KEYS:
            redacted[key] = mask_value(value)
        elif isinstance(value, dict):
            redacted[key] = redact_mapping(value)
        elif isinstance(value, list):
            redacted[key] = [
                redact_mapping(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            redacted[key] = value
    return redacted


def project_record(record: dict[str, Any], fields: list[str] | None = None) -> dict[str, Any]:
    wanted = fields or RECORD_SAMPLE_FIELDS
    projected: dict[str, Any] = {}
    for key in wanted:
        if key in record:
            projected[key] = record[key]
    if "id" not in projected and record.get("id"):
        projected["id"] = record["id"]
    return redact_mapping(projected)
