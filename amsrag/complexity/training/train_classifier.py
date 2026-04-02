"""
复杂度分类器训练模块

提供ModernBERT模型的微调训练功能
"""

import os
import json
import torch
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
import logging
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, classification_report, confusion_matrix

logger = logging.getLogger(__name__)

# 检查依赖
TRANSFORMERS_AVAILABLE = False
try:
    from transformers import (
        AutoTokenizer, 
        AutoModelForSequenceClassification,
        TrainingArguments,
        Trainer,
        EarlyStoppingCallback
    )
    from peft import LoraConfig, get_peft_model, TaskType
    import evaluate
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    logger.warning("transformers或peft未安装，训练功能不可用")


@dataclass
class TrainingConfig:
    """训练配置"""
    model_name: str = "answerdotai/ModernBERT-large"
    output_dir: str = "amsrag/models/modernbert_complexity_classifier_standard"
    max_length: int = 256
    batch_size: int = 16
    learning_rate: float = 2e-5
    num_epochs: int = 3
    warmup_ratio: float = 0.1
    weight_decay: float = 0.01
    
    # LoRA配置
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.1
    
    # 早停配置
    early_stopping_patience: int = 3
    early_stopping_threshold: float = 0.001
    
    # 评估配置
    eval_steps: int = 100
    save_steps: int = 200
    logging_steps: int = 50
    
    # 数据配置
    train_size: float = 0.7
    val_size: float = 0.15
    test_size: float = 0.15
    random_seed: int = 42


class ComplexityDataset(torch.utils.data.Dataset):
    """复杂度分类数据集"""
    
    def __init__(self, 
                 queries: List[str], 
                 labels: List[int], 
                 tokenizer, 
                 max_length: int = 256):
        self.queries = queries
        self.labels = labels
        self.tokenizer = tokenizer
        self.max_length = max_length
    
    def __len__(self):
        return len(self.queries)
    
    def __getitem__(self, idx):
        query = self.queries[idx]
        label = self.labels[idx]
        
        # 编码文本
        encoding = self.tokenizer(
            query,
            truncation=True,
            padding='max_length',
            max_length=self.max_length,
            return_tensors='pt'
        )
        
        return {
            'input_ids': encoding['input_ids'].flatten(),
            'attention_mask': encoding['attention_mask'].flatten(),
            'labels': torch.tensor(label, dtype=torch.long)
        }


class ComplexityTrainer:
    """复杂度分类器训练器"""
    
    def __init__(self, config: TrainingConfig = None):
        """
        初始化训练器
        
        Args:
            config: 训练配置
        """
        self.config = config or TrainingConfig()
        
        if not TRANSFORMERS_AVAILABLE:
            raise ImportError("需要安装transformers和peft库")
        
        # 标签映射
        self.label2id = {
            "zero_hop": 0,
            "one_hop": 1,
            "multi_hop": 2
        }
        self.id2label = {v: k for k, v in self.label2id.items()}
        
        # 设置设备
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        logger.info(f"使用设备: {self.device}")
    
    def load_data(self, data_path: str) -> Tuple[List[str], List[int]]:
        """
        加载训练数据
        
        Args:
            data_path: 数据文件路径
            
        Returns:
            (查询列表, 标签列表)
        """
        with open(data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        queries = []
        labels = []
        
        for item in data:
            queries.append(item['query'])
            labels.append(self.label2id[item['complexity']])
        
        logger.info(f"加载了 {len(queries)} 条数据")
        return queries, labels
    
    def split_data(self, queries: List[str], labels: List[int]) -> Dict[str, Any]:
        """
        划分数据集
        
        Args:
            queries: 查询列表
            labels: 标签列表
            
        Returns:
            包含训练、验证、测试集的字典
        """
        # 先分出测试集
        X_temp, X_test, y_temp, y_test = train_test_split(
            queries, labels, 
            test_size=self.config.test_size, 
            random_state=self.config.random_seed,
            stratify=labels
        )
        
        # 再分出验证集
        val_ratio = self.config.val_size / (1 - self.config.test_size)
        X_train, X_val, y_train, y_val = train_test_split(
            X_temp, y_temp,
            test_size=val_ratio,
            random_state=self.config.random_seed,
            stratify=y_temp
        )
        
        logger.info(f"数据集划分:")
        logger.info(f"  训练集: {len(X_train)}")
        logger.info(f"  验证集: {len(X_val)}")
        logger.info(f"  测试集: {len(X_test)}")
        
        return {
            'train': (X_train, y_train),
            'val': (X_val, y_val),
            'test': (X_test, y_test)
        }
    
    def prepare_model(self):
        """准备模型和分词器"""
        logger.info(f"加载模型: {self.config.model_name}")
        
        # 加载分词器
        self.tokenizer = AutoTokenizer.from_pretrained(self.config.model_name)
        
        # 加载基础模型
        self.model = AutoModelForSequenceClassification.from_pretrained(
            self.config.model_name,
            num_labels=len(self.label2id),
            id2label=self.id2label,
            label2id=self.label2id
        )
        
        # 配置LoRA
        peft_config = LoraConfig(
            task_type=TaskType.SEQ_CLS,
            r=self.config.lora_r,
            lora_alpha=self.config.lora_alpha,
            lora_dropout=self.config.lora_dropout,
            bias="none",
            target_modules=["q_proj", "v_proj"]  # ModernBERT的注意力层
        )
        
        # 应用LoRA
        self.model = get_peft_model(self.model, peft_config)
        self.model.print_trainable_parameters()
        
        # 移动到设备
        self.model.to(self.device)
    
    def compute_metrics(self, eval_pred):
        """计算评估指标"""
        predictions, labels = eval_pred
        predictions = np.argmax(predictions, axis=1)
        
        # 计算各项指标
        accuracy = accuracy_score(labels, predictions)
        f1_macro = f1_score(labels, predictions, average='macro')
        f1_weighted = f1_score(labels, predictions, average='weighted')
        
        return {
            'accuracy': accuracy,
            'f1_macro': f1_macro,
            'f1_weighted': f1_weighted
        }
    
    def train(self, train_dataset, val_dataset):
        """执行训练"""
        # 训练参数
        training_args = TrainingArguments(
            output_dir=self.config.output_dir,
            num_train_epochs=self.config.num_epochs,
            per_device_train_batch_size=self.config.batch_size,
            per_device_eval_batch_size=self.config.batch_size,
            warmup_ratio=self.config.warmup_ratio,
            weight_decay=self.config.weight_decay,
            logging_dir=f"{self.config.output_dir}/logs",
            logging_steps=self.config.logging_steps,
            evaluation_strategy="steps",
            eval_steps=self.config.eval_steps,
            save_strategy="steps",
            save_steps=self.config.save_steps,
            load_best_model_at_end=True,
            metric_for_best_model="f1_macro",
            greater_is_better=True,
            save_total_limit=3,
            report_to="none",  # 不使用wandb等
            fp16=torch.cuda.is_available(),  # 如果有GPU则使用混合精度
        )
        
        # 创建训练器
        trainer = Trainer(
            model=self.model,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=val_dataset,
            compute_metrics=self.compute_metrics,
            callbacks=[
                EarlyStoppingCallback(
                    early_stopping_patience=self.config.early_stopping_patience,
                    early_stopping_threshold=self.config.early_stopping_threshold
                )
            ]
        )
        
        # 开始训练
        logger.info("开始训练...")
        trainer.train()
        
        # 保存最佳模型
        logger.info(f"保存模型到: {self.config.output_dir}")
        trainer.save_model()
        self.tokenizer.save_pretrained(self.config.output_dir)
        
        return trainer
    
    def evaluate(self, test_dataset) -> Dict[str, Any]:
        """评估模型"""
        # 加载最佳模型进行评估
        from transformers import pipeline
        
        classifier = pipeline(
            "text-classification",
            model=self.config.output_dir,
            device=0 if torch.cuda.is_available() else -1
        )
        
        # 提取测试数据
        test_queries = [self.tokenizer.decode(test_dataset[i]['input_ids'], skip_special_tokens=True) 
                       for i in range(len(test_dataset))]
        test_labels = [test_dataset[i]['labels'].item() for i in range(len(test_dataset))]
        
        # 批量预测
        predictions = classifier(test_queries, batch_size=32)
        pred_labels = [self.label2id[p['label']] for p in predictions]
        
        # 计算指标
        accuracy = accuracy_score(test_labels, pred_labels)
        f1_macro = f1_score(test_labels, pred_labels, average='macro')
        f1_weighted = f1_score(test_labels, pred_labels, average='weighted')
        
        # 分类报告
        report = classification_report(
            test_labels, pred_labels,
            target_names=list(self.label2id.keys()),
            output_dict=True
        )
        
        # 混淆矩阵
        cm = confusion_matrix(test_labels, pred_labels)
        
        results = {
            'accuracy': accuracy,
            'f1_macro': f1_macro,
            'f1_weighted': f1_weighted,
            'classification_report': report,
            'confusion_matrix': cm.tolist()
        }
        
        # 保存评估结果
        results_path = Path(self.config.output_dir) / "evaluation_results.json"
        with open(results_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        logger.info(f"评估结果:")
        logger.info(f"  准确率: {accuracy:.4f}")
        logger.info(f"  Macro F1: {f1_macro:.4f}")
        logger.info(f"  Weighted F1: {f1_weighted:.4f}")
        
        return results


async def train_classifier(
    data_path: str,
    config: Optional[TrainingConfig] = None
) -> Dict[str, Any]:
    """
    训练复杂度分类器
    
    Args:
        data_path: 训练数据路径
        config: 训练配置
        
    Returns:
        训练和评估结果
    """
    trainer = ComplexityTrainer(config)
    
    # 加载数据
    queries, labels = trainer.load_data(data_path)
    
    # 划分数据集
    splits = trainer.split_data(queries, labels)
    
    # 准备模型
    trainer.prepare_model()
    
    # 创建数据集
    train_dataset = ComplexityDataset(
        *splits['train'], trainer.tokenizer, trainer.config.max_length
    )
    val_dataset = ComplexityDataset(
        *splits['val'], trainer.tokenizer, trainer.config.max_length
    )
    test_dataset = ComplexityDataset(
        *splits['test'], trainer.tokenizer, trainer.config.max_length
    )
    
    # 训练
    trainer.train(train_dataset, val_dataset)
    
    # 评估
    results = trainer.evaluate(test_dataset)
    
    logger.info("训练完成！")
    return results

