# 迁移计划 - LangGraph → LangChain

## 📋 迁移策略

采用**渐进式迁移**，新旧并存，验证后切换：

1. ✅ **Phase 1**: 创建新架构文件（`*_new.py`）
2. ⏳ **Phase 2**: 实现剩余节点（2-6）
3. ⏳ **Phase 3**: 端到端测试
4. ⏳ **Phase 4**: 切换默认入口
5. ⏳ **Phase 5**: 删除旧代码

## 📂 文件对照表

| 旧文件 | 新文件 | 状态 |
|--------|--------|------|
| `models.py` | `models_new.py` | ✅ 完成 |
| `nodes/base.py` | `nodes/base_new.py` | ✅ 完成 |
| `nodes/node_00_input.py` | `nodes/node_00_input_new.py` | ✅ 完成 |
| `nodes/node_01_fill_basic.py` | `nodes/node_01_fill_basic_new.py` | ✅ 完成 |
| `graph.py` | `workflow_new.py` | ✅ 完成 |
| `__main__.py` | `__main___new.py` | ✅ 完成 |
| `mcp_server.py` | `mcp_server_new.py` | ⏳ 待实现 |
| `runtime/workflow_runtime.py` | `runtime_new.py` | ⏳ 待实现 |
| - | `nodes/node_02_fill_publication_new.py` | ⏳ 待实现 |
| - | `nodes/node_03_match_media_new.py` | ⏳ 待实现 |
| - | `nodes/node_04_match_account_new.py` | ⏳ 待实现 |
| - | `nodes/node_05_calculate_fee_new.py` | ⏳ 待实现 |
| - | `nodes/node_06_generate_payment_new.py` | ⏳ 待实现 |

## 🧪 测试对照表

| 旧测试 | 新测试 | 状态 |
|--------|--------|------|
| `test_basic.py` | `test_new_architecture.py` | ✅ 完成（14个测试） |
| `test_conditional_routing.py` | - | ⏳ 不需要（逻辑简化） |
| - | `test_end_to_end_new.py` | ⏳ 待实现 |

## 🚀 Phase 2: 实现剩余节点

### 节点2: 完善发布信息
```python
class Node02FillPublication(BaseNode):
    """提取标题、日期、类型、截图"""
    
    def process(self, context: WorkflowContext) -> NodeOutput:
        # 从 context.records 读取
        # 提取发布信息
        # 更新 context.records
        pass
```

### 节点3: 匹配媒体库
```python
class Node03MatchMedia(BaseNode):
    """补充媒体级别、粉丝量"""
    
    def process(self, context: WorkflowContext) -> NodeOutput:
        # 读取 3-媒体库.xlsx
        # 匹配媒体名称
        # 补充级别和粉丝量
        pass
```

### 节点4: 匹配账户信息
```python
class Node04MatchAccount(BaseNode):
    """补充收款信息"""
    
    def process(self, context: WorkflowContext) -> NodeOutput:
        # 读取 4-账户信息.xlsx
        # 匹配账户
        # 补充收款信息
        pass
```

### 节点5: 计算费用
```python
class Node05CalculateFee(BaseNode):
    """匹配费用规则，生成明细"""
    
    def process(self, context: WorkflowContext) -> NodeOutput:
        # 读取 5-费用.xlsx
        # 匹配规则
        # 计算金额
        # 生成约稿明细表
        pass
```

### 节点6: 生成付款表
```python
class Node06GeneratePayment(BaseNode):
    """月度汇总，输出Excel"""
    
    def process(self, context: WorkflowContext) -> NodeOutput:
        # 按月汇总
        # 生成付款表
        # 写入 Excel
        pass
```

## 🧪 Phase 3: 端到端测试

```python
# tests/test_end_to_end_new.py

def test_full_workflow_with_real_data():
    """使用真实数据测试完整流程"""
    context = run_workflow(
        input_file="./table/1-链接.xlsx",
        table_dir="./table"
    )
    
    assert len(context.records) > 0
    assert context.quote_details is not None
    assert context.monthly_summary is not None
    assert context.payment_rows is not None
    assert len(context.completed_nodes) == 7
```

## 🔄 Phase 4: 切换默认入口

```bash
# 1. 重命名文件
mv src/workflow/__main__.py src/workflow/__main___old.py
mv src/workflow/__main___new.py src/workflow/__main__.py

# 2. 更新 pyproject.toml
[project.scripts]
workflow = "workflow.__main__:main"  # 指向新入口

# 3. 测试
workflow run --input ./table/1-链接.xlsx
```

## 🗑️ Phase 5: 清理旧代码

在新架构稳定运行 **1周** 后：

```bash
# 删除旧文件
rm src/workflow/models.py
rm src/workflow/graph.py
rm src/workflow/nodes/base.py
rm src/workflow/nodes/node_00_input.py
rm src/workflow/nodes/node_01_fill_basic.py
rm src/workflow/__main___old.py
rm tests/test_basic.py
rm tests/test_conditional_routing.py

# 重命名新文件（去掉 _new 后缀）
# 这一步可选，也可以保持 _new 以示区分
```

## ⚠️ 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 新架构有未知bug | 中 | 新旧并存，充分测试 |
| 迁移过程中代码混乱 | 低 | 命名清晰（`*_new.py`） |
| 旧代码仍被引用 | 中 | 搜索代码库，检查引用 |
| 性能回退 | 低 | 基准测试对比 |

## 📊 迁移进度追踪

### 当前进度：35% (7/20)

- [x] 新架构设计
- [x] 核心模型（WorkflowContext, Issue, NodeOutput）
- [x] 节点基类（BaseNode）
- [x] 节点0（输入验证）
- [x] 节点1（填写基础信息）
- [x] 工作流定义（workflow_new.py）
- [x] 测试套件（14个测试）
- [ ] 节点2（完善发布信息）
- [ ] 节点3（匹配媒体库）
- [ ] 节点4（匹配账户信息）
- [ ] 节点5（计算费用）
- [ ] 节点6（生成付款表）
- [ ] 命令行入口集成
- [ ] MCP服务器适配
- [ ] 端到端测试
- [ ] 生产环境验证
- [ ] 性能测试
- [ ] 文档更新
- [ ] 删除旧代码
- [ ] 发布新版本

## 🎯 下一步行动

**立即执行**（按优先级）：

1. **实现节点2**: `node_02_fill_publication_new.py`
   - 提取标题、日期、类型
   - 估计时间：2小时

2. **实现节点3**: `node_03_match_media_new.py`
   - 匹配媒体库
   - 估计时间：1.5小时

3. **实现节点4**: `node_04_match_account_new.py`
   - 匹配账户信息
   - 估计时间：1小时

4. **实现节点5**: `node_05_calculate_fee_new.py`
   - 计算费用
   - 估计时间：2小时

5. **实现节点6**: `node_06_generate_payment_new.py`
   - 生成付款表
   - 估计时间：1.5小时

**总估计时间**: 8小时

## 📝 检查清单

在每个节点完成后检查：

- [ ] 实现了 `process()` 方法
- [ ] 正确读取和更新 `context`
- [ ] 添加了适当的 `Issue`
- [ ] 计算了 `metrics`
- [ ] 编写了单元测试
- [ ] 更新了工作流链

在迁移完成后检查：

- [ ] 所有测试通过
- [ ] 端到端测试通过
- [ ] 文档更新
- [ ] 命令行工具正常工作
- [ ] MCP服务器正常工作
- [ ] 性能无明显下降
- [ ] 旧代码引用已清理

---

**维护者**: 请在完成每个阶段后更新此文档。
