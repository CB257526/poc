"""节点2: 完善发布信息 - 通过网络爬取"""

import asyncio
from typing import Dict, Any, List
from datetime import datetime
from collections import defaultdict

from workflows.nodes.base import BaseNode
from workflows.models import WorkflowContext, NodeOutput, NodeMetrics, Issue
from workflows.services import get_logger
from workflows.utils.web_scraper import scrape_publications

logger = get_logger()


class Node02FillPublication(BaseNode):
    """
    完善发布信息节点

    职责：
    1. 通过网络爬取获取标题、发布日期、文章类型、截图
    2. 判断发布形式（原创/通稿）
    3. 验证必填字段
    """

    def __init__(self):
        super().__init__("node_02", "完善发布信息")

    def process(self, context: WorkflowContext) -> NodeOutput:
        """处理发布信息"""
        start_time = datetime.now()
        metrics = NodeMetrics()
        issues = []

        records = context.records
        if not records:
            return self._create_success_output(
                processed_count=0,
                success_count=0,
                data={},
                issues=[]
            )

        metrics.processed_count = len(records)

        try:
            # 并发爬取所有记录的主链接
            logger.info("starting_web_scraping", count=len(records))

            records_with_scraped = asyncio.run(scrape_publications(records))

            # 检查爬取结果并记录问题，同时将爬取结果映射到标准字段
            for record in records_with_scraped:
                record_id = record.get("id", "unknown")
                correction = (context.config.get("publication_corrections") or {}).get(str(record_id), {})
                corrected_title = str(correction.get("title") or "").strip()
                corrected_type = str(correction.get("article_type") or "").strip()

                if record.get("scrape_error"):
                    if not (corrected_title and corrected_type):
                        issues.append(Issue(
                            level="error",
                            code="SCRAPE_FAILED",
                            message=f"爬取失败: {record['scrape_error']}",
                            node_id=self.node_id,
                            record_id=record_id
                        ))
                        metrics.error_count += 1
                        continue

                # 验证必填字段
                if not (corrected_title or record.get("scraped_title")):
                    issues.append(Issue(
                        level="warning",
                        code="MISSING_TITLE",
                        message="未能提取标题",
                        node_id=self.node_id,
                        record_id=record_id
                    ))

                # 将爬取结果映射到标准字段，供后续节点使用
                record["标题"] = corrected_title or record.get("scraped_title")
                record["发布日期"] = record.get("scraped_publish_date")
                record["文章类型"] = corrected_type or record.get("scraped_article_type")
                record["截图"] = record.get("scraped_screenshot")
                record["平台"] = record.get("primary_platform")

                metrics.success_count += 1

            # 判断发布形式（原创/通稿）
            self._determine_publication_type(records_with_scraped)

            logger.info(
                "web_scraping_completed",
                total=len(records),
                success=metrics.success_count,
                errors=metrics.error_count
            )

        except Exception as e:
            logger.error("scraping_failed", error=str(e), exc_info=True)
            # 网页抓取只用于补充标题、发布日期和文章类型。浏览器不可用或站点
            # 限制抓取时，不应阻断媒体匹配、账户补全、费用计算和付款生成。
            for record in records:
                record.setdefault("标题", None)
                record.setdefault("发布日期", None)
                record.setdefault("文章类型", None)
                record.setdefault("截图", None)
                record["平台"] = record.get("primary_platform")
            issue = Issue(
                level="warning",
                code="SCRAPING_UNAVAILABLE",
                message="网页信息暂未获取，已继续进行媒体、账户及费用处理",
                node_id=self.node_id
            )
            issues.append(issue)
            metrics.error_count = len(records)
            logger.warning(
                "scraping_skipped_without_blocking_workflow",
                count=len(records),
            )

        # 计算耗时
        duration = (datetime.now() - start_time).total_seconds() * 1000
        metrics.duration_ms = duration

        return self._create_success_output(
            processed_count=metrics.processed_count,
            success_count=metrics.success_count,
            data={},
            issues=issues
        )

    def _determine_publication_type(self, records: List[Dict[str, Any]]):
        """
        判断发布形式：原创 vs 通稿

        逻辑：
        - 维护标题哈希表
        - 相同标题的视为通稿，不同标题视为原创

        Args:
            records: 记录列表（会直接修改）
        """
        # 标题 -> 记录列表
        title_groups = defaultdict(list)

        for record in records:
            title = record.get("scraped_title", "").strip()
            if title:
                # 标准化标题（去除空格、标点等）
                normalized_title = self._normalize_title(title)
                title_groups[normalized_title].append(record)

        # 标记发布形式
        for normalized_title, group in title_groups.items():
            if len(group) > 1:
                # 多个媒体使用相同标题 -> 通稿
                for record in group:
                    record["publication_type"] = "通稿"
                    record["发布形式"] = "通稿"
            else:
                # 唯一标题 -> 原创
                group[0]["publication_type"] = "原创"
                group[0]["发布形式"] = "原创"

        # 没有标题的记录标记为未知
        for record in records:
            if "publication_type" not in record:
                record["publication_type"] = "未知"
                record["发布形式"] = "未知"

    @staticmethod
    def _normalize_title(title: str) -> str:
        """
        标准化标题用于比较

        - 去除空格
        - 去除标点符号
        - 转小写
        """
        import re
        # 移除所有空白字符
        title = re.sub(r'\s+', '', title)
        # 移除标点符号
        title = re.sub(r'[^\w一-鿿]', '', title)
        # 转小写
        return title.lower()
