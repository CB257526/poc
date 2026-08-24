"""平台解析器管理器"""

from typing import Dict, Type
from .base import BaseParser
from .zhihu import ZhihuParser
from .weibo import WeiboParser
from .bilibili import BilibiliParser
from .weixin import WeixinParser
from .douyin import DouyinParser
from .xiaohongshu import XiaohongshuParser
from .dongchedi import DongchediParser
from .yiche import YicheParser
from .toutiao import ToutiaoParser
from .baijiahao import BaijiahaoParser
from .sohu import SohuParser
from .generic import GenericParser


# 平台到解析器的映射
PARSER_MAP: Dict[str, Type[BaseParser]] = {
    "知乎": ZhihuParser,
    "微博": WeiboParser,
    "B站": BilibiliParser,
    "微信公众号": WeixinParser,
    "微信视频号": WeixinParser,  # 复用微信解析器
    "微信": WeixinParser,  # 通用微信
    "抖音": DouyinParser,
    "小红书": XiaohongshuParser,
    "懂车帝": DongchediParser,
    "易车": YicheParser,
    "今日头条": ToutiaoParser,
    "百家号": BaijiahaoParser,
    "搜狐": SohuParser,
}


def get_parser(platform: str) -> BaseParser:
    """
    获取指定平台的解析器

    Args:
        platform: 平台名称（如"知乎"、"微博"）

    Returns:
        解析器实例
    """
    parser_class = PARSER_MAP.get(platform, GenericParser)
    return parser_class()
