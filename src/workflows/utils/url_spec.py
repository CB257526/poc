"""表1 原始链接文本的 URL 规范校验。

只做校验、不做自动纠正。常见问题：
- 把 www 写成 ww / wwww
- 主机名里用了全角小数点（。．）或其他全角标点
- 缺少合法主机名、非法域名标签
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence
from urllib.parse import urlparse
import re

# 与 Node00 / Node01 提取规则一致：排除空白与中文，避免吃进「知乎：」或尾部说明
URL_PATTERN = re.compile(r"https?://[^\s一-龥]+", re.IGNORECASE)

# 单元格里可能残留的「像 URL 但夹了全角字符」的片段
URL_LIKE_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)

TRAILING_PUNCT = ".,;!?。，；！？'\"“”‘’）)]》>"

# Excel 里最常见的全角/不可见字符（小数点、空格、斜线、冒号等）
FORBIDDEN_IN_URL = re.compile(
    "["
    "。．、，；：！？／＼"
    "（）【】「」『』"
    "　 ​‌‍﻿"
    "]"
)

HOSTNAME_LABEL = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
IPV4_PATTERN = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")

# 把 www 写短 / 写长，几乎一定是笔误
WWW_TYPO_LABELS = {"w", "ww", "wwww", "wwwww", "wwwwww"}

ALLOWED_SCHEMES = {"http", "https"}


@dataclass(frozen=True)
class LinkSpecFinding:
    """一条候选链接的校验结果。"""

    text: str
    url: str
    reasons: List[str]

    @property
    def ok(self) -> bool:
        return not self.reasons


def strip_trailing_punct(url: str) -> str:
    return url.rstrip(TRAILING_PUNCT)


def extract_url_candidates(text: str) -> List[str]:
    """从原始单元格文本中抽出 URL 候选（含可能夹带全角字符的片段）。"""
    if not text:
        return []

    seen: set[str] = set()
    candidates: List[str] = []
    for pattern in (URL_LIKE_PATTERN, URL_PATTERN):
        for match in pattern.findall(str(text)):
            url = strip_trailing_punct(match)
            if url and url not in seen:
                seen.add(url)
                candidates.append(url)
    # 全角字符会让「排除中文」的正则提前截断，只保留更完整的那条
    return [
        url
        for url in candidates
        if not any(other != url and other.startswith(url) for other in candidates)
    ]


def _host_looks_ipv4(host: str) -> bool:
    if not IPV4_PATTERN.match(host):
        return False
    return all(0 <= int(part) <= 255 for part in host.split("."))


def validate_url(url: str) -> List[str]:
    """校验单条 URL，返回人类可读的原因列表；空列表表示通过。"""
    reasons: List[str] = []
    if not url or not str(url).strip():
        return ["链接为空"]

    raw = str(url).strip()
    if FORBIDDEN_IN_URL.search(raw):
        reasons.append("链接中含有全角标点或空白（例如全角小数点「。」「．」）")

    if any(ord(ch) < 32 for ch in raw):
        reasons.append("链接中含有控制字符")

    if " " in raw or "\t" in raw:
        reasons.append("链接中含有空格")

    try:
        parsed = urlparse(raw)
    except Exception:
        reasons.append("无法按 URL 规范解析")
        return reasons

    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        reasons.append("协议必须是 http 或 https")

    try:
        host = (parsed.hostname or "").strip(".")
    except (ValueError, UnicodeError):
        reasons.append("主机名无法按 URL 规范解析")
        return reasons
    netloc = parsed.netloc or ""

    if not host:
        reasons.append("缺少主机名")
        return reasons

    if "@" in netloc:
        reasons.append("不允许在链接中携带用户名/密码")

    if parsed.port is not None and not (1 <= parsed.port <= 65535):
        reasons.append("端口号不合法")

    if not host.isascii():
        reasons.append("主机名含有非 ASCII 字符，请改用半角域名")
        return reasons

    host_lower = host.lower()
    if _host_looks_ipv4(host_lower):
        return reasons

    labels = [part for part in host_lower.split(".")]
    if any(not part for part in host_lower.split(".")):
        reasons.append("主机名存在空的域名标签（连续的点）")

    if len(labels) < 2:
        reasons.append("主机名不是合法域名")

    for label in labels:
        if not label:
            continue
        if label.startswith("-") or label.endswith("-"):
            reasons.append(f"域名标签不合法: {label}")
        elif not HOSTNAME_LABEL.match(label):
            reasons.append(f"域名标签含非法字符: {label}")

    first = labels[0] if labels else ""
    if first in WWW_TYPO_LABELS:
        reasons.append(f"主机名疑似把 www 写成了 {first}")

    return reasons


def inspect_link_text(text: str) -> List[LinkSpecFinding]:
    """检查一段原始链接文本（可能含平台前缀、分享文案）。"""
    findings: List[LinkSpecFinding] = []
    seen: set[str] = set()
    source = "" if text is None else str(text)
    lines = source.split("\n") or [source]

    for line in lines:
        line = line.strip()
        if not line:
            continue
        for candidate in extract_url_candidates(line):
            if candidate in seen:
                continue
            seen.add(candidate)
            findings.append(
                LinkSpecFinding(
                    text=line,
                    url=candidate,
                    reasons=validate_url(candidate),
                )
            )

    if not findings:
        for candidate in extract_url_candidates(source):
            findings.append(
                LinkSpecFinding(
                    text=source,
                    url=candidate,
                    reasons=validate_url(candidate),
                )
            )
    return findings


def inspect_link_texts(texts: Iterable[str]) -> List[LinkSpecFinding]:
    findings: List[LinkSpecFinding] = []
    for text in texts:
        if text is None:
            continue
        findings.extend(inspect_link_text(str(text)))
    return findings


def invalid_link_findings(texts: Sequence[str] | None) -> List[LinkSpecFinding]:
    if not texts:
        return []
    return [item for item in inspect_link_texts(texts) if not item.ok]


def format_invalid_url_message(finding: LinkSpecFinding) -> str:
    reason = "；".join(finding.reasons) if finding.reasons else "不符合链接规范"
    return f"链接不符合规范: {finding.url}（{reason}）"
