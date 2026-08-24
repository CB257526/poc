"""测试新增业务节点"""

import pytest
from datetime import datetime
from workflows.models import WorkflowContext
from workflows.nodes.node_02_fill_publication import Node02FillPublication
from workflows.nodes.node_03_match_media import Node03MatchMedia
from workflows.nodes.node_04_match_account import Node04MatchAccount
from workflows.nodes.node_05_calculate_fee import Node05CalculateFee
from workflows.nodes.node_06_generate_payment import Node06GeneratePayment


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


# ============================================================
# 回归测试：针对真实表格结构修复的字段映射与转换逻辑
# ============================================================

def test_node_02_convert_excel_date():
    """测试 Excel 序列日期转换（约稿表发布日期为序列号，如 46050=2026-01-28）"""
    node = Node02FillPublication()

    # Excel 序列号（int / float / 字符串）
    assert node._convert_excel_date(46050) == "2026-01-28"
    assert node._convert_excel_date(46050.0) == "2026-01-28"
    assert node._convert_excel_date("46050") == "2026-01-28"

    # datetime 对象
    assert node._convert_excel_date(datetime(2026, 2, 3)) == "2026-02-03"

    # 普通日期字符串
    assert node._convert_excel_date("2026-01-22") == "2026-01-22"
    assert node._convert_excel_date("2026/02/15") == "2026-02-15"

    # 空值 / 无法识别
    assert node._convert_excel_date(None) is None
    assert node._convert_excel_date("") is None


def test_node_02_normalize_link_with_quotes():
    """测试链接标准化能清理引号（源表中链接常被引号包裹）"""
    node = Node02FillPublication()

    # 带尾引号（来自 1-链接 表）
    assert node._normalize_link('https://www.bilibili.com/opus/1160708465008574473"') \
        == "bilibili.com/opus/1160708465008574473"
    # 带开头引号（同时验证查询参数会被移除）
    assert node._normalize_link('"https://weibo.com/ttarticle/p/show?id=2309405257991917273143') \
        == "weibo.com/ttarticle/p/show"
    # 单引号包裹
    assert node._normalize_link("'https://example.com/path/'") == "example.com/path"


def test_node_03_media_field_mapping():
    """测试媒体库列名映射（真实表头：媒体级别/粉丝量，而非媒体等级/粉丝数）"""
    node = Node03MatchMedia()
    node._media_data = [
        {"序号": 1, "媒体名称": "Alex Cui", "媒体级别": "FA", "粉丝量": "20.4w（微博129.2w）"},
        {"序号": 2, "媒体名称": "Oxygen", "媒体级别": "FC", "粉丝量": "4.3w"},
    ]

    matched = node._match_media_info("Alex Cui")
    assert matched is not None
    # 关键：能取到媒体级别和粉丝量
    assert matched.get("媒体级别") == "FA"
    assert matched.get("粉丝量") == "20.4w（微博129.2w）"


def test_node_03_rejects_duplicate_media_name():
    """媒体库重名时不得静默使用第一条记录。"""
    node = Node03MatchMedia()
    node._media_data = [
        {"媒体名称": "Alex Cui", "媒体级别": "FA", "粉丝量": "20.4w"},
        {"媒体名称": "Alex Cui", "媒体级别": "FB", "粉丝量": "10w"},
    ]

    assert node._match_media_info("Alex Cui") is None
    assert len(node._build_media_index()["alexcui"]) == 2


def test_node_03_process_success(monkeypatch, base_context):
    """匹配成功时写入媒体等级、粉丝量及可处理状态。"""
    monkeypatch.setattr(
        "workflows.nodes.node_03_match_media.ExcelService.read_sheet_as_dicts",
        lambda _: [{"媒体名称": "测试媒体", "媒体级别": "FA", "粉丝量": "20w"}],
    )

    output = Node03MatchMedia().process(base_context)

    assert output.success is True
    assert output.metrics.success_count == 1
    assert output.metrics.error_count == 0
    assert base_context.records[0]["媒体等级"] == "FA"
    assert base_context.records[0]["粉丝量"] == "20w"
    assert base_context.records[0]["media_match_status"] == "matched"
    assert base_context.records[0]["processable"] is True


def test_node_03_process_media_not_found_is_error(monkeypatch, base_context):
    """表1媒体名无法匹配时生成error并阻止后续业务处理。"""
    monkeypatch.setattr(
        "workflows.nodes.node_03_match_media.ExcelService.read_sheet_as_dicts",
        lambda _: [{"媒体名称": "另一个媒体", "媒体级别": "FA", "粉丝量": "20w"}],
    )

    output = Node03MatchMedia().process(base_context)

    assert output.metrics.error_count == 1
    assert any(issue.level == "error" and issue.code == "MEDIA_NOT_FOUND" for issue in output.issues)
    assert base_context.records[0]["media_match_status"] == "pending_confirmation"
    assert base_context.records[0]["processable"] is False


def test_node_03_does_not_duplicate_node_00_media_error(monkeypatch, base_context):
    """节点0已报告媒体名称错误时，节点3只设置拦截状态，不重复报错。"""
    base_context.add_issue(
        level="error",
        code="MEDIA_NOT_IN_LIBRARY",
        message="媒体库中没有这个媒体: 测试媒体",
        node_id="node_00",
        record_id="1",
    )
    monkeypatch.setattr(
        "workflows.nodes.node_03_match_media.ExcelService.read_sheet_as_dicts",
        lambda _: [{"媒体名称": "另一个媒体", "媒体级别": "FA", "粉丝量": "20w"}],
    )

    output = Node03MatchMedia().process(base_context)

    assert not any(issue.code == "MEDIA_NOT_FOUND" for issue in output.issues)
    assert base_context.records[0]["media_match_status"] == "pending_confirmation"
    assert base_context.records[0]["processable"] is False


def test_node_03_process_missing_fan_count_is_error(monkeypatch, base_context):
    """媒体库缺少粉丝量时生成error并标记记录不完整。"""
    monkeypatch.setattr(
        "workflows.nodes.node_03_match_media.ExcelService.read_sheet_as_dicts",
        lambda _: [{"媒体名称": "测试媒体", "媒体级别": "FA", "粉丝量": None}],
    )

    output = Node03MatchMedia().process(base_context)

    assert output.metrics.error_count == 1
    assert any(issue.level == "error" and issue.code == "MISSING_FAN_COUNT" for issue in output.issues)
    assert base_context.records[0]["media_match_status"] == "incomplete"
    assert base_context.records[0]["processable"] is False


def test_node_03_process_missing_media_level_is_error(monkeypatch, base_context):
    """媒体库缺少媒体级别时生成error并阻止后续业务处理。"""
    monkeypatch.setattr(
        "workflows.nodes.node_03_match_media.ExcelService.read_sheet_as_dicts",
        lambda _: [{"媒体名称": "测试媒体", "媒体级别": None, "粉丝量": "20w"}],
    )

    output = Node03MatchMedia().process(base_context)

    assert output.metrics.error_count == 1
    assert any(issue.level == "error" and issue.code == "MISSING_MEDIA_LEVEL" for issue in output.issues)
    assert base_context.records[0]["media_match_status"] == "incomplete"
    assert base_context.records[0]["processable"] is False


def test_node_03_process_duplicate_media_name_is_error(monkeypatch, base_context):
    """媒体库出现同名记录时生成error，不自动选择其中一条。"""
    monkeypatch.setattr(
        "workflows.nodes.node_03_match_media.ExcelService.read_sheet_as_dicts",
        lambda _: [
            {"媒体名称": "测试媒体", "媒体级别": "FA", "粉丝量": "20w"},
            {"媒体名称": "测试媒体", "媒体级别": "FB", "粉丝量": "10w"},
        ],
    )

    output = Node03MatchMedia().process(base_context)

    assert output.metrics.error_count == 1
    assert any(issue.level == "error" and issue.code == "DUPLICATE_MEDIA_NAME" for issue in output.issues)
    assert "媒体等级" not in base_context.records[0]
    assert base_context.records[0]["media_match_status"] == "pending_confirmation"
    assert base_context.records[0]["processable"] is False


def test_node_04_account_field_mapping():
    """测试账户信息列名映射（真实表头：户名/银行卡账号/开户行信息）"""
    node = Node04MatchAccount()
    node._account_data = [
        {
            "媒体": "Oxygen",
            "户名": "徐浩轩",
            "银行卡账号": "6217921478762521",
            "电话": "18837128611",
            "开户行信息（具体到支行）": "浦发郑州经三路支行",
            "开户行所在城市": "郑州",
        },
    ]

    matched = node._match_account_info("Oxygen")
    assert matched is not None
    # 关键：能取到户名、账号、开户行
    assert matched.get("户名") == "徐浩轩"
    assert matched.get("银行卡账号") == "6217921478762521"
    assert matched.get("开户行信息（具体到支行）") == "浦发郑州经三路支行"


def test_node_04_process_success(monkeypatch, base_context):
    """账户匹配成功时补齐所有输出字段。"""
    monkeypatch.setattr(
        "workflows.nodes.node_04_match_account.ExcelService.read_sheet_as_dicts",
        lambda _: [{
            "媒体": "测试媒体",
            "户名": "测试用户",
            "身份证号": "110101199001011234",
            "银行卡账号": "6222000000000000",
            "电话": "13800000000",
            "开户行信息（具体到支行）": "测试银行北京支行",
            "开户行所在城市": "北京",
        }],
    )

    output = Node04MatchAccount().process(base_context)

    assert output.metrics.success_count == 1
    assert output.metrics.error_count == 0
    assert base_context.records[0]["收款方"] == "测试用户"
    assert base_context.records[0]["身份证"] == "110101199001011234"
    assert base_context.records[0]["开户行所在城市"] == "北京"
    assert base_context.records[0]["account_match_status"] == "matched"
    assert base_context.records[0]["processable"] is True


def test_node_04_skips_unprocessable_record(monkeypatch, base_context):
    """节点3未通过的记录不得进入账户匹配。"""
    base_context.records[0]["processable"] = False
    monkeypatch.setattr(
        "workflows.nodes.node_04_match_account.ExcelService.read_sheet_as_dicts",
        lambda _: [],
    )

    output = Node04MatchAccount().process(base_context)

    assert output.metrics.success_count == 0
    assert output.metrics.error_count == 0
    assert output.issues == []
    assert base_context.records[0]["account_match_status"] == "skipped"


def test_node_04_account_not_found_is_error(monkeypatch, base_context):
    """账户信息无法匹配时生成error并阻止后续处理。"""
    monkeypatch.setattr(
        "workflows.nodes.node_04_match_account.ExcelService.read_sheet_as_dicts",
        lambda _: [{"媒体": "另一个媒体"}],
    )

    output = Node04MatchAccount().process(base_context)

    assert output.metrics.error_count == 1
    assert any(issue.level == "error" and issue.code == "ACCOUNT_NOT_FOUND" for issue in output.issues)
    assert base_context.records[0]["account_match_status"] == "not_found"
    assert base_context.records[0]["processable"] is False


def test_node_04_missing_required_field_is_error(monkeypatch, base_context):
    """任一账户必填字段为空时生成error。"""
    monkeypatch.setattr(
        "workflows.nodes.node_04_match_account.ExcelService.read_sheet_as_dicts",
        lambda _: [{
            "媒体": "测试媒体",
            "户名": "测试用户",
            "身份证号": None,
            "银行卡账号": "6222000000000000",
            "电话": "13800000000",
            "开户行信息（具体到支行）": "测试银行北京支行",
            "开户行所在城市": "北京",
        }],
    )

    output = Node04MatchAccount().process(base_context)

    assert output.metrics.error_count == 1
    issue = next(issue for issue in output.issues if issue.code == "MISSING_ACCOUNT_FIELDS")
    assert issue.level == "error"
    assert issue.details["missing_fields"] == ["身份证"]
    assert base_context.records[0]["account_match_status"] == "incomplete"
    assert base_context.records[0]["processable"] is False


def test_node_04_duplicate_media_is_error(monkeypatch, base_context):
    """账户信息表中媒体重名时不得自动选择账户。"""
    monkeypatch.setattr(
        "workflows.nodes.node_04_match_account.ExcelService.read_sheet_as_dicts",
        lambda _: [
            {"媒体": "测试媒体", "户名": "用户A"},
            {"媒体": "测试媒体", "户名": "用户B"},
        ],
    )

    output = Node04MatchAccount().process(base_context)

    assert output.metrics.error_count == 1
    assert any(issue.level == "error" and issue.code == "DUPLICATE_ACCOUNT_MEDIA" for issue in output.issues)
    assert base_context.records[0]["account_match_status"] == "duplicate"
    assert base_context.records[0]["processable"] is False


def test_node_05_calculate_fee_by_type():
    """测试费用计算按文章类型分列（真实表头：等级/视频费用/图文费用）"""
    node = Node05CalculateFee()
    node._fee_rules = [
        {"等级": "FA", "视频费用": 2000, "图文费用": 1000},
        {"等级": "FB", "视频费用": 1800, "图文费用": 800},
        {"等级": "FC", "视频费用": 1500, "图文费用": 600},
    ]

    # 视频类型取视频费用列
    assert node._calculate_fee("FA", "视频") == 2000.0
    assert node._calculate_fee("FB", "视频") == 1800.0
    # 图文类型取图文费用列
    assert node._calculate_fee("FA", "图文") == 1000.0
    assert node._calculate_fee("FC", "图文") == 600.0
    # 未知等级
    assert node._calculate_fee("ZZ", "图文") is None
