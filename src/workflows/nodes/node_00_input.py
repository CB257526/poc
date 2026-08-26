"""节点0: 输入验证 - 新版本"""

from workflows.nodes.base import BaseNode
from workflows.models import WorkflowContext, NodeOutput, Issue
from workflows.services import ExcelService, get_logger
from workflows.utils.url_spec import (
    URL_PATTERN,
    format_invalid_url_message,
    invalid_link_findings,
)
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, parse_qsl
import os

logger = get_logger()

# 链接归一化时忽略的查询参数（分享/埋点参数，不参与内容标识）
# 这些参数只影响来源统计，同一篇内容多次分享会产生不同的值
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_psn", "utm_id",
    "share_code", "share_token", "share_did", "share_uid", "share_source",
    "shp1", "timestamp", "req_id_new", "chn_id", "category_new",
    "module_name", "tt_from", "upstream_biz", "use_new_style",
    "link_source", "app", "aid", "iid",
    "spm", "spm_id_from", "vd_source", "seid",
    "from", "ref", "refer", "source",
}


class Node00Input(BaseNode):
    """
    节点0: 输入验证

    职责：
    1. 验证输入文件存在且可读
    2. 验证参考表格存在
    3. 读取输入文件的记录
    4. 初始化记录结构
    """

    def __init__(self):
        super().__init__("node_00", "输入验证")

    def process(self, context: WorkflowContext) -> NodeOutput:
        """
        执行输入验证

        Args:
            context: 工作流上下文

        Returns:
            NodeOutput，包含验证结果和初始化的记录
        """
        excel = ExcelService()
        issues = []
        processed_count = 0
        success_count = 0

        # === 1. 验证输入文件 ===
        if not os.path.exists(context.input_file):
            issues.append(Issue(
                level="critical",
                code="INPUT_FILE_NOT_FOUND",
                message=f"输入文件不存在: {context.input_file}",
                node_id=self.node_id
            ))
            return self._create_failure_output(
                processed_count=0,
                success_count=0,
                issues=issues
            )

        # === 2. 验证参考表格 ===
        required_tables = ["3-媒体库", "4-账户信息", "5-费用"]
        for table_name in required_tables:
            try:
                context.get_table_path(table_name)
            except FileNotFoundError as e:
                issues.append(Issue(
                    level="critical",
                    code="REFERENCE_TABLE_NOT_FOUND",
                    message=str(e),
                    node_id=self.node_id,
                    details={"table_name": table_name}
                ))

        # 如果有 critical 错误，提前返回
        if any(i.level == "critical" for i in issues):
            return self._create_failure_output(
                processed_count=0,
                success_count=0,
                issues=issues
            )

        # === 3. 读取输入文件 ===
        try:
            # 1-链接.xlsx 是无表头的"主题-媒体-链接"分层表，用专用方法解析
            rows = excel.read_link_sheet(context.input_file, sheet_name="Sheet1")
            if not rows:
                issues.append(Issue(
                    level="critical",
                    code="EMPTY_INPUT_FILE",
                    message="输入文件为空",
                    node_id=self.node_id 
                ))
                return self._create_failure_output(
                    processed_count=0,
                    success_count=0,
                    issues=issues
                )

            processed_count = len(rows)

        except Exception as e:
            issues.append(Issue(
                level="critical",
                code="READ_INPUT_FILE_FAILED",
                message=f"读取输入文件失败: {str(e)}",
                node_id=self.node_id
            ))
            return self._create_failure_output(
                processed_count=0,
                success_count=0,
                issues=issues
            )

        # === 4. 读取媒体库名称，供下一步校验 ===
        # 归一化规则与 Node3 保持一致，避免两处对"同名"的判断不同
        known_media_names = None
        try:
            media_table_path = context.get_table_path("3-媒体库")
            media_rows = excel.read_sheet_as_dicts(media_table_path)
            known_media_names = {
                self._normalize_name(name): str(name).strip()
                for row in media_rows
                if (name := row.get("媒体") or row.get("媒体名称") or row.get("账号"))
            }
            known_media_names.pop("", None)
            logger.info(
                "media_names_loaded_for_validation",
                path=media_table_path,
                names_count=len(known_media_names)
            )
        except Exception as e:
            # 读不到媒体库时跳过本项校验，交由 Node3 报 critical，不在此处中断
            issues.append(Issue(
                level="error",
                code="MEDIA_TABLE_LOAD_FAILED",
                message=f"无法加载媒体库表，跳过媒体名称校验: {str(e)}",
                node_id=self.node_id
            ))

        # === 5. 按主题+媒体合并与去重 ===
        # 同一主题中的同一媒体可能被用户多次填入（补链接时），需要合并+去重
        merged_rows = self._merge_duplicate_media(rows, issues)

        # 合并后的条数才是本节点实际要处理的记录数，
        # 否则被合并掉的行会被 error_count 当成失败记录
        processed_count = len(merged_rows)

        # === 6. 初始化记录结构 ===
        records = []
        # 前端在首次校验发现媒体名错误后，可按 Excel 行号提交修正值。
        # 工作流会从节点0重新执行，确保修正后的名称仍经过完整校验，再进入后续节点。
        media_name_corrections = {
            str(key): str(value).strip()
            for key, value in (context.config.get("media_name_corrections") or {}).items()
            if str(value).strip()
        }

        for idx, row in enumerate(merged_rows):
            record_id = f"rec_{idx + 1:04d}"

            correction = media_name_corrections.get(str(row.get("row_number")))
            if correction:
                row = {**row, "媒体": correction}

            # 验证必需字段（链接为列表，空列表视为缺失）
            if not row.get("链接"):
                issues.append(Issue(
                    level="error",
                    code="MISSING_REQUIRED_FIELD",
                    message="缺少必需字段：链接",
                    node_id=self.node_id,
                    record_id=record_id
                ))
                continue

            # 校验媒体名称是否存在于媒体库
            media_name = row.get("媒体")
            if known_media_names is not None and media_name:
                if self._normalize_name(media_name) not in known_media_names:
                    issues.append(Issue(
                        level="error",
                        code="MEDIA_NOT_IN_LIBRARY",
                        message=f"媒体库中没有这个媒体: {media_name}",
                        node_id=self.node_id,
                        record_id=record_id,
                        details={
                            "media_name": media_name,
                            "row_number": row.get("row_number"),
                            "allowed_media_names": sorted(known_media_names.values()),
                        }
                    ))

            issues.extend(self._validate_record_links(record_id, row))

            # 创建记录（read_link_sheet 已按媒体聚合，每条记录即一个媒体块，
            # 链接为列表，供 Node1 逐条解析并合并主链接+同步链接）
            record = {
                **row,
                "id": record_id,
            }

            records.append(record)
            success_count += 1

        logger.info(
            "input_validation_completed",
            total_rows=processed_count,
            valid_records=success_count,
            issues_count=len(issues)
        )

        # === 7. 返回结果 ===
        return self._create_success_output(
            processed_count=processed_count, #已处理的总记录数
            success_count=success_count, #成功处理的记录数
            data={"records": records}, #读取表内容
            issues=issues #问题列表
        )

    def _merge_duplicate_media(
        self,
        rows: List[Dict[str, Any]],
        issues: List[Issue]
    ) -> List[Dict[str, Any]]:
        """
        合并同一主题中多次出现的同一媒体，去重链接

        场景：
        - 用户第一次填了几条链接，后来想起还有其他平台，又添一行填剩余链接
        - 第二次填写的链接文本可能与第一次不同（如"知乎：https://..."vs"https://..."），
          但实际 URL 相同 → 需要归一化后再判断重复

        策略：
        - 按(主题, 媒体名称)分组
        - 合并同组的所有链接列表
        - 对所有链接归一化 URL 后去重（保留第一次出现的原始文本）
        - row_number 取第一次出现的位置

        Args:
            rows: read_link_sheet 的原始输出（每条记录对应一个媒体块）
            issues: 问题列表，遇到重复会添加 warning

        Returns:
            合并去重后的记录列表
        """
        # 按(主题, 媒体)分组
        groups: Dict[Tuple[Optional[str], str], List[Dict[str, Any]]] = {}

        for row in rows:
            topic = row.get("主题")
            media = row.get("媒体")

            if not media:
                # 没有媒体名，无法分组，直接保留（后续会因缺字段报错）
                continue

            key = (topic, media)
            if key not in groups:
                groups[key] = []
            groups[key].append(row)

        # 合并每组
        merged = []

        for (topic, media), group_rows in groups.items():
            if len(group_rows) == 1:
                # 该媒体只出现一次，直接使用
                merged.append(group_rows[0])
                continue

            # 同一主题中该媒体出现多次 → 需要合并
            logger.info(
                "merge_duplicate_media_within_topic",
                topic=topic,
                media=media,
                occurrences=len(group_rows)
            )

            # 取第一次出现的 row_number
            first_row_number = group_rows[0].get("row_number")

            # 合并所有链接
            all_link_texts = []
            for r in group_rows:
                all_link_texts.extend(r.get("链接", []))

            # 去重：归一化 URL 后判断，保留第一次出现的原始文本
            seen_normalized: Dict[str, str] = {}  # {归一化URL: 原始文本}
            unique_links = []
            duplicates_found = []

            for link_text in all_link_texts:
                normalized = self._normalize_url(link_text)

                if not normalized:
                    # 无法提取 URL，保留原文本（后续 Node1 会报 warning）
                    unique_links.append(link_text)
                    continue

                if normalized in seen_normalized:
                    # 重复链接
                    duplicates_found.append({
                        "original": seen_normalized[normalized],
                        "duplicate": link_text,
                        "normalized": normalized
                    })
                else:
                    seen_normalized[normalized] = link_text
                    unique_links.append(link_text)

            # 记录去重情况
            if duplicates_found:
                issues.append(Issue(
                    level="warning",
                    code="DUPLICATE_LINKS_MERGED",
                    message=f"合并重复媒体时发现 {len(duplicates_found)} 条重复链接已去除: {media}（主题: {topic}）",
                    node_id=self.node_id,
                    details={
                        "topic": topic,
                        "media": media,
                        "duplicates": duplicates_found[:5]  # 最多记录5条示例
                    }
                ))

            # 构造合并后的记录
            merged_row = {
                "主题": topic,
                "媒体": media,
                "row_number": first_row_number,
                "链接": unique_links,
            }

            merged.append(merged_row)

        return merged

    def _validate_record_links(self, record_id: str, row: Dict[str, Any]) -> List[Issue]:
        """校验表1原始链接文本是否符合 URL 规范，不做自动纠正。"""
        issues: List[Issue] = []
        for finding in invalid_link_findings(self._link_texts(row)):
            issues.append(Issue(
                level="error",
                code="INVALID_URL",
                message=format_invalid_url_message(finding),
                node_id=self.node_id,
                record_id=record_id,
                details={
                    "url": finding.url,
                    "raw_text": finding.text,
                    "reasons": finding.reasons,
                    "row_number": row.get("row_number"),
                    "media_name": row.get("媒体"),
                },
            ))
        return issues

    @staticmethod
    def _link_texts(row: Dict[str, Any]) -> List[str]:
        links = row.get("链接") or []
        if isinstance(links, str):
            return [links] if links.strip() else []
        return [str(item) for item in links if item and str(item).strip()]

    def _normalize_url(self, link_text: str) -> str:
        """
        从链接文本中提取并归一化 URL，用于去重比较

        处理：
        1. 提取 URL（去除"知乎："前缀、引号等）
        2. 移除分享/埋点参数（utm_*, share_*, timestamp 等）
        3. 统一协议为 https
        4. 去除末尾斜杠
        5. 转小写（域名部分）

        Args:
            link_text: 原始链接文本，如"知乎：https://www.zhihu.com/..."

        Returns:
            归一化后的 URL，提取失败返回空字符串
        """
        # 1. 提取 URL
        match = URL_PATTERN.search(link_text)
        if not match:
            return ""

        url = match.group(0)

        # 清理末尾可能误匹配的标点
        url = url.rstrip(".,;!?。，；！？'\"“”‘’")

        try:
            # 2. 解析
            parsed = urlparse(url)

            # 3. 过滤查询参数（移除追踪参数）
            if parsed.query:
                params = parse_qsl(parsed.query, keep_blank_values=True)
                # 保留非追踪参数；空参数名（如懂车帝分享链的 "?=" ）无意义，一并丢弃
                filtered_params = [
                    (k, v) for k, v in params
                    if k and k not in TRACKING_PARAMS
                ]
                # 重建 query（排序以保证一致性）
                filtered_query = "&".join(
                    f"{k}={v}" for k, v in sorted(filtered_params)
                )
            else:
                filtered_query = ""

            # 4. 统一协议为 https
            scheme = "https"

            # 5. 域名小写
            netloc = parsed.netloc.lower()

            # 6. 路径保持原样（可能包含大小写敏感的 ID）
            path = parsed.path.rstrip("/")  # 去除末尾斜杠

            # 7. 重建 URL
            normalized = f"{scheme}://{netloc}{path}"
            if filtered_query:
                normalized += f"?{filtered_query}"

            return normalized

        except Exception as e:
            logger.warning(
                "url_normalize_failed",
                link_text=link_text,
                error=str(e)
            )
            return ""

    @staticmethod
    def _normalize_name(name: str) -> str:
        """
        标准化名称用于比较（与 Node3 的 _normalize_name 规则一致）

        - 移除空格
        - 转换为小写
        """
        if not name:
            return ""

        name = str(name).replace(" ", "").replace("　", "")
        return name.lower()


# {
#   "主题": "主题1",
#   "媒体": "Alex Cui",
#   "row_n umber": 2, 
#   "链接": [
#     "https://weixin.qq.com/sph/A6rPIi6ml",
#     "微博：https://weibo.com/2633750580/Qohm9jAvX",
#     "b站：https://www.bilibili.com/video/BV1RgzpBHEQL/",
#     "抖音： https://v.douyin.com/k4T4MKGl61M/ S@Y.zg",
#     "小红书： http://xhslink.com/o/4ri7r97p7NR",
#     "知乎： https://www.zhihu.com/zvideo/1997648866380632485",
#     "易车：https://vc.m.yiche.com/vplay/10594881.html",
#     "懂车帝：https://dcd.zjbyte.cn/i7598033298614583870/?link_source=share&app=automobile"
#   ],
#   "id": "rec_0001"
# }
