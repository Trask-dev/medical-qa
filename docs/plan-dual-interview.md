# 双通道问诊架构计划

> 日期: 2026-06-24 | 状态: ✅ 已完成

## 目标

将当前单一问诊节点拆分为基础/专家双通道，专家通道注入知识库上下文。

## 架构对比

```
Before:  safety_check → interview → response → END

After:   safety_check → route → basic_interview → response → END
                              → expert_interview → response → END
```

## 节点职责

| 节点 | 触发条件 | 行为 |
|------|---------|------|
| `basic_interview_node` | 默认 | 基于 prompt 模板生成选择题，和现在一样 |
| `expert_interview_node` | 路由判定为需要知识增强 | 先从知识库检索→注入 prompt →生成知识增强的选择题 |

## 执行步骤

### Step 1: 创建 expert_interview_node.py (20min)

```
workflow/nodes/
├── interview_node.py          → basic_interview_node.py (重命名)
└── expert_interview_node.py   ← 新文件
```

Expert node 核心差异：
- 每轮**同步**检索知识库（不依赖后台异步任务）
- 检索结果注入 prompt 模板：`prompts/expert_consultation.j2`
- 其余逻辑（选项生成、事实提取、终止判断）复用 basic 节点

### Step 2: 创建 expert prompt 模板 (10min)

`prompts/expert_consultation.j2`：
- 在 Block 3（采集任务）之后新增 **知识库参考** 区块
- 变量 `{{ knowledge_context }}` 注入检索到的知识片段
- 提醒 LLM 基于知识库内容设计选项

### Step 3: 路由逻辑 (10min)

`workflow/routes.py`：
```python
def route_interview_type(state) -> str:
    if state.get("use_expert"):
        return "expert_interview"
    return "basic_interview"
```

### Step 4: 更新 graph.py (5min)

```python
workflow.add_node("basic_interview", basic_interview_node)
workflow.add_node("expert_interview", expert_interview_node)
workflow.add_conditional_edges("safety_check", route_interview_type, {
    "basic_interview": "basic_interview",
    "expert_interview": "expert_interview",
})
```

### Step 5: 重命名 + 更新导入 (10min)

- `interview_node.py` → `basic_interview_node.py`
- 更新所有 `from workflow.nodes.interview_node import` 引用

### Step 6: 测试更新 (15min)

- 更新 `tests/conftest.py` MockL2Adapter 路径
- 更新 `tests/unit_nodes/test_interview.py` 导入

## 文件变更清单

| 操作 | 文件 |
|------|------|
| 新建 | `workflow/nodes/expert_interview_node.py` |
| 新建 | `prompts/expert_consultation.j2` |
| 重命名 | `interview_node.py` → `basic_interview_node.py` |
| 修改 | `workflow/routes.py` (+route_interview_type) |
| 修改 | `workflow/graph.py` (+expert节点) |
| 修改 | `api/routers/messages.py` (import路径) |
| 修改 | `tests/conftest.py` (mock路径) |
| 修改 | `tests/unit_nodes/test_interview.py` (import路径) |

## 预计工作量

总计 ~1.5h，7 个文件变更。
