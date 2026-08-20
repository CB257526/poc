"""节点1: 填写约稿资料基础信息

职责：
1. 读取表1（1-链接.xlsx）
2. 解析媒体名称和链接（处理媒体名称继承逻辑）
3. 从链接中提取URL，识别平台
4. 区分主发布链接和同步平台链接
5. 去重检查
"""

import re
import uuid
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import urlparse
from workflow.nodes.base import BaseNode
from workflow.models import WorkflowState, NodeOutput
from workflow.services import ExcelService, IssueCollector, get_logger

logger = get_logger()


# 平台域名映射表
PLATFORM_DOMAINS = {
    "zhihu.com": "知乎",
    "weibo.com": "微博",
    "weixin.qq.com": "微信视频号",
    "mp.weixin.qq.com": "微信公众号",
    "bilibili.com": "B站",
    "douyin.com": "抖音",
    "xiaohongshu.com": "小红书",
    "xhs.com": "小红书",
    "yiche.com": "易车",
    "dongchedi.com": "懂车帝",
    "baijiahao.baidu.com": "百家号",
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
    """节点1 - 填写约稿资料基础信息"""

    def __init__(self):
        super().__init__("node_01", "填写约稿资料基础信息")

    def execute(self, state: WorkflowState) -> NodeOutput:
        """执行节点逻辑"""
        issue_collector = IssueCollector()
        excel_service = ExcelService()

        # 获取表1路径
        table1_path = self._get_table_path(state, "1-链接")

        logger.info("reading_table1", path=table1_path)

        # === 1. 读取表1 ===
        try:
            rows = excel_service.read_sheet_as_dicts(table1_path, sheet_name="Sheet1")
        except Exception as e:
            raise ValueError(f"读取表1失败: {str(e)}")

        if not rows:
            raise ValueError("表1没有数据")

        logger.info("table1_read", rows=len(rows))

        # === 2. 解析链接，处理媒体名称继承 ===
        records = self._parse_links(rows, issue_collector)

        logger.info("links_parsed", records=len(records))

        # === 3. 识别平台 ===
        records = self._identify_platforms(records, issue_collector)

        # === 4. 区分主发布链接和同步链接 ===
        records = self._classify_primary_and_sync(records, issue_collector)

        # === 5. 去重检查 ===
        records = self._check_duplicates(records, issue_collector)

        # === 6. 更新状态 ===
        state["records"] = records

        # === 7. 生成输出 ===
        metrics = {
            "total_rows_read": len(rows),
            "records_created": len(records),
            "platforms_identified": len(set(r.get("primary_platform") for r in records if r.get("primary_platform"))),
            "duplicates_found": sum(1 for r in records if r.get("is_duplicate", False))
        }

        return self._create_success_output(
            data={"records": records},
            processed_count=len(rows),
            success_count=len(records),
            issues=issue_collector.get_issues(),
            metrics=metrics
        )

    def _parse_links(
        self,
        rows: List[Dict[str, Any]],
        issue_collector: IssueCollector
    ) -> List[Dict[str, Any]]:
        """
        解析链接，处理媒体名称继承逻辑

        表1的格式：
        - A列：媒体名称（只在第一行出现，后续行需要继承）或"主题X"
        - B列：链接（可能包含平台前缀，可能有多个链接用换行分隔）
        """
        records = []
        current_media = None
        current_topic = None
        row_index = 0

        for row in rows:
            row_index += 1

            col_a = row.get(list(row.keys())[0])  # A列
            col_b = row.get(list(row.keys())[1]) if len(row.keys()) > 1 else None  # B列

            # 处理A列（媒体名称或主题）
            if col_a and str(col_a).strip():
                col_a_clean = str(col_a).strip()

                # 判断是否是主题标记
                if col_a_clean.startswith("主题"):
                    current_topic = col_a_clean
                    logger.debug("topic_detected", topic=current_topic, row=row_index)
                    continue
                else:
                    # 这是新的媒体名称
                    current_media = col_a_clean
                    logger.debug("media_detected", media=current_media, row=row_index)

            # 处理B列（链接）
            if col_b and str(col_b).strip():
                if not current_media:
                    issue_collector.add_warning(
                        code="NO_MEDIA_CONTEXT",
                        message=f"第{row_index}行有链接但没有媒体上下文",
                        node_id=self.node_id,
                        details={"row": row_index, "content": col_b}
                    )
                    continue

                # 提取链接（可能有多个，用换行分隔）
                links = self._extract_urls_from_text(str(col_b))

                if not links:
                    issue_collector.add_warning(
                        code="NO_URL_FOUND",
                        message=f"第{row_index}行无法提取URL",
                        node_id=self.node_id,
                        details={"row": row_index, "content": col_b}
                    )
                    continue

                # 为每个链接创建一条记录
                for link_text, url in links:
                    record_id = f"rec_{uuid.uuid4().hex[:8]}"

                    record = {
                        "record_id": record_id,
                        "media_name": current_media,
                        "topic": current_topic,
                        "raw_text": link_text,
                        "url": url,
                        "source_row": row_index,
                        "primary_link": None,  # 后续步骤填充
                        "primary_platform": None,  # 后续步骤填充
                        "sync_links": [],  # 后续步骤填充
                    }

                    records.append(record)

        logger.info("links_parsed", total_links=len(records))
        return records

    def _extract_urls_from_text(self, text: str) -> List[Tuple[str, str]]:
        """
        从文本中提取URL

        返回 [(原始文本, 提取的URL), ...]
        """
        # URL正则表达式
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

    def _identify_platforms(
        self,
        records: List[Dict[str, Any]],
        issue_collector: IssueCollector
    ) -> List[Dict[str, Any]]:
        """识别平台"""
        for record in records:
            url = record.get("url")
            if not url:
                continue

            try:
                parsed = urlparse(url)
                domain = parsed.netloc.lower()

                # 移除 www. 前缀
                if domain.startswith("www."):
                    domain = domain[4:]

                # 匹配平台
                platform = None
                for domain_pattern, platform_name in PLATFORM_DOMAINS.items():
                    if domain_pattern in domain:
                        platform = platform_name
                        break

                if platform:
                    record["platform"] = platform
                else:
                    record["platform"] = "unknown"
                    issue_collector.add_warning(
                        code="UNKNOWN_PLATFORM",
                        message=f"无法识别平台: {domain}",
                        node_id=self.node_id,
                        record_id=record["record_id"],
                        details={"url": url, "domain": domain}
                    )

            except Exception as e:
                issue_collector.add_warning(
                    code="URL_PARSE_FAILED",
                    message=f"URL解析失败: {str(e)}",
                    node_id=self.node_id,
                    record_id=record["record_id"],
                    details={"url": url}
                )
                record["platform"] = "unknown"

        return records

    def _classify_primary_and_sync(
        self,
        records: List[Dict[str, Any]],
        issue_collector: IssueCollector
    ) -> List[Dict[str, Any]]:
        """
        区分主发布链接和同步链接

        策略：按媒体分组，每个媒体选择优先级最高的平台作为主平台
        """
        # 按媒体分组
        media_groups: Dict[str, List[Dict[str, Any]]] = {}
        for record in records:
            media_name = record.get("media_name")
            if not media_name:
                continue

            if media_name not in media_groups:
                media_groups[media_name] = []

            media_groups[media_name].append(record)

        # 为每个媒体组选择主链接
        result_records = []

        for media_name, group_records in media_groups.items():
            if len(group_records) == 1:
                # 只有一个链接，直接作为主链接
                record = group_records[0]
                record["primary_link"] = record["url"]
                record["primary_platform"] = record["platform"]
                record["sync_links"] = []
                result_records.append(record)

            else:
                # 多个链接，按优先级选择主链接
                # 按平台优先级排序
                sorted_records = sorted(
                    group_records,
                    key=lambda r: PLATFORM_PRIORITY.get(r.get("platform", "unknown"), 999)
                )

                # 第一个是主链接
                primary_record = sorted_records[0]

                # 其他是同步链接
                sync_links = [
                    {
                        "url": r["url"],
                        "platform": r["platform"],
                        "raw_text": r["raw_text"]
                    }
                    for r in sorted_records[1:]
                ]

                # 创建一条合并的记录
                merged_record = {
                    "record_id": primary_record["record_id"],
                    "media_name": media_name,
                    "topic": primary_record.get("topic"),
                    "primary_link": primary_record["url"],
                    "primary_platform": primary_record["platform"],
                    "sync_links": sync_links,
                    "source_row": primary_record["source_row"]
                }

                result_records.append(merged_record)

                logger.debug(
                    "primary_selected",
                    media=media_name,
                    primary_platform=primary_record["platform"],
                    sync_count=len(sync_links)
                )

        return result_records

    def _check_duplicates(
        self,
        records: List[Dict[str, Any]],
        issue_collector: IssueCollector
    ) -> List[Dict[str, Any]]:
        """检查重复链接"""
        seen_urls = {}

        for record in records:
            url = record.get("primary_link")
            if not url:
                continue

            if url in seen_urls:
                # 发现重复
                original_record_id = seen_urls[url]
                record["is_duplicate"] = True
                record["duplicate_of"] = original_record_id

                issue_collector.add_warning(
                    code="DUPLICATE_URL",
                    message=f"发现重复的URL: {url}",
                    node_id=self.node_id,
                    record_id=record["record_id"],
                    details={
                        "url": url,
                        "original_record": original_record_id,
                        "current_media": record.get("media_name"),
                    }
                )
            else:
                seen_urls[url] = record["record_id"]
                record["is_duplicate"] = False

        return records
