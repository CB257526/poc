"""测试新增业务节点"""

import pytest
from datetime import datetime
from workflow.models import WorkflowContext
from workflow.nodes.node_02_fill_publication import Node02FillPublication
from workflow.nodes.node_03_match_media import Node03MatchMedia
from workflow.nodes.node_04_match_account import Node04MatchAccount
from workflow.nodes.node_05_calculate_fee import Node05CalculateFee
from workflow.nodes.node_06_generate_payment import Node06GeneratePayment


@pytest.fixture
def base_context():
    """创建基础上下文"""
    return WorkflowContext(
        run_id="test_run",
        run_started_at=datetime.now(),
        input_file="test.xlsx",
        table_dir="./table",
        records=[
            {
                "id": "1",
                "链接": "https://zhihu.com/article/123456",
                "媒体": "测试媒体",
                "平台": "知乎"
            }
        ]
    )


def test_node_02_normalize_link():
    """测试链接标准化"""
    node = Node02FillPublication()

    # 测试移除协议
    assert node._normalize_link("https://example.com/path") == "example.com/path"
    assert node._normalize_link("http://example.com/path") == "example.com/path"

    # 测试移除www
    assert node._normalize_link("https://www.example.com/path") == "example.com/path"

    # 测试移除查询参数
    assert node._normalize_link("https://example.com/path?key=value") == "example.com/path"

    # 测试移除尾部斜杠
    assert node._normalize_link("https://example.com/path/") == "example.com/path"

    # 测试组合情况
    assert node._normalize_link("https://www.example.com/path/?key=value") == "example.com/path"


def test_node_03_normalize_name():
    """测试名称标准化"""
    node = Node03MatchMedia()

    # 测试移除空格
    assert node._normalize_name("测试 媒体") == "测试媒体"
    assert node._normalize_name("测试　媒体") == "测试媒体"

    # 测试转换小写
    assert node._normalize_name("ABC") == "abc"
    assert node._normalize_name("Test Media") == "testmedia"


def test_node_04_normalize_name():
    """测试账户名称标准化"""
    node = Node04MatchAccount()

    # 测试移除空格和转换小写
    assert node._normalize_name("测试 账户") == "测试账户"
    assert node._normalize_name("ABC DEF") == "abcdef"


def test_node_05_parse_fee():
    """测试费用解析"""
    node = Node05CalculateFee()

    # 测试数字
    assert node._parse_fee(100) == 100.0
    assert node._parse_fee(100.5) == 100.5

    # 测试字符串
    assert node._parse_fee("100") == 100.0
    assert node._parse_fee("100.5") == 100.5

    # 测试带货币符号
    assert node._parse_fee("¥100") == 100.0
    assert node._parse_fee("￥100.5") == 100.5

    # 测试带逗号
    assert node._parse_fee("1,000") == 1000.0
    assert node._parse_fee("1,000.50") == 1000.5

    # 测试None和无效值
    assert node._parse_fee(None) is None
    assert node._parse_fee("invalid") is None


def test_node_06_extract_month():
    """测试月份提取"""
    node = Node06GeneratePayment()

    # 测试标准日期格式
    assert node._extract_month("2024-08-15") == "2024-08"
    assert node._extract_month("2024/08/15") == "2024-08"
    assert node._extract_month("20240815") == "2024-08"

    # 测试只有年月
    assert node._extract_month("2024-08") == "2024-08"
    assert node._extract_month("2024/08") == "2024-08"

    # 测试datetime对象
    dt = datetime(2024, 8, 15)
    assert node._extract_month(dt) == "2024-08"

    # 测试无效输入
    assert node._extract_month(None) == ""
    assert node._extract_month("") == ""
    assert node._extract_month("invalid") == ""


def test_workflow_with_all_nodes(base_context):
    """测试完整工作流（集成测试，需要真实表格文件）"""
    # 这个测试需要真实的表格文件，标记为可能跳过
    import os

    # 检查表格文件是否存在
    table_files = [
        "./table/2-约稿资料.xlsx",
        "./table/3-媒体库.xlsx",
        "./table/4-账户信息.xlsx",
        "./table/5-费用.xlsx"
    ]

    if not all(os.path.exists(f) for f in table_files):
        pytest.skip("需要真实的表格文件来运行集成测试")

    # 如果文件存在，测试各节点能够正常初始化
    node2 = Node02FillPublication()
    assert node2.node_id == "node_02"
    assert node2.node_name == "完善发布信息"

    node3 = Node03MatchMedia()
    assert node3.node_id == "node_03"
    assert node3.node_name == "匹配媒体库"

    node4 = Node04MatchAccount()
    assert node4.node_id == "node_04"
    assert node4.node_name == "匹配账户信息"

    node5 = Node05CalculateFee()
    assert node5.node_id == "node_05"
    assert node5.node_name == "计算费用"

    node6 = Node06GeneratePayment()
    assert node6.node_id == "node_06"
    assert node6.node_name == "生成付款表"
