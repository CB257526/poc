"""工作流静态说明书：节点顺序、读写字段、典型错误码。"""

from __future__ import annotations

from typing import Any

WORKFLOW_NODES: list[dict[str, Any]] = [
    {
        "node_id": "node_00",
        "name": "输入验证",
        "reads": ["input_file", "table_dir", "config.media_name_corrections"],
        "writes": ["records"],
        "error_codes": [
            "INPUT_FILE_NOT_FOUND",
            "REFERENCE_TABLE_NOT_FOUND",
            "EMPTY_INPUT_FILE",
            "READ_INPUT_FILE_FAILED",
            "MEDIA_TABLE_LOAD_FAILED",
            "MISSING_REQUIRED_FIELD",
            "MEDIA_NOT_IN_LIBRARY",
            "DUPLICATE_LINKS_MERGED",
        ],
    },
    {
        "node_id": "node_01",
        "name": "填写约稿资料基础信息",
        "reads": ["records.链接"],
        "writes": ["records.url", "records.platform", "records.primary_link", "records.sync_links"],
        "error_codes": ["NO_URL_FOUND", "UNKNOWN_PLATFORM"],
    },
    {
        "node_id": "node_02",
        "name": "完善发布信息",
        "reads": ["records.primary_link", "records.url"],
        "writes": ["records.标题", "records.发布日期", "records.文章类型", "records.发布形式"],
        "error_codes": ["SCRAPE_FAILED", "MISSING_TITLE", "SCRAPING_FAILED"],
    },
    {
        "node_id": "node_03",
        "name": "匹配媒体库",
        "reads": ["records.媒体", "3-媒体库"],
        "writes": ["records.媒体等级", "records.粉丝量", "records.media_match_status", "records.processable"],
        "error_codes": [
            "TABLE_LOAD_FAILED",
            "MISSING_MEDIA_NAME",
            "DUPLICATE_MEDIA_NAME",
            "MISSING_MEDIA_LEVEL",
            "MISSING_FAN_COUNT",
            "MEDIA_NOT_FOUND",
        ],
    },
    {
        "node_id": "node_04",
        "name": "匹配账户信息",
        "reads": ["records.媒体", "records.processable", "4-账户信息"],
        "writes": [
            "records.收款方",
            "records.开户行",
            "records.账号",
            "records.联系方式",
            "records.身份证",
            "records.account_match_status",
            "records.processable",
        ],
        "error_codes": [
            "TABLE_LOAD_FAILED",
            "MISSING_MEDIA_NAME",
            "DUPLICATE_ACCOUNT_MEDIA",
            "MISSING_ACCOUNT_FIELDS",
            "ACCOUNT_NOT_FOUND",
        ],
    },
    {
        "node_id": "node_05",
        "name": "计算费用",
        "reads": ["records.processable", "records.媒体等级", "records.文章类型", "5-费用"],
        "writes": ["quote_details"],
        "error_codes": ["TABLE_LOAD_FAILED", "MISSING_MEDIA_LEVEL", "MISSING_ARTICLE_TYPE", "FEE_RULE_NOT_FOUND"],
    },
    {
        "node_id": "node_06",
        "name": "生成付款表",
        "reads": ["quote_details"],
        "writes": ["monthly_summary", "payment_rows", "output_files"],
        "error_codes": ["NO_QUOTE_DETAILS", "NO_ELIGIBLE_QUOTE_DETAILS", "GENERATION_FAILED"],
    },
]


def get_node_catalog(node_id: str | None = None) -> dict[str, Any] | list[dict[str, Any]]:
    if node_id is None:
        return WORKFLOW_NODES
    for node in WORKFLOW_NODES:
        if node["node_id"] == node_id:
            return node
    raise KeyError(node_id)


def node_ids() -> list[str]:
    return [node["node_id"] for node in WORKFLOW_NODES]


def remaining_nodes(completed: list[str]) -> list[str]:
    done = set(completed)
    return [node_id for node_id in node_ids() if node_id not in done]
