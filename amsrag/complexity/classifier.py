"""
澶嶆潅搴﹀垎绫诲櫒妯″潡
鍩轰簬ModernBERT鐨勬煡璇㈠鏉傚害鍒嗙被
"""

import os
import json
import torch
import numpy as np
import logging
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Any

# 妫€鏌ヤ緷璧?
TRANSFORMERS_AVAILABLE = False
try:
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    from peft import PeftModel, PeftConfig
    TRANSFORMERS_AVAILABLE = True
except ImportError as e:
    # 浣跨敤logger鑰岄潪print锛岀鍚堟棩蹇楄鑼?
    logging.getLogger(__name__).warning(f"Transformers搴撳鍏ュけ璐? {e}锛屽皢浠呬娇鐢ㄥ惎鍙戝紡瑙勫垯")



logger = logging.getLogger(__name__)

@dataclass 
class ComplexityClassifierConfig:
    """澶嶆潅搴﹀垎绫诲櫒閰嶇疆"""
    model_path: str = "amsrag/models/modernbert_complexity_classifier_standard"
    pkl_model_path: str = ""  # PKL妯″瀷璺緞锛屼负绌哄垯鑷姩鎼滅储
    max_length: int = 256
    confidence_threshold: float = 0.7
    device: str = "auto"
    temperature: float = 1.5  # 娓╁害缂╂斁鍙傛暟
    enable_calibration: bool = True
    calibration_method: str = "temperature_scaling"
    
    # 鍘熷鏍囩鍒板鏉傚害绛夌骇鐨勬槧灏?
    label_to_complexity: Dict[str, str] = None
    
    
    def __post_init__(self):
        if self.label_to_complexity is None:
            self.label_to_complexity = {
                # 鐩存帴浣跨敤璁粌鏃剁殑鏍囩鏄犲皠
                "zero_hop": "zero_hop",
                "one_hop": "one_hop", 
                "multi_hop": "multi_hop"
            }
        
        # 鍙傛暟楠岃瘉
        if not 0 < self.confidence_threshold < 1:
            raise ValueError(f"confidence_threshold蹇呴』鍦?0,1)鑼冨洿鍐咃紝褰撳墠鍊? {self.confidence_threshold}")
        if self.temperature <= 0:
            raise ValueError(f"temperature蹇呴』澶т簬0锛屽綋鍓嶅€? {self.temperature}")
        if self.max_length <= 0:
            raise ValueError(f"max_length蹇呴』澶т簬0锛屽綋鍓嶅€? {self.max_length}")
        supported_methods = {"temperature_scaling", "platt_scaling", "isotonic"}
        if self.calibration_method not in supported_methods:
            raise ValueError(
                f"Unsupported calibration_method: {self.calibration_method}. "
                f"Supported: {sorted(supported_methods)}"
            )

class ComplexityClassifier:
    """澶嶆潅搴﹀垎绫诲櫒"""
    
    def __init__(self, config: ComplexityClassifierConfig = None):
        """鍒濆鍖栧垎绫诲櫒"""
        self.config = config or ComplexityClassifierConfig()
        self.model = None
        self.tokenizer = None
        self.pkl_model = None
        self._model_type = "lora"  # lora, pkl, heuristic
        self.id2label = {}
        
        # 鍒濆鍖栨牎鍑嗗櫒
        self.calibrator = None
        self._init_calibrator()
        
        # 妫€鏌ヤ緷璧?
        if not TRANSFORMERS_AVAILABLE:
            logger.warning("transformers搴撴湭瀹夎锛屽皢浠呬娇鐢ㄥ惎鍙戝紡瑙勫垯")
            return
            
        # 鑷姩鍔犺浇妯″瀷
        self._load_model()
    
    def _init_calibrator(self):
        """Initialize confidence calibrator and load persisted params when possible."""
        if not self.config.enable_calibration:
            self.calibrator = None
            logger.info("Calibration is disabled by configuration.")
            return
        try:
            from .calibrator import ConfidenceCalibrator

            # 鍒涘缓鏍″噯鍣ㄥ疄渚嬶紝璁剧疆榛樿娓╁害
            self.calibrator = ConfidenceCalibrator(temperature=self.config.temperature)
            if self.config.calibration_method != "temperature_scaling":
                logger.warning(
                    f"Calibration method '{self.config.calibration_method}' is not yet "
                    "implemented; fallback to temperature_scaling."
                )

            # 1. 灏濊瘯 JSON 褰㈠紡鐨勬牎鍑嗗弬鏁?
            model_dir = os.path.dirname(self.config.model_path)
            calibration_file = os.path.join(model_dir, "calibration_params.json")
            if os.path.exists(calibration_file):
                self.calibrator.load(calibration_file)
                logger.info(f"鍔犺浇鏍″噯鍙傛暟锛屾俯搴? {self.calibrator.temperature}")
                return

            # 2. 灏濊瘯鍔犺浇瀹為獙浜х敓鐨?TemperatureScaling pkl锛堝鏋滃瓨鍦級
            try:
                import pickle

                candidate_files = [
                    os.path.join(model_dir, "calibrator_temperature_scaling.pkl"),
                    os.path.join(model_dir, "calibrator_platt_scaling.pkl"),
                    os.path.join(model_dir, "calibrator_isotonic.pkl"),
                ]

                for pkl_path in candidate_files:
                    if not os.path.exists(pkl_path):
                        continue
                    try:
                        with open(pkl_path, "rb") as f:
                            obj = pickle.load(f)
                        temp = getattr(obj, "temperature_", None)
                        if temp is not None:
                            self.calibrator.temperature = float(temp)
                            logger.info(
                                f"浠?{pkl_path} 鍔犺浇娓╁害缂╂斁鍙傛暟: {self.calibrator.temperature}"
                            )
                            return
                    except Exception as e:  # noqa: BLE001 - 浠呰褰曟棩蹇?
                        logger.warning(f"鍔犺浇鏍″噯 pkl 澶辫触 {pkl_path}: {e}")

                logger.info("鏈壘鍒版牎鍑嗗弬鏁版枃浠讹紝浣跨敤榛樿娓╁害 1.5")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"鍒濆鍖栨牎鍑嗗櫒鏃惰В鏋?pkl 澶辫触锛屽皢浣跨敤榛樿娓╁害: {e}")

        except Exception as e:  # noqa: BLE001
            logger.warning(f"鏍″噯鍣ㄥ垵濮嬪寲澶辫触: {e}")
            self.calibrator = None
    
    @classmethod
    def load_default(cls, model_path: str = None) -> "ComplexityClassifier":
        """鍔犺浇榛樿閰嶇疆鐨勫垎绫诲櫒"""
        config = ComplexityClassifierConfig()
        if model_path:
            config.model_path = model_path
        return cls(config)
    
    def _load_model(self):
        """鍔犺浇ModernBERT妯″瀷鍜岀浉鍏崇粍浠?"""
        if not TRANSFORMERS_AVAILABLE:
            return
            
        try:
            logger.info(f"姝ｅ湪鍔犺浇澶嶆潅搴﹀垎绫诲櫒: {self.config.model_path}")
            
            # 妫€鏌ユ爣鍑嗘牸寮忔ā鍨嬭矾寰勬槸鍚﹀瓨鍦?
            if not os.path.exists(self.config.model_path):
                logger.warning(f"妯″瀷璺緞涓嶅瓨鍦? {self.config.model_path}")
                
                # 浠呭湪鏍囧噯妯″瀷涓嶅瓨鍦ㄦ椂锛屾墠灏濊瘯鍔犺浇PKL鏍煎紡锛堝悜鍚庡吋瀹癸級
                logger.info("鏍囧噯鏍煎紡妯″瀷涓嶅瓨鍦紝灏濊瘯鏌ユ壘PKL鏍煎紡妯″瀷锛堝悜鍚庡吋瀹癸級...")
                pkl_model_paths = [
                    self.config.pkl_model_path,  # 閰嶇疆鎸囧畾鐨勮矾寰?
                    os.path.join(os.path.dirname(self.config.model_path), "modernbert_best_model.pkl"),
                    "experiments/experiment1_complexity_classifier/outputs/models/modernbert_best_model.pkl",
                ]
                
                for pkl_model_path in pkl_model_paths:
                    if pkl_model_path and os.path.exists(pkl_model_path):
                        logger.info(f"鍙戠幇PKL鏍煎紡鐨勮缁冩ā鍨? {pkl_model_path}")
                        try:
                            self.pkl_model = self._load_pkl_model_safely(pkl_model_path)
                            if self.pkl_model is not None:
                                logger.info("PKL妯″瀷鍔犺浇鎴愬姛锛堝悜鍚庡吋瀹规ā寮忥級")
                                logger.info(f"妯″瀷绫诲瀷: {type(self.pkl_model)}")
                                self._model_type = "pkl"
                                return
                        except Exception as e:
                            logger.warning(f"PKL妯″瀷鍔犺浇澶辫触: {e}")
                
                logger.warning("No available model found; fallback to heuristic classification.")
                return
            
            logger.info(f"鍔犺浇鏍囧噯鏍煎紡妯″瀷: {self.config.model_path}")
            
            # 妫€鏌ユ槸鍚︿负PEFT/LoRA妯″瀷
            adapter_config_path = os.path.join(self.config.model_path, "adapter_config.json")
            if os.path.exists(adapter_config_path):
                logger.info("妫€娴嬪埌PEFT/LoRA妯″瀷锛屽姞杞介€傞厤鍣?..")
                
                # 鍔犺浇PEFT閰嶇疆
                peft_config = PeftConfig.from_pretrained(self.config.model_path)
                
                # 淇鐩稿璺緞闂
                base_model_path = peft_config.base_model_name_or_path
                if base_model_path.startswith("../"):
                    # 澶勭悊鐩稿璺緞锛屽皢鍏惰浆鎹负缁濆璺緞
                    adapter_dir = os.path.dirname(self.config.model_path)
                    base_model_path = os.path.abspath(os.path.join(adapter_dir, base_model_path))
                    logger.info(f"淇鐩稿璺緞: {peft_config.base_model_name_or_path} -> {base_model_path}")

                # 妫€鏌ヤ慨澶嶅悗鐨勮矾寰勬槸鍚﹀瓨鍦?
                if not os.path.exists(base_model_path):
                    logger.warning(f"鍩虹妯″瀷璺緞涓嶅瓨鍦? {base_model_path}锛屽皢浠呬娇鐢ㄥ惎鍙戝紡瑙勫垯")
                    return

                # 鍔犺浇鍩虹妯″瀷鍜宼okenizer
                self.tokenizer = AutoTokenizer.from_pretrained(base_model_path)
                base_model = AutoModelForSequenceClassification.from_pretrained(
                    base_model_path,
                    num_labels=3,  # zero_hop, one_hop, multi_hop
                    torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32
                )
                
                # 鍔犺浇PEFT閫傞厤鍣?
                self.model = PeftModel.from_pretrained(base_model, self.config.model_path)
                self._model_type = "lora"
                
            else:
                # 鏅€氭ā鍨嬪姞杞?
                self.tokenizer = AutoTokenizer.from_pretrained(self.config.model_path)
                self.model = AutoModelForSequenceClassification.from_pretrained(
                    self.config.model_path,
                    torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32
                )
                self._model_type = "lora"
            
            # 璁剧疆璁惧
            if self.config.device == "auto":
                self.config.device = "cuda" if torch.cuda.is_available() else "cpu"
            
            self.model.to(self.config.device)
            self.model.eval()
            
            # 璁剧疆鏍囩鏄犲皠
            if hasattr(self.model.config, 'id2label'):
                self.id2label = self.model.config.id2label
            else:
                self.id2label = {0: "zero_hop", 1: "one_hop", 2: "multi_hop"}
            
            logger.info("澶嶆潅搴﹀垎绫诲櫒鍔犺浇鎴愬姛")
            
        except Exception as e:
            logger.error(f"妯″瀷鍔犺浇澶辫触: {e}")
            logger.warning("Model loading failed; fallback to heuristic classification.")
    
    def _load_pkl_model_safely(self, pkl_model_path: str):
        """瀹夊叏鍔犺浇PKL妯″瀷 - 瀹屾暣瑙ｅ喅鏂规"""
        import sys
        import importlib
        import pickle
        
        try:
            # 璁剧疆鐜鍙橀噺閬垮厤Triton闂
            os.environ['PYTORCH_DISABLE_TRITON'] = '1'
            os.environ['TORCHDYNAMO_DISABLE'] = '1'
            
            # 1. 娣诲姞瀹為獙鐩綍鍒癙ython璺緞
            experiment_dir = os.path.join(os.getcwd(), "experiments", "experiment1_complexity_classifier")
            if os.path.exists(experiment_dir) and experiment_dir not in sys.path:
                sys.path.insert(0, experiment_dir)
                logger.debug(f"涓存椂娣诲姞璺緞: {experiment_dir}")
            
            # 2. 瀵煎叆蹇呰鐨勬ā鍧?
            try:
                import src.models.modernbert_classifier
                importlib.reload(src.models.modernbert_classifier)
                logger.debug("鎴愬姛瀵煎叆瀹為獙鐜鐨凪odernBertClassifier")
            except ImportError as e:
                logger.warning(f"鏃犳硶瀵煎叆瀹為獙鐜妯″潡: {e}")
                return None
            
            # 3. 浣跨敤涓庤缁冮樁娈典竴鑷寸殑鏂瑰紡鍔犺浇妯″瀷瀵硅薄
            #    璁粌鑴氭湰涓娇鐢ㄧ殑鏄?pickle.dump(model, f)锛屽洜姝よ繖閲屼紭鍏堝皾璇?pickle.load锛?
            #    濡傚け璐ュ啀閫€鍥炲埌 torch.load 浠ュ吋瀹规湭鏉ュ彲鑳界殑 torch.save 浜х墿銆?
            with open(pkl_model_path, 'rb') as f:
                try:
                    model = pickle.load(f)
                    logger.debug("浣跨敤 pickle.load 鎴愬姛鍔犺浇 PKL 妯″瀷")
                except Exception as e:
                    logger.warning(f"pickle.load 璇诲彇 PKL 妯″瀷澶辫触锛屽皢閫€鍥?torch.load: {e}")
                    f.seek(0)
                    import torch
                    model = torch.load(f, map_location=torch.device('cpu'), weights_only=False)
            
            # 4. 淇閰嶇疆闂 - 淇姝ｇ‘鐨則ransformer閰嶇疆
            if hasattr(model, 'model') and hasattr(model.model, 'transformer') and hasattr(model.model.transformer, 'config'):
                transformer_config = model.model.transformer.config
                logger.debug("淇Transformer閰嶇疆...")
                
                setattr(transformer_config, 'output_attentions', False)
                setattr(transformer_config, 'output_hidden_states', False)
                setattr(transformer_config, 'return_dict', True)
                setattr(transformer_config, 'use_cache', True)
                
                logger.debug("Transformer閰嶇疆淇瀹屾垚")
            
            # 5. 璁剧疆涓鸿瘎浼版ā寮?
            if hasattr(model, 'model') and hasattr(model.model, 'eval'):
                model.model.eval()
                logger.debug("Model switched to eval mode.")
            
            # 6. 楠岃瘉妯″瀷鎺ュ彛
            if hasattr(model, 'predict'):
                logger.info("PKL model loaded successfully and predict interface is available.")
                logger.info(f"妯″瀷绫诲瀷: {type(model)}")
                return model
            else:
                logger.warning("PKL妯″瀷缂哄皯predict鏂规硶")
                return None
                
        except Exception as e:
            logger.error(f"PKL妯″瀷鍔犺浇澶辫触: {e}")
            return None
    
    def _predict_with_pkl_model(self, query: str) -> str:
        """浣跨敤PKL妯″瀷杩涜棰勬祴 - 澶勭悊瀹為檯杩斿洖鏍煎紡"""
        if self.pkl_model is None:
            raise ValueError("PKL model is not loaded.")
            
        try:
            # 鐩存帴璋冪敤妯″瀷鐨刾redict鏂规硶
            prediction = self.pkl_model.predict(query)
            
            # 澶勭悊涓嶅悓鐨勮繑鍥炴牸寮?
            if prediction is None:
                logger.warning("PKL妯″瀷杩斿洖None")
                return "one_hop"
                
            if isinstance(prediction, (list, tuple, np.ndarray)):
                if len(prediction) == 0:
                    logger.warning("PKL model returned an empty prediction sequence.")
                    return "one_hop"
                # 鑾峰彇绗竴涓厓绱狅紙鍙兘鏄暟缁勭储寮曪級
                class_idx = prediction[0]
                if isinstance(class_idx, (int, np.integer)):
                    # 鏄犲皠鍒扮被鍒悕绉?
                    class_names = ['zero_hop', 'one_hop', 'multi_hop']
                    if 0 <= class_idx < len(class_names):
                        return class_names[class_idx]
                    else:
                        logger.warning(f"Invalid class index from PKL model: {class_idx}; fallback to one_hop.")
                        return "one_hop"
                elif isinstance(class_idx, str):
                    return class_idx
                else:
                    logger.warning(f"鏈煡鐨勭被鍒被鍨? {type(class_idx)}")
                    return "one_hop"
            elif isinstance(prediction, str):
                return prediction
            elif isinstance(prediction, (int, np.integer)):
                class_names = ['zero_hop', 'one_hop', 'multi_hop']
                if 0 <= prediction < len(class_names):
                    return class_names[prediction]
                return "one_hop"
            else:
                logger.warning(f"PKL妯″瀷杩斿洖鏈煡鏍煎紡: {type(prediction)}")
                return "one_hop"  # 榛樿杩斿洖
                
        except Exception as e:
            logger.error(f"PKL妯″瀷棰勬祴澶辫触: {e}")
            raise
    
    def _get_pkl_model_probabilities(self, query: str) -> Dict[str, float]:
        """鑾峰彇PKL妯″瀷鐨勬鐜囧垎甯?- 澶勭悊瀹為檯杩斿洖鏍煎紡"""
        try:
            if hasattr(self.pkl_model, 'predict_proba'):
                proba = self.pkl_model.predict_proba(query)
                
                # 澶勭悊涓嶅悓鐨勮繑鍥炴牸寮?
                if isinstance(proba, (list, tuple, np.ndarray)) and len(proba) > 0:
                    if isinstance(proba[0], (list, tuple, np.ndarray)):
                        proba = proba[0]  # 鍙栫涓€涓牱鏈殑姒傜巼
                
                # 纭繚proba鏄彲绱㈠紩鐨?
                if hasattr(proba, '__len__') and len(proba) >= 3:
                    return {
                        "zero_hop": float(proba[0]),
                        "one_hop": float(proba[1]),
                        "multi_hop": float(proba[2])
                    }
                else:
                    logger.warning(f"姒傜巼鏁扮粍闀垮害涓嶈冻: {len(proba) if hasattr(proba, '__len__') else 'unknown'}")
                    return {}
            else:
                return {}
        except Exception as e:
            logger.debug(f"鑾峰彇姒傜巼鍒嗗竷澶辫触: {e}")
            return {}
    
    def _fix_pkl_model_config(self):
        """淇PKL妯″瀷鐨勯厤缃棶棰?"""
        try:
            if hasattr(self.pkl_model, 'model') and hasattr(self.pkl_model.model, 'config'):
                config = self.pkl_model.model.config
                
                # 鐩存帴璁剧疆灞炴€э紝涓嶆鏌ユ槸鍚﹀瓨鍦?
                setattr(config, 'output_attentions', False)
                setattr(config, 'output_hidden_states', False)
                setattr(config, 'return_dict', True)
                setattr(config, 'use_cache', True)
                
                # 娣诲姞鍏朵粬鍙兘闇€瑕佺殑灞炴€?
                setattr(config, 'pad_token_id', getattr(config, 'pad_token_id', 0))
                setattr(config, 'eos_token_id', getattr(config, 'eos_token_id', 2))
                
                logger.debug("PKL妯″瀷閰嶇疆淇瀹屾垚")
                
                # 濡傛灉妯″瀷鏈塼okenizer锛屼篃淇tokenizer鐨勯厤缃?
                if hasattr(self.pkl_model, 'tokenizer') and self.pkl_model.tokenizer:
                    tokenizer = self.pkl_model.tokenizer
                    if hasattr(tokenizer, 'model_max_length') and tokenizer.model_max_length is None:
                        tokenizer.model_max_length = 512
                
        except Exception as e:
            logger.warning(f"閰嶇疆淇澶辫触: {e}")
    

    
    def load_model(self, model_path: str = None):
        """鍏叡妯″瀷鍔犺浇鏂规硶"""
        if model_path:
            self.config.model_path = model_path
        self._load_model()
            
        try:
            logger.info(f"姝ｅ湪鍔犺浇澶嶆潅搴﹀垎绫诲櫒: {self.config.model_path}")
            
            # 妫€鏌ユā鍨嬭矾寰勬槸鍚﹀瓨鍦?
            if not os.path.exists(self.config.model_path):
                logger.warning(f"妯″瀷璺緞涓嶅瓨鍦? {self.config.model_path}锛屽皢浠呬娇鐢ㄥ惎鍙戝紡瑙勫垯")
                return
                
            # 妫€鏌ユ槸鍚︿负PEFT/LoRA妯″瀷
            adapter_config_path = os.path.join(self.config.model_path, "adapter_config.json")
            if os.path.exists(adapter_config_path):
                logger.info("妫€娴嬪埌PEFT/LoRA妯″瀷锛屽姞杞介€傞厤鍣?..")
                
                # 鍔犺浇PEFT閰嶇疆
                peft_config = PeftConfig.from_pretrained(self.config.model_path)
                
                # 淇鐩稿璺緞闂
                base_model_path = peft_config.base_model_name_or_path
                if base_model_path.startswith("../"):
                    # 澶勭悊鐩稿璺緞锛屽皢鍏惰浆鎹负缁濆璺緞
                    adapter_dir = os.path.dirname(self.config.model_path)
                    base_model_path = os.path.abspath(os.path.join(adapter_dir, base_model_path))
                    logger.info(f"淇鐩稿璺緞: {peft_config.base_model_name_or_path} -> {base_model_path}")

                # 妫€鏌ヤ慨澶嶅悗鐨勮矾寰勬槸鍚﹀瓨鍦?
                if not os.path.exists(base_model_path):
                    # 灏濊瘯浣跨敤椤圭洰鍐呯殑鍩虹妯″瀷
                    project_base_model_path = "amsrag/models/modernbert/answerdotai_ModernBERT-large"
                    if os.path.exists(project_base_model_path):
                        base_model_path = project_base_model_path
                        logger.info(f"浣跨敤椤圭洰鍐呭熀纭€妯″瀷: {base_model_path}")
                    else:
                        logger.warning(
                            f"Base model path does not exist: {base_model_path}; trying online model."
                        )
                        base_model_path = "answerdotai/ModernBERT-large"

                # 鍔犺浇鍩虹妯″瀷
                base_model = AutoModelForSequenceClassification.from_pretrained(
                    base_model_path,
                    num_labels=3,  # 鎴戜滑鐨勮缁冩ā鍨嬩娇鐢?涓被鍒?
                    device_map=self.config.device if self.config.device != "auto" else "auto",
                    attn_implementation="eager",  # 绂佺敤Flash Attention
                    torch_dtype=torch.float32,   # 浣跨敤float32閬垮厤鏌愪簺璁惧闂
                    trust_remote_code=True       # 鍏佽杩滅▼浠ｇ爜鎵ц
                )
                
                # 鍔犺浇PEFT閫傞厤鍣?
                self.model = PeftModel.from_pretrained(base_model, self.config.model_path)
                
                # 鍔犺浇鏍囩鏄犲皠
                label_mapping_path = os.path.join(self.config.model_path, "label_mapping.json")
                if os.path.exists(label_mapping_path):
                    with open(label_mapping_path, 'r', encoding='utf-8') as f:
                        label_mapping = json.load(f)
                    self.id2label = label_mapping.get("id2label", {})
                    
                    # 纭繚id2label鐨勯敭鏄暣鏁?
                    self.id2label = {int(k): v for k, v in self.id2label.items()}
                else:
                    # 榛樿鏍囩鏄犲皠
                    self.id2label = {0: "zero_hop", 1: "one_hop", 2: "multi_hop"}
            else:
                # 鏅€氭ā鍨嬪姞杞?
                self.model = AutoModelForSequenceClassification.from_pretrained(
                    self.config.model_path,
                    device_map=self.config.device if self.config.device != "auto" else "auto",
                    attn_implementation="eager",  # 绂佺敤Flash Attention
                    torch_dtype=torch.float32,   # 浣跨敤float32閬垮厤鏌愪簺璁惧闂
                    trust_remote_code=True       # 鍏佽杩滅▼浠ｇ爜鎵ц
                )
                
                # 鑾峰彇鏍囩鏄犲皠
                self.id2label = self.model.config.id2label
            
            # 鍔犺浇tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.config.model_path,
                trust_remote_code=True
            )
            
            logger.info("澶嶆潅搴﹀垎绫诲櫒鍔犺浇鎴愬姛")
            
        except Exception as e:
            logger.error(f"鍔犺浇妯″瀷澶辫触: {e}")
            self.model = None
            self.tokenizer = None
    
    def _map_to_complexity(self, original_label: str) -> str:
        """灏嗗師濮嬫爣绛炬槧灏勫埌澶嶆潅搴︾瓑绾?"""
        # 棣栧厛灏濊瘯閰嶇疆鏄犲皠
        mapped = self.config.label_to_complexity.get(original_label, original_label)
        if mapped != original_label:
            return mapped
        
        # 澶勭悊LABEL_x鏍煎紡鐨勬爣绛撅紙ModernBERT妯″瀷杈撳嚭锛?
        label_mapping = {
            "LABEL_0": "zero_hop",
            "LABEL_1": "one_hop", 
            "LABEL_2": "multi_hop"
        }
        if original_label in label_mapping:
            return label_mapping[original_label]
        
        # 澶勭悊鍏朵粬鏍煎紡鐨勬爣绛?
        base_mapping = {
            "zero-hop": "zero_hop",
            "one-hop": "one_hop", 
            "multi-hop": "multi_hop",
            "0": "zero_hop",
            "1": "one_hop",
            "2": "multi_hop"
        }
        return base_mapping.get(original_label, original_label)
    
    def _smart_map_base_model(self, original_label: str) -> str:
        """鏅鸿兘鏄犲皠鍩虹妯″瀷鐨勬爣绛?"""
        # 鍩虹妯″瀷鐨勬爣绛炬槧灏?
        base_mapping = {
            "zero-hop": "zero_hop",
            "one-hop": "one_hop", 
            "multi-hop": "multi_hop"
        }
        return base_mapping.get(original_label, original_label)
    
    def predict(self, query: str) -> str:
        """棰勬祴鏌ヨ澶嶆潅搴?"""
        if not self.is_available():
            # 鍥為€€鍒板惎鍙戝紡瑙勫垯
            return self._heuristic_classify(query)
        
        try:
            # PKL妯″瀷棰勬祴
            if self._model_type == "pkl" and self.pkl_model is not None:
                predicted_label = self._predict_with_pkl_model(query)
                return self._map_to_complexity(predicted_label)
            
            # LoRA妯″瀷棰勬祴
            elif self._model_type == "lora" and self.model is not None:
                # 缂栫爜杈撳叆
                inputs = self.tokenizer(
                    query,
                    truncation=True,
                    padding=True,
                    max_length=self.config.max_length,
                    return_tensors="pt"
                )
                
                # 鑷姩妫€娴嬭澶囧苟绉诲姩杈撳叆
                device = next(self.model.parameters()).device
                inputs = {k: v.to(device) for k, v in inputs.items()}
                
                # 鎺ㄧ悊
                with torch.no_grad():
                    outputs = self.model(**inputs)
                    logits = outputs.logits
                    probabilities = torch.softmax(logits, dim=-1)
                    predicted_id = torch.argmax(probabilities, dim=-1).item()
                    confidence = probabilities[0][predicted_id].item()
                
                # 鑾峰彇棰勬祴鏍囩
                predicted_label = self.id2label.get(predicted_id, "one_hop")
                
                # 鏄犲皠鍒板鏉傚害绛夌骇
                complexity = self._map_to_complexity(predicted_label)
                
                return complexity
            else:
                return self._heuristic_classify(query)
            
        except Exception as e:
            logger.error(f"棰勬祴澶辫触: {e}")
            return self._heuristic_classify(query)
    
    def predict_with_confidence(self, query: str) -> Tuple[str, float, Dict[str, float]]:
        """棰勬祴鏌ヨ澶嶆潅搴︼紙甯︾疆淇″害鏍″噯锛?"""
        if not self.is_available():
            # 鍥為€€鍒板惎鍙戝紡瑙勫垯
            complexity = self._heuristic_classify(query)
            return complexity, 0.5, {}
        
        try:
            # PKL妯″瀷棰勬祴
            if self._model_type == "pkl" and self.pkl_model is not None:
                predicted_label = self._predict_with_pkl_model(query)
                complexity = self._map_to_complexity(predicted_label)
                
                # 鑾峰彇姒傜巼鍒嗗竷
                probabilities = self._get_pkl_model_probabilities(query)
                if probabilities:
                    raw_confidence = max(probabilities.values())
                else:
                    raw_confidence = 0.8  # 榛樿缃俊搴?
                    
            # LoRA妯″瀷棰勬祴
            elif self._model_type == "lora" and self.model is not None:
                # 缂栫爜杈撳叆
                inputs = self.tokenizer(
                    query,
                    truncation=True,
                    padding=True,
                    max_length=self.config.max_length,
                    return_tensors="pt"
                )
                
                # 鑷姩妫€娴嬭澶囧苟绉诲姩杈撳叆
                device = next(self.model.parameters()).device
                inputs = {k: v.to(device) for k, v in inputs.items()}
                
                # 鎺ㄧ悊
                with torch.no_grad():
                    outputs = self.model(**inputs)
                    logits = outputs.logits
                    probabilities_tensor = torch.softmax(logits, dim=-1)
                    predicted_id = torch.argmax(probabilities_tensor, dim=-1).item()
                    raw_confidence = probabilities_tensor[0][predicted_id].item()
                
                # 鑾峰彇棰勬祴鏍囩
                predicted_label = self.id2label.get(predicted_id, "one_hop")
                
                # 鏄犲皠鍒板鏉傚害绛夌骇
                complexity = self._map_to_complexity(predicted_label)
                
                # 鏋勫缓姒傜巼瀛楀吀
                prob_array = probabilities_tensor[0].cpu().numpy()
                probabilities = {
                    "zero_hop": float(prob_array[0]) if len(prob_array) > 0 else 0.0,
                    "one_hop": float(prob_array[1]) if len(prob_array) > 1 else 0.0,
                    "multi_hop": float(prob_array[2]) if len(prob_array) > 2 else 0.0
                }
            else:
                complexity = self._heuristic_classify(query)
                return complexity, 0.5, {}
            
            # 鏄犲皠鍒板鏉傚害绛夌骇
            complexity = self._map_to_complexity(predicted_label) if 'predicted_label' in locals() else complexity
            
            # 搴旂敤缃俊搴︽牎鍑?
            if self.calibrator is not None:
                # 鑾峰彇logits锛堝鏋滃彲鐢級
                logits = None
                if 'logits' in locals() and hasattr(locals()['logits'], 'cpu'):
                    logits_array = locals()['logits'][0].cpu().numpy()
                    logits = logits_array
                
                # 鏍″噯缃俊搴?
                confidence = self.calibrator.calibrate_confidence(
                    raw_confidence,
                    logits=logits
                )
                
                # 涔熸牎鍑嗘鐜囧垎甯?
                if probabilities:
                    probabilities = self.calibrator.calibrate_probabilities(probabilities)
                
                logger.debug(f"缃俊搴︽牎鍑? {raw_confidence:.3f} -> {confidence:.3f}")
            else:
                # 鏃犳牎鍑嗗櫒鏃剁洿鎺ヤ娇鐢ㄥ師濮嬬疆淇″害
                confidence = raw_confidence
            
            return complexity, confidence, probabilities
            
        except Exception as e:
            logger.error(f"棰勬祴澶辫触: {e}")
            complexity = self._heuristic_classify(query)
            return complexity, 0.5, {}
    
    def get_logits(self, query: str) -> List[float]:
        """
        鑾峰彇鏌ヨ鐨勫師濮媗ogits杈撳嚭
        
        Args:
            query: 鏌ヨ瀛楃涓?
            
        Returns:
            logits: 鍘熷logits杈撳嚭
        """
        if not self.is_available():
            # 濡傛灉妯″瀷涓嶅彲鐢紝杩斿洖涓€涓粯璁ょ殑logits
            return [0.33, 0.34, 0.33]  # 鍧囩瓑姒傜巼
        
        try:
            # 缂栫爜杈撳叆
            inputs = self.tokenizer(
                query,
                truncation=True,
                padding=True,
                max_length=self.config.max_length,
                return_tensors="pt"
            )
            
            # 鑷姩妫€娴嬭澶囧苟绉诲姩杈撳叆
            device = next(self.model.parameters()).device
            inputs = {k: v.to(device) for k, v in inputs.items()}
            
            # 鎺ㄧ悊
            with torch.no_grad():
                outputs = self.model(**inputs)
                logits = outputs.logits.cpu().numpy()[0].tolist()
            
            return logits
            
        except Exception as e:
            logger.error(f"鑾峰彇logits澶辫触: {e}")
            return [0.33, 0.34, 0.33]  # 鍧囩瓑姒傜巼
    

    @staticmethod
    def _compute_binary_ece(
        confidences: np.ndarray,
        correct_predictions: np.ndarray,
        n_bins: int = 10,
    ) -> float:
        if len(confidences) == 0:
            return 0.0

        bin_boundaries = np.linspace(0.0, 1.0, n_bins + 1)
        ece = 0.0
        total = float(len(confidences))
        for i in range(n_bins):
            lower = bin_boundaries[i]
            upper = bin_boundaries[i + 1]
            in_bin = (confidences > lower) & (confidences <= upper)
            if not np.any(in_bin):
                continue
            acc = float(np.mean(correct_predictions[in_bin]))
            conf = float(np.mean(confidences[in_bin]))
            ece += abs(conf - acc) * (float(np.sum(in_bin)) / total)
        return float(ece)

    def calibrate_confidence(
        self,
        validation_queries: List[str],
        validation_labels: List[str],
        verbose: bool = False,
    ) -> Dict[str, float]:
        if self.calibrator is None:
            return {"status": "disabled", "method": self.config.calibration_method}
        if not validation_queries or not validation_labels:
            return {"status": "empty_validation_data", "method": self.config.calibration_method}
        if len(validation_queries) != len(validation_labels):
            return {"status": "length_mismatch", "method": self.config.calibration_method}
        if not self.is_available():
            return {"status": "classifier_unavailable", "method": self.config.calibration_method}

        label_to_id = {"zero_hop": 0, "one_hop": 1, "multi_hop": 2}
        validation_data = []
        raw_confidences = []
        correct_predictions = []

        for query, label in zip(validation_queries, validation_labels):
            if label not in label_to_id:
                continue
            logits = np.array(self.get_logits(query), dtype=float)
            if logits.size == 0:
                continue
            logits = logits - np.max(logits)
            exp_logits = np.exp(logits)
            probs = exp_logits / np.sum(exp_logits)
            pred_id = int(np.argmax(probs))
            raw_conf = float(np.max(probs))

            raw_confidences.append(raw_conf)
            correct_predictions.append(1 if pred_id == label_to_id[label] else 0)
            validation_data.append((logits.tolist(), label_to_id[label]))

        if not validation_data:
            return {"status": "no_valid_samples", "method": self.config.calibration_method}

        raw_conf_array = np.array(raw_confidences, dtype=float)
        correct_array = np.array(correct_predictions, dtype=float)
        pre_ece = self._compute_binary_ece(raw_conf_array, correct_array)

        optimal_temperature = self.calibrator.fit_temperature(validation_data)

        calibrated_confidences = []
        for logits, _ in validation_data:
            scaled_logits = np.array(logits, dtype=float) / max(self.calibrator.temperature, 1e-6)
            exp_logits = np.exp(scaled_logits - np.max(scaled_logits))
            probs = exp_logits / np.sum(exp_logits)
            calibrated_confidences.append(float(np.max(probs)))

        calibrated_conf_array = np.array(calibrated_confidences, dtype=float)
        post_ece = self._compute_binary_ece(calibrated_conf_array, correct_array)
        ece_improvement = pre_ece - post_ece

        self.calibrator.calibration_stats["pre_calibration_ece"] = pre_ece
        self.calibrator.calibration_stats["post_calibration_ece"] = post_ece

        result = {
            "status": "ok",
            "method": self.config.calibration_method,
            "samples": float(len(validation_data)),
            "optimal_temperature": float(optimal_temperature),
            "pre_calibration_ece": float(pre_ece),
            "post_calibration_ece": float(post_ece),
            "ece_improvement": float(ece_improvement),
        }
        if verbose:
            logger.info(f"Calibration results: {result}")
        return result

    def _heuristic_classify(self, query: str) -> str:
        """鍚彂寮忓鏉傚害鍒嗙被"""
        query_lower = query.lower()
        
        # 绠€鍗曠殑鍚彂寮忚鍒?
        if len(query.split()) <= 3:
            return "zero_hop"
        elif any(word in query_lower for word in ["compare", "relationship", "difference", "similarity"]):
            return "multi_hop"
        else:
            return "one_hop"
    
    async def apredict(self, query: str) -> str:
        """寮傛棰勬祴鏌ヨ澶嶆潅搴?"""
        return self.predict(query)
    
    def is_available(self) -> bool:
        """妫€鏌ュ垎绫诲櫒鏄惁鍙敤"""
        if self._model_type == "pkl":
            return self.pkl_model is not None
        elif self._model_type == "lora":
            return self.model is not None and self.tokenizer is not None
        else:
            return False


def get_global_classifier(model_path: str = None) -> ComplexityClassifier:
    """鑾峰彇鍏ㄥ眬鍒嗙被鍣ㄥ疄渚?"""
    global _global_classifier
    if not hasattr(get_global_classifier, '_global_classifier'):
        get_global_classifier._global_classifier = ComplexityClassifier.load_default(model_path)
    return get_global_classifier._global_classifier

async def classify_query_complexity(query: str, model_path: str = None) -> str:
    """寮傛鍒嗙被鏌ヨ澶嶆潅搴?"""
    classifier = get_global_classifier(model_path)
    return classifier.predict(query)

def classify_query_complexity_sync(query: str, model_path: str = None) -> str:
    """鍚屾鍒嗙被鏌ヨ澶嶆潅搴?"""
    classifier = get_global_classifier(model_path)
    return classifier.predict(query) 
