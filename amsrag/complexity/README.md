# 查询复杂度感知与路由模块

本模块实现了论文《查询复杂度感知与置信度融合的多源检索增强生成框架》中描述的复杂度分类和自适应路由功能。

## 核心组件

### 1. 复杂度分类器 (`classifier.py`)

基于ModernBERT的三类查询复杂度分类器：

```python
from amsrag.complexity import ComplexityClassifier

classifier = ComplexityClassifier()
complexity, confidence, probabilities = classifier.predict_with_confidence("你的查询")

# 输出示例：
# complexity: "zero_hop" | "one_hop" | "multi_hop"
# confidence: 0.85 (校准后的置信度)
# probabilities: {"zero_hop": 0.1, "one_hop": 0.15, "multi_hop": 0.75}
```

**论文要求的性能指标**：
- 准确率: 85.9%
- Macro-F1: 85.4%
- 校准后ECE: 4.0%

### 2. 置信度校准器 (`calibrator.py`)

实现温度缩放（Temperature Scaling）以降低ECE：

```python
from amsrag.complexity.calibrator import ConfidenceCalibrator

calibrator = ConfidenceCalibrator(temperature=1.5)
calibrated_confidence = calibrator.calibrate_confidence(
    raw_confidence=0.9,
    logits=model_logits
)
```

**校准公式**：
```
scaled_logits = logits / temperature
probabilities = softmax(scaled_logits)
```

### 3. 复杂度感知路由器 (`router.py`)

根据复杂度和置信度实现三层渐进式检索策略：

```python
from amsrag.complexity import ComplexityAwareRouter

router = ComplexityAwareRouter()
complexity_result = await router.predict_complexity_detailed(query)
retrieval_plan = router.get_retrieval_plan(complexity_result)

# 渐进式策略：
# 策略A (confidence >= 0.9): 单路径 - ["llm_only"] 或 ["naive"]
# 策略B (0.6 <= confidence < 0.9): 双路径 - ["naive", "bm25"]
# 策略C (confidence < 0.6): 多路径 - ["naive", "bm25", "local/global"]
```

## 渐进式检索策略

### 策略A：高置信度单路径 (θ ≥ 0.9)

- **适用场景**：明确的零跳或单跳查询
- **检索方案**：
  - Zero-hop: 直接LLM回答（`llm_only`）
  - One-hop: 单一最优检索器（`naive`）
  - Multi-hop: 图检索（`local`）
- **特点**：快速响应，降低开销

### 策略B：中等置信度双路径 (0.6 ≤ θ < 0.9)

- **适用场景**：存在一定不确定性的查询
- **检索方案**：互补的两类检索器
  - 向量 + 关键词：`["naive", "bm25"]`
  - 向量 + 图：`["naive", "local"]`
  - 关键词 + 图：`["bm25", "local"]`
- **特点**：平衡质量与效率，确保互补性

### 策略C：低置信度多路径 (θ < 0.6)

- **适用场景**：复杂查询或高度不确定查询
- **检索方案**：多源冗余检索
  - 基础三路径：`["naive", "bm25", "local"]`
  - 触发Global条件下：`["naive", "bm25", "global"]`
- **特点**：最大化证据覆盖

### Global检索触发条件

1. 明确的多跳查询（`complexity == "multi_hop"` and `confidence > 0.5`）
2. 多跳概率高（`multi_hop_prob > 0.4` and `confidence < 0.7`）
3. 高熵低置信度（概率分布平坦）
4. 包含全局性关键词（"总体"、"比较"、"关系"等）
5. 单跳/多跳边界情况

## 训练模块 (`training/`)

### 数据生成器 (`data_generator.py`)

```python
from amsrag.complexity.training import generate_training_data

# 从MS MARCO和HotpotQA生成标注数据
await generate_training_data(
    msmarco_path="path/to/msmarco.jsonl",
    hotpotqa_path="path/to/hotpotqa.json",
    output_path="training_data.json",
    llm_func=your_llm_function
)
```

### 模型训练 (`train_classifier.py`)

```python
from amsrag.complexity.training import train_classifier, TrainingConfig

config = TrainingConfig(
    model_name="answerdotai/ModernBERT-large",
    batch_size=16,
    learning_rate=2e-5,
    num_epochs=3
)

results = await train_classifier(
    data_path="training_data.json",
    config=config
)
```

### 置信度校准 (`calibration_trainer.py`)

```python
from amsrag.complexity.training import calibrate_classifier

calibration_results = await calibrate_classifier(
    model_path="path/to/trained_model",
    val_data_path="validation_data.json"
)

# 输出：
# - optimal_temperature: 最优温度参数
# - original_ece: 校准前ECE
# - calibrated_ece: 校准后ECE
# - 可靠性图表
```

## 使用示例

### 基础使用

```python
from amsrag import EnhancedGraphRAG
from amsrag.complexity import ComplexityAwareRouter

# 创建带复杂度路由的RAG系统
rag = EnhancedGraphRAG(
    enable_enhanced_features=True,
    enable_confidence_fusion=True
)

# 查询会自动使用复杂度路由
response = await rag.aquery("查询问题")
```

### 手动路由

```python
router = ComplexityAwareRouter()

# 预测复杂度
complexity_result = await router.predict_complexity_detailed(query)
print(f"复杂度: {complexity_result['complexity']}")
print(f"置信度: {complexity_result['confidence']:.3f}")

# 获取检索计划
retrieval_plan = router.get_retrieval_plan(complexity_result)
print(f"检索计划: {retrieval_plan}")
```

## 性能优化建议

1. **模型加载**：首次加载ModernBERT模型需要一定时间，建议缓存模型实例
2. **批量预测**：对于大量查询，可以批量处理以提高吞吐量
3. **GPU加速**：复杂度分类支持CUDA加速，设置`device="cuda"`
4. **校准参数**：使用预训练的校准参数可以跳过校准步骤

## 论文对应关系

| 论文章节 | 实现模块 | 核心功能 |
|---------|---------|---------|
| 3.1 查询复杂度建模 | `classifier.py` | ModernBERT分类 |
| 3.1 置信度估计 | `calibrator.py` | 温度缩放校准 |
| 3.2 渐进式检索 | `router.py` | 三层策略选择 |
| 公式 (2) | `router.py` L296-304 | S(α,c)函数 |

## 参考文献

论文：查询复杂度感知与置信度融合的多源检索增强生成框架
模型：ModernBERT (Warner et al., 2024)
校准方法：Temperature Scaling (Guo et al., 2017)

