"""节点1: 填写约稿资料基础信息 - 新版本"""

import re
import uuid
from typing import Dict, Any, List, Tuple
from urllib.parse import urlparse

from workflows.nodes.base import BaseNode
from workflows.models import WorkflowContext, NodeOutput, Issue
from workflows.services import get_logger

logger = get_logger()


# 平台域名映射表（按优先级排序，更具体的在前面）
PLATFORM_DOMAINS = {
    "mp.weixin.qq.com": "微信公众号",  # 更具体的在前
    "weixin.qq.com": "微信视频号",     # 更通用的在后
    "zhihu.com": "知乎",
    "weibo.com": "微博",
    "bilibili.com": "B站",
    "douyin.com": "抖音",
    "xiaohongshu.com": "小红书",
    "xhs.com": "小红书",
    "xhslink.com": "小红书",  # 小红书短链
    "yiche.com": "易车",
    "dongchedi.com": "懂车帝",
    "dcd.zjbyte.cn": "懂车帝",  # 懂车帝短链
    "baijiahao.baidu.com": "百家号",
    "mbd.baidu.com": "百家号",  # 百家号移动端短链
    "mr.baidu.com": "百家号",   # 百度分享短链
    "toutiao.com": "今日头条",
    "sohu.com": "搜狐",
    "autohome.com.cn": "汽车之家",
}

# 主平台优先级（数字越小优先级越高）
PLATFORM_PRIORITY = {
    "知乎": 1,
    "微信公众号": 2,
    "微信视频号": 3,
    "微博": 4,
    "B站": 5,
    "抖音": 6,
    "小红书": 7,
}


class Node01FillBasic(BaseNode):
    """
    节点1: 填写约稿资料基础信息

    职责：
    1. 解析链接，处理媒体名称继承逻辑
    2. 从链接中提取URL，识别平台
    3. 区分主发布链接和同步平台链接
    4. 去重检查
    """

    def __init__(self):
        super().__init__("node_01", "填写约稿资料基础信息")

    def process(self, context: WorkflowContext) -> NodeOutput:
        """
        执行节点逻辑

        Args:
            context: 工作流上下文

        Returns:
            NodeOutput，包含解析后的记录
        """
        # 从 context 读取记录（由节点0创建）
        raw_records = context.records
        if not raw_records:
            return self._create_success_output(
                processed_count=0,
                success_count=0,
                data={},
                issues=[]
            )

        issues = []
        processed_count = len(raw_records)

        logger.info("processing_records", count=processed_count)

        # === 1. 解析每条记录中的链接 ===
        parsed_records = []
        for record in raw_records:
            links = record.get("链接")
            if not links:
                continue

            # 兼容字符串与列表两种形态（新结构下为列表）
            if isinstance(links, str):
                links = [links]

            for link_text in links:
                # 提取URL（一条链接文本可能包含多个URL）
                urls = self._extract_urls_from_text(str(link_text))

                if not urls:
                    issues.append(Issue(
                        level="warning",
                        code="NO_URL_FOUND",
                        message=f"无法从文本中提取URL: {link_text}",
                        node_id=self.node_id,
                        record_id=record.get("id")
                    ))
                    continue

                # 为每个URL创建一条记录
                for raw_text, extracted_url in urls:
                    parsed_record = {
                        **record,  # 继承原始数据
                        "raw_link_text": raw_text,
                        "url": extracted_url,
                        "platform": None,  # 下一步填充
                    }
                    parsed_records.append(parsed_record)

        logger.info("urls_extracted", total_urls=len(parsed_records))

        # === 2. 识别平台 ===
        for record in parsed_records:
            url = record.get("url")
            if url:
                platform = self._identify_platform(url)
                record["platform"] = platform

                if platform == "unknown":
                    issues.append(Issue(
                        level="warning",
                        code="UNKNOWN_PLATFORM",
                        message=f"无法识别平台: {url}",
                        node_id=self.node_id,
                        record_id=record.get("id")
                    ))

        # === 3. 按媒体分组，区分主链接和同步链接 ===
        final_records = self._group_by_media(parsed_records)

        logger.info("records_grouped", final_count=len(final_records))

        # === 4. 去重检查 ===
        final_records = self._check_duplicates(final_records, issues)

        success_count = len(final_records)

        # === 5. 返回结果 ===
        return self._create_success_output(
            processed_count=processed_count,
            success_count=success_count,
            data={"records": final_records},
            issues=issues
        )

    def _extract_urls_from_text(self, text: str) -> List[Tuple[str, str]]:
        """
        从文本中提取URL

        Args:
            text: 原始文本

        Returns:
            [(原始文本行, 提取的URL), ...]
        """
        url_pattern = r'https?://[^\s一-龥]+'
        results = []

        # 按行分割（处理多个链接的情况）
        lines = text.split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 查找URL
            urls = re.findall(url_pattern, line)

            if urls:
                # 取第一个URL
                url = urls[0]
                # 清理URL（移除末尾的标点符号）
                url = url.rstrip('.,;!?。，；！？')
                results.append((line, url))

        return results

    def _identify_platform(self, url: str) -> str:
        """
        识别平台

        Args:
            url: URL

        Returns:
            平台名称，如 "知乎"、"微博"，未识别返回 "unknown"
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # 移除 www. 前缀
            if domain.startswith("www."):
                domain = domain[4:]

            # 匹配平台
            for domain_pattern, platform_name in PLATFORM_DOMAINS.items():
                if domain_pattern in domain:
                    return platform_name

            return "unknown"

        except Exception as e:
            logger.warning("url_parse_failed", url=url, error=str(e))
            return "unknown"

    def _group_by_media(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        按媒体分组，区分主链接和同步链接

        策略：
        - 如果一个记录ID对应多个URL，按平台优先级选择主链接
        - 其他链接作为同步链接

        Args:
            records: 解析后的记录列表

        Returns:
            合并后的记录列表
        """
        # 按记录ID分组
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for record in records:
            record_id = record.get("id")
            if not record_id:
                continue

            if record_id not in groups:
                groups[record_id] = []

            groups[record_id].append(record)

        # 合并每组
        result_records = []

        for record_id, group in groups.items():
            if len(group) == 1:
                # 只有一个链接，直接作为主链接
                record = group[0]
                record["primary_link"] = record["url"]
                record["primary_platform"] = record["platform"]
                record["sync_links"] = []
                result_records.append(record)

            else:
                # 多个链接，按优先级选择主链接
                sorted_group = sorted(
                    group,
                    key=lambda r: PLATFORM_PRIORITY.get(r.get("platform", "unknown"), 999)
                )

                # 第一个是主链接
                primary = sorted_group[0]

                # 其他是同步链接
                sync_links = [
                    {
                        "url": r["url"],
                        "platform": r["platform"],
                        "raw_text": r.get("raw_link_text", "")
                    }
                    for r in sorted_group[1:]
                ]

                # 合并记录
                merged = {
                    **primary,
                    "primary_link": primary["url"],
                    "primary_platform": primary["platform"],
                    "sync_links": sync_links
                }

                result_records.append(merged)

                logger.debug(
                    "links_merged",
                    record_id=record_id,
                    primary_platform=primary["platform"],
                    sync_count=len(sync_links)
                )

        return result_records

    def _check_duplicates(
        self,
        records: List[Dict[str, Any]],
        issues: List[Issue]
    ) -> List[Dict[str, Any]]:
        """
        检查重复的主链接

        Args:
            records: 记录列表
            issues: 问题列表（会添加新的问题）

        Returns:
            标记了重复的记录列表
        """
        seen_urls = {}

        for record in records:
            url = record.get("primary_link")
            if not url:
                continue

            if url in seen_urls:
                # 发现重复
                original_id = seen_urls[url]
                record["is_duplicate"] = True
                record["duplicate_of"] = original_id

                issues.append(Issue(
                    level="warning",
                    code="DUPLICATE_URL",
                    message=f"发现重复的URL: {url}",
                    node_id=self.node_id,
                    record_id=record.get("id"),
                    details={
                        "url": url,
                        "original_record": original_id
                    }
                ))
            else:
                seen_urls[url] = record.get("id")
                record["is_duplicate"] = False

        return records
