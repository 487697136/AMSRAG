"""
置信度校准训练模块

实现温度缩放校准，将ECE降至4%以下
"""

import os
import json
import torch
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
import logging
from sklearn.metrics import brier_score_loss
import matplotlib.pyplot as plt
import seaborn as sns

logger = logging.getLogger(__name__)


class CalibrationTrainer:
    """
    置信度校准训练器
    
    实现温度缩放以降低ECE（期望校准误差）
    """
    
    def __init__(self, model_path: str):
        """
        初始化校准训练器
        
        Args:
            model_path: 已训练模型的路径
        """
        self.model_path = model_path
        self.temperature = 1.5  # 初始温度
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        # 加载模型
        self._load_model()
    
    def _load_model(self):
        """加载预训练模型"""
        try:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
            
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_path)
            self.model = AutoModelForSequenceClassification.from_pretrained(self.model_path)
            self.model.to(self.device)
            self.model.eval()
            
            logger.info(f"成功加载模型: {self.model_path}")
        except Exception as e:
            logger.error(f"加载模型失败: {e}")
            raise
    
    def get_logits_and_labels(self, dataset) -> Tuple[np.ndarray, np.ndarray]:
        """
        获取模型的logits和真实标签
        
        Args:
            dataset: 数据集
            
        Returns:
            (logits, labels)
        """
        all_logits = []
        all_labels = []
        
        self.model.eval()
        with torch.no_grad():
            for batch in dataset:
                inputs = {
                    'input_ids': batch['input_ids'].to(self.device),
                    'attention_mask': batch['attention_mask'].to(self.device)
                }
                
                outputs = self.model(**inputs)
                logits = outputs.logits.cpu().numpy()
                labels = batch['labels'].numpy()
                
                all_logits.append(logits)
                all_labels.append(labels)
        
        return np.vstack(all_logits), np.concatenate(all_labels)
    
    def temperature_scale(self, logits: np.ndarray, temperature: float) -> np.ndarray:
        """
        应用温度缩放
        
        Args:
            logits: 原始logits
            temperature: 温度参数
            
        Returns:
            缩放后的概率
        """
        scaled_logits = logits / temperature
        # Softmax
        exp_logits = np.exp(scaled_logits - np.max(scaled_logits, axis=1, keepdims=True))
        probabilities = exp_logits / np.sum(exp_logits, axis=1, keepdims=True)
        return probabilities
    
    def compute_ece(self, 
                   probabilities: np.ndarray, 
                   labels: np.ndarray, 
                   n_bins: int = 15) -> float:
        """
        计算期望校准误差（ECE）
        
        Args:
            probabilities: 预测概率
            labels: 真实标签
            n_bins: 分箱数量
            
        Returns:
            ECE值
        """
        # 获取最大概率（置信度）和预测标签
        confidences = np.max(probabilities, axis=1)
        predictions = np.argmax(probabilities, axis=1)
        accuracies = (predictions == labels).astype(float)
        
        # 创建分箱
        bin_boundaries = np.linspace(0, 1, n_bins + 1)
        ece = 0.0
        
        for i in range(n_bins):
            bin_lower = bin_boundaries[i]
            bin_upper = bin_boundaries[i + 1]
            
            # 找到落在当前箱中的样本
            in_bin = (confidences > bin_lower) & (confidences <= bin_upper)
            
            if np.sum(in_bin) > 0:
                # 计算箱内平均置信度和准确率
                avg_confidence = np.mean(confidences[in_bin])
                avg_accuracy = np.mean(accuracies[in_bin])
                
                # 累加ECE
                ece += np.sum(in_bin) * np.abs(avg_confidence - avg_accuracy) / len(confidences)
        
        return ece
    
    def optimize_temperature(self, 
                           logits: np.ndarray, 
                           labels: np.ndarray,
                           lr: float = 0.01,
                           max_iter: int = 50,
                           patience: int = 5) -> float:
        """
        优化温度参数以最小化ECE
        
        Args:
            logits: 验证集logits
            labels: 验证集标签
            lr: 学习率
            max_iter: 最大迭代次数
            patience: 早停耐心值
            
        Returns:
            最优温度
        """
        best_temperature = self.temperature
        best_ece = float('inf')
        patience_counter = 0
        
        temperatures = []
        eces = []
        
        # 网格搜索 + 精细调整
        for temp in np.arange(0.5, 3.0, 0.1):
            probs = self.temperature_scale(logits, temp)
            ece = self.compute_ece(probs, labels)
            
            temperatures.append(temp)
            eces.append(ece)
            
            if ece < best_ece:
                best_ece = ece
                best_temperature = temp
                patience_counter = 0
            else:
                patience_counter += 1
            
            if patience_counter >= patience:
                break
        
        logger.info(f"最优温度: {best_temperature:.3f}, ECE: {best_ece:.4f}")
        
        # 绘制温度-ECE曲线
        self._plot_temperature_curve(temperatures, eces, best_temperature)
        
        return best_temperature
    
    def _plot_temperature_curve(self, temperatures, eces, best_temp):
        """绘制温度-ECE曲线"""
        plt.figure(figsize=(8, 6))
        plt.plot(temperatures, eces, 'b-', linewidth=2)
        plt.scatter([best_temp], [min(eces)], color='red', s=100, zorder=5)
        plt.xlabel('Temperature', fontsize=12)
        plt.ylabel('ECE', fontsize=12)
        plt.title('Temperature vs ECE', fontsize=14)
        plt.grid(True, alpha=0.3)
        
        # 添加最优点标注
        plt.annotate(f'Best: T={best_temp:.2f}, ECE={min(eces):.4f}',
                    xy=(best_temp, min(eces)),
                    xytext=(best_temp+0.3, min(eces)+0.01),
                    arrowprops=dict(arrowstyle='->', color='red'))
        
        save_path = Path(self.model_path) / "temperature_ece_curve.png"
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        logger.info(f"温度曲线已保存到: {save_path}")
    
    def plot_reliability_diagram(self, 
                               probabilities: np.ndarray,
                               labels: np.ndarray,
                               n_bins: int = 15,
                               title_suffix: str = ""):
        """
        绘制可靠性图
        
        Args:
            probabilities: 预测概率
            labels: 真实标签
            n_bins: 分箱数量
            title_suffix: 标题后缀
        """
        # 获取置信度和准确性
        confidences = np.max(probabilities, axis=1)
        predictions = np.argmax(probabilities, axis=1)
        accuracies = (predictions == labels).astype(float)
        
        # 创建分箱
        bin_boundaries = np.linspace(0, 1, n_bins + 1)
        bin_centers = (bin_boundaries[:-1] + bin_boundaries[1:]) / 2
        
        avg_accuracies = []
        avg_confidences = []
        bin_counts = []
        
        for i in range(n_bins):
            bin_lower = bin_boundaries[i]
            bin_upper = bin_boundaries[i + 1]
            in_bin = (confidences > bin_lower) & (confidences <= bin_upper)
            
            if np.sum(in_bin) > 0:
                avg_accuracies.append(np.mean(accuracies[in_bin]))
                avg_confidences.append(np.mean(confidences[in_bin]))
                bin_counts.append(np.sum(in_bin))
            else:
                avg_accuracies.append(0)
                avg_confidences.append(bin_centers[i])
                bin_counts.append(0)
        
        # 绘图
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
        
        # 可靠性图
        ax1.plot([0, 1], [0, 1], 'k--', label='Perfect calibration')
        ax1.bar(avg_confidences, avg_accuracies, width=1/n_bins, alpha=0.7, 
                edgecolor='black', label='Actual')
        ax1.set_xlabel('Confidence', fontsize=12)
        ax1.set_ylabel('Accuracy', fontsize=12)
        ax1.set_title(f'Reliability Diagram {title_suffix}', fontsize=14)
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # 直方图
        ax2.bar(bin_centers, bin_counts, width=1/n_bins, alpha=0.7, edgecolor='black')
        ax2.set_xlabel('Confidence', fontsize=12)
        ax2.set_ylabel('Count', fontsize=12)
        ax2.set_title('Confidence Distribution', fontsize=14)
        ax2.grid(True, alpha=0.3)
        
        save_path = Path(self.model_path) / f"reliability_diagram{title_suffix.replace(' ', '_')}.png"
        plt.tight_layout()
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        logger.info(f"可靠性图已保存到: {save_path}")
    
    def calibrate(self, val_dataset) -> Dict[str, Any]:
        """
        执行校准
        
        Args:
            val_dataset: 验证数据集
            
        Returns:
            校准结果
        """
        logger.info("开始置信度校准...")
        
        # 获取logits和标签
        logits, labels = self.get_logits_and_labels(val_dataset)
        
        # 计算原始ECE
        original_probs = self.temperature_scale(logits, 1.0)
        original_ece = self.compute_ece(original_probs, labels)
        logger.info(f"原始ECE: {original_ece:.4f}")
        
        # 优化温度
        optimal_temperature = self.optimize_temperature(logits, labels)
        
        # 计算校准后的ECE
        calibrated_probs = self.temperature_scale(logits, optimal_temperature)
        calibrated_ece = self.compute_ece(calibrated_probs, labels)
        logger.info(f"校准后ECE: {calibrated_ece:.4f}")
        
        # 绘制可靠性图
        self.plot_reliability_diagram(original_probs, labels, title_suffix="(Before Calibration)")
        self.plot_reliability_diagram(calibrated_probs, labels, title_suffix="(After Calibration)")
        
        # 计算其他指标
        results = {
            'original_ece': float(original_ece),
            'calibrated_ece': float(calibrated_ece),
            'optimal_temperature': float(optimal_temperature),
            'ece_reduction': float(original_ece - calibrated_ece),
            'ece_reduction_percentage': float((original_ece - calibrated_ece) / original_ece * 100)
        }
        
        # 保存校准参数
        calibration_params = {
            'temperature': optimal_temperature,
            'calibration_stats': results
        }
        
        params_path = Path(self.model_path) / "calibration_params.json"
        with open(params_path, 'w', encoding='utf-8') as f:
            json.dump(calibration_params, f, ensure_ascii=False, indent=2)
        
        logger.info(f"校准参数已保存到: {params_path}")
        logger.info(f"ECE降低: {results['ece_reduction']:.4f} ({results['ece_reduction_percentage']:.1f}%)")
        
        return results


async def calibrate_classifier(
    model_path: str,
    val_data_path: str,
    batch_size: int = 32
) -> Dict[str, Any]:
    """
    校准复杂度分类器
    
    Args:
        model_path: 模型路径
        val_data_path: 验证数据路径
        batch_size: 批次大小
        
    Returns:
        校准结果
    """
    from .train_classifier import ComplexityDataset
    from transformers import AutoTokenizer
    import torch
    
    # 创建校准器
    calibrator = CalibrationTrainer(model_path)
    
    # 加载验证数据
    with open(val_data_path, 'r', encoding='utf-8') as f:
        val_data = json.load(f)
    
    # 准备数据
    queries = [item['query'] for item in val_data]
    label_map = {"zero_hop": 0, "one_hop": 1, "multi_hop": 2}
    labels = [label_map[item['complexity']] for item in val_data]
    
    # 创建数据集
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    val_dataset = ComplexityDataset(queries, labels, tokenizer)
    
    # 创建数据加载器
    val_loader = torch.utils.data.DataLoader(
        val_dataset,
        batch_size=batch_size,
        shuffle=False
    )
    
    # 执行校准
    results = calibrator.calibrate(val_loader)
    
    logger.info("校准完成！")
    return results

