"""
置信度校准模块
实现温度缩放(Temperature Scaling)以降低ECE至4%以下
"""

import numpy as np
import torch
import torch.nn as nn
import json
import os
from typing import Tuple, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class TemperatureScaling(nn.Module):
    """温度缩放校准器"""
    
    def __init__(self):
        super().__init__()
        self.temperature = nn.Parameter(torch.ones(1) * 1.5)
    
    def forward(self, logits):
        """应用温度缩放"""
        return logits / self.temperature
    
    def calibrate(self, logits, labels, lr=0.01, max_iter=50):
        """在验证集上学习最优温度参数"""
        optimizer = torch.optim.LBFGS([self.temperature], lr=lr, max_iter=max_iter)
        
        def eval():
            loss = nn.CrossEntropyLoss()(self.forward(logits), labels)
            loss.backward()
            return loss
        
        optimizer.step(eval)
        return self.temperature.item()


class ConfidenceCalibrator:
    """
    置信度校准器，实现温度缩放以降低ECE
    
    根据论文要求，将ECE从10.2%降至4.0%
    """
    
    def __init__(self, temperature: float = 1.5):
        """
        初始化校准器
        
        Args:
            temperature: 温度参数，默认1.5（基于实验结果）
        """
        self.temperature = temperature
        self.calibration_stats = {
            'pre_calibration_ece': None,
            'post_calibration_ece': None,
            'samples_calibrated': 0
        }
        
    def calibrate_confidence(self, 
                           raw_confidence: float, 
                           logits: Optional[np.ndarray] = None) -> float:
        """
        应用温度缩放校准置信度
        
        Args:
            raw_confidence: 原始置信度
            logits: 原始logits（可选）
            
        Returns:
            校准后的置信度
        """
        if logits is not None and len(logits) > 0:
            # 应用温度缩放到logits
            scaled_logits = logits / self.temperature
            # 重新计算softmax
            exp_logits = np.exp(scaled_logits - np.max(scaled_logits))
            probabilities = exp_logits / np.sum(exp_logits)
            calibrated_confidence = float(np.max(probabilities))
        else:
            # 简单的温度缩放（当没有logits时）
            # 使用logit变换
            if raw_confidence >= 0.999:
                raw_confidence = 0.999
            if raw_confidence <= 0.001:
                raw_confidence = 0.001
                
            # 转换到logit空间
            logit = np.log(raw_confidence / (1 - raw_confidence))
            # 应用温度缩放
            scaled_logit = logit / self.temperature
            # 转换回概率
            calibrated_confidence = float(1 / (1 + np.exp(-scaled_logit)))
        
        # 记录样本数，缺失键时进行容错初始化
        if 'samples_calibrated' not in self.calibration_stats:
            self.calibration_stats['samples_calibrated'] = 0
        self.calibration_stats['samples_calibrated'] += 1
        
        return calibrated_confidence
    
    def calibrate_probabilities(self, probabilities: Dict[str, float]) -> Dict[str, float]:
        """
        校准整个概率分布
        
        Args:
            probabilities: 原始概率分布
            
        Returns:
            校准后的概率分布
        """
        # 提取概率值并转换为logits
        classes = list(probabilities.keys())
        probs = np.array([probabilities[c] for c in classes])
        
        # 防止log(0)
        probs = np.clip(probs, 1e-7, 1 - 1e-7)
        
        # 转换为logits
        logits = np.log(probs / (1 - probs))
        
        # 应用温度缩放
        scaled_logits = logits / self.temperature
        
        # 转换回概率（使用softmax）
        exp_logits = np.exp(scaled_logits - np.max(scaled_logits))
        calibrated_probs = exp_logits / np.sum(exp_logits)
        
        # 构建校准后的概率字典
        calibrated_dict = {c: float(p) for c, p in zip(classes, calibrated_probs)}
        
        return calibrated_dict
    
    def compute_ece(self, predictions, confidences, labels, n_bins=15):
        """
        计算期望校准误差(Expected Calibration Error, ECE)
        
        Args:
            predictions: 预测结果
            confidences: 置信度分数
            labels: 真实标签
            n_bins: 分箱数量
            
        Returns:
            ECE (百分比)
        """
        predictions = np.array(predictions)
        confidences = np.array(confidences)
        labels = np.array(labels)
        
        # 计算准确率
        accuracies = (predictions == labels).astype(float)
        
        # 创建分箱
        bin_boundaries = np.linspace(0, 1, n_bins + 1)
        bin_lowers = bin_boundaries[:-1]
        bin_uppers = bin_boundaries[1:]
        
        ece = 0.0
        for bin_lower, bin_upper in zip(bin_lowers, bin_uppers):
            # 找到落在当前箱中的样本
            in_bin = (confidences > bin_lower) & (confidences <= bin_upper)
            prop_in_bin = in_bin.mean()
            
            if prop_in_bin > 0:
                # 计算箱内准确率和平均置信度
                accuracy_in_bin = accuracies[in_bin].mean()
                avg_confidence_in_bin = confidences[in_bin].mean()
                
                # 累加ECE
                ece += np.abs(avg_confidence_in_bin - accuracy_in_bin) * prop_in_bin
        
        return ece * 100  # 转换为百分比
    
    def fit_temperature(self, 
                       validation_data: list,
                       learning_rate: float = 0.01,
                       max_iter: int = 50) -> float:
        """
        在验证集上学习最优温度参数
        
        Args:
            validation_data: 验证数据列表，每个元素为(logits, label)
            learning_rate: 学习率
            max_iter: 最大迭代次数
            
        Returns:
            最优温度参数
        """
        if not validation_data:
            logger.warning("验证集为空，使用默认温度参数")
            return self.temperature
        
        # 准备数据
        all_logits = []
        all_labels = []
        
        for logits, label in validation_data:
            all_logits.append(logits)
            all_labels.append(label)
        
        logits_tensor = torch.tensor(np.array(all_logits), dtype=torch.float32)
        labels_tensor = torch.tensor(all_labels, dtype=torch.long)
        
        # 创建温度缩放模型
        temp_model = TemperatureScaling()
        
        # 学习最优温度
        optimal_temp = temp_model.calibrate(logits_tensor, labels_tensor, 
                                          lr=learning_rate, max_iter=max_iter)
        
        self.temperature = optimal_temp
        logger.info(f"学习到的最优温度参数: {optimal_temp:.3f}")
        
        return optimal_temp
    
    def save(self, filepath: str):
        """保存校准参数"""
        params = {
            'temperature': self.temperature,
            'calibration_stats': self.calibration_stats
        }
        
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(params, f, indent=2)
        
        logger.info(f"校准参数已保存至: {filepath}")
    
    def load(self, filepath: str):
        """加载校准参数"""
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                params = json.load(f)
            
            self.temperature = params.get('temperature', 1.5)
            # 与 __init__ 中的默认结构合并，避免缺失键导致 KeyError
            default_stats = {
                'pre_calibration_ece': None,
                'post_calibration_ece': None,
                'samples_calibrated': 0,
            }
            loaded_stats = params.get('calibration_stats', {}) or {}
            if isinstance(loaded_stats, dict):
                default_stats.update(loaded_stats)
            self.calibration_stats = default_stats
            
            logger.info(f"从 {filepath} 加载校准参数，温度: {self.temperature}")
        else:
            logger.warning(f"校准参数文件不存在: {filepath}")


def evaluate_calibration(classifier, test_data: list) -> Dict[str, float]:
    """
    评估校准效果
    
    Returns:
        包含校准前后ECE的字典
    """
    predictions = []
    raw_confidences = []
    calibrated_confidences = []
    labels = []
    
    for query_data in test_data:
        # 获取原始预测
        complexity, raw_conf, probs = classifier.predict_with_confidence(query_data['query'])
        
        # 应用校准
        calibrated_conf = classifier.calibrator.calibrate_confidence(raw_conf)
        
        predictions.append(complexity)
        raw_confidences.append(raw_conf)
        calibrated_confidences.append(calibrated_conf)
        labels.append(query_data['true_complexity'])
    
    # 计算ECE
    predictions_array = np.array([
        {'zero_hop': 0, 'one_hop': 1, 'multi_hop': 2}[p] 
        for p in predictions
    ])
    labels_array = np.array([
        {'zero_hop': 0, 'one_hop': 1, 'multi_hop': 2}[l] 
        for l in labels
    ])
    
    calibrator = ConfidenceCalibrator()
    
    raw_ece = calibrator.compute_ece(
        predictions_array, 
        np.array(raw_confidences), 
        labels_array
    )
    
    calibrated_ece = calibrator.compute_ece(
        predictions_array,
        np.array(calibrated_confidences),
        labels_array
    )
    
    return {
        'raw_ece': raw_ece,
        'calibrated_ece': calibrated_ece,
        'improvement': raw_ece - calibrated_ece
    }

