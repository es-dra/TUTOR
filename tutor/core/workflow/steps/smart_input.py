"""SmartInputStep - 智能输入处理步骤

自动识别用户输入中的:
- arXiv URL/ID
- 本地文件路径
- 领域关键词 (如 "CV", "NLP", "RL", "Transformer")
- 自然语言描述

并自动调用 arXiv 搜索补充相关文献。

Usage:
    from tutor.core.workflow.steps.smart_input import SmartInputStep

    steps = [
        SmartInputStep(
            auto_search=True,  # 自动搜索补充文献
            max_auto_papers=5  # 最多自动搜索5篇
        ),
        PaperValidationStep(),
        ...
    ]
"""

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from tutor.core.workflow.base import WorkflowStep, WorkflowContext

logger = logging.getLogger(__name__)


# 常见研究领域关键词映射
DOMAIN_KEYWORDS = {
    # 计算机视觉
    "cv": ["computer vision", "image recognition", "object detection", "image segmentation"],
    "nlp": ["natural language processing", "text understanding", "language model"],
    "rl": ["reinforcement learning", "policy gradient", "deep q learning"],
    "ml": ["machine learning", "supervised learning", "unsupervised learning"],
    "dl": ["deep learning", "neural network", "representation learning"],
    "transformer": ["transformer", "attention mechanism", "self-attention", "bert", "gpt"],
    "gan": ["generative adversarial network", "gan", "generative model"],
    "vae": ["variational autoencoder", "vae", "generative model"],
    "diffusion": ["diffusion model", "score based model", "ddpm", "stable diffusion"],
    "llm": ["large language model", "llm", "language model", "chatgpt"],
    "vlm": ["vision language model", "multimodal", "visual question answering"],
    "vit": ["vision transformer", "ViT", "image classification"],
    "seg": ["semantic segmentation", "instance segmentation", "panoptic segmentation"],
    "det": ["object detection", "yolo", "faster r-cnn", "detr"],
    "ocr": ["optical character recognition", "text recognition", "scene text"],
    "ocr": ["image captioning", "visual storytelling", "vqa"],
    "speech": ["speech recognition", "asr", "text-to-speech", "tts"],
    "robotics": ["robotics", "motion planning", "manipulation"],
    "graph": ["graph neural network", "gnn", "network embedding"],
    "recsys": ["recommender system", "collaborative filtering", "content-based filtering"],
    "ts": ["time series", "forecasting", "temporal modeling"],
    "few-shot": ["few-shot learning", "meta learning", "domain adaptation"],
    "self-supervised": ["self-supervised learning", "contrastive learning", "masked autoencoder"],
    "蒸馏": ["knowledge distillation", "model compression", "distillation"],
    "剪枝": ["neural network pruning", "model compression", "pruning"],
    "量化": ["quantization", "model quantization", "int8", "fp16"],
    "联邦": ["federated learning", "distributed learning", "privacy-preserving"],
    "对抗": ["adversarial attack", "adversarial robustness", "pgd", "fgsm"],
    "优化": ["optimizer", "adam", "sgd", "learning rate"],
    "归一化": ["batch normalization", "layer normalization", "normalization"],
    "注意力": ["attention", "self-attention", "multi-head attention"],
}

# 常用算法缩写
ALGORITHM_KEYWORDS = {
    # 视觉骨干网络
    "resnet": "ResNet: Deep Residual Learning for Image Recognition",
    "resnext": "Aggregated Residual Transformations for Deep Neural Networks",
    "vgg": "Very Deep Convolutional Networks for Large-Scale Image Recognition",
    "efficientnet": "EfficientNet: Rethinking Model Scaling for Convolutional Neural Networks",
    "mobilenet": "MobileNets: Efficient Convolutional Neural Networks for Mobile Vision Applications",
    "vit": "An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale",
    "swin": "Swin Transformer: Hierarchical Vision Transformer using Shifted Windows",
    "convnext": "A ConvNet for the 2020s",

    # 检测相关
    "yolo": "You Only Look Once: Unified, Real-Time Object Detection",
    "faster-rcnn": "Faster R-CNN: Towards Real-Time Object Detection with Region Proposal Networks",
    "mask-rcnn": "Mask R-CNN",
    "detr": "End-to-End Object Detection with Transformers",
    "centernet": "CenterNet: Objects as Points",

    # 生成模型
    "gan": "Generative Adversarial Networks",
    "dcgan": "Deep Convolutional GAN",
    "wgan": "Wasserstein GAN",
    "stylegan": "A Style-Based Generator Architecture for Generative Adversarial Networks",
    "vae": "Autoencoding Variational Bayes",
    "ddpm": "Denoising Diffusion Probabilistic Models",
    "ddim": "Diffusion Models Beat GANs on Image Synthesis",
    "score": "Score-Based Generative Modeling through Stochastic Differential Equations",

    # Transformer/LLM
    "bert": "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding",
    "gpt": "Improving Language Understanding by Generative Pre-Training",
    "gpt2": "Language Models are Unsupervised Multitask Learners",
    "gpt3": "Language Models are Few-Shot Learners",
    "t5": "Exploring the Limits of Transfer Learning with a Unified Text-to-Text Transformer",
    "llama": "LLaMA: Open and Efficient Foundation Language Models",
    "llama2": "Llama 2: Open Foundation and Fine-Tuned Chat Models",
    "chatgpt": "ChatGPT",
    "gpt4": "GPT-4 Technical Report",

    # 多模态
    "clip": "Learning Transferable Visual Models From Natural Language Supervision",
    "blip": "BLIP: Bootstrapping Language-Image Pre-training",
    "blip2": "BLIP-2: Bootstrapping Language-Image Pre-training with Frozen Image Encoders and LMs",
    "llava": "Large Language and Vision Assistant",
    "instructblip": "InstructBLIP: Towards General-purpose Vision-Language Models",
    "minigpt4": "MiniGPT-4: Enhancing Vision Language Understanding with One Single Projection Layer",

    # 强化学习
    "ppo": "Proximal Policy Optimization Algorithms",
    "a2c": "Asynchronous Methods for Deep Reinforcement Learning",
    "dqn": "Human-level control through deep reinforcement learning",
    "ddpg": "Continuous control with deep reinforcement learning",
    "td3": "Addressing Function Approximation Error in Actor-Critic Methods",
    "sac": "Soft Actor-Critic: Off-Policy Maximum Entropy Deep Reinforcement Learning",

    # 自监督/对比学习
    "simclr": "A Simple Framework for Contrastive Learning of Visual Representations",
    "moco": "Momentum Contrast for Unsupervised Visual Representation Learning",
    "byol": "Bootstrap Your Own Latent: A New Approach to Self-Supervised Learning",
    "swav": "Unsupervised Learning of Visual Features through Contrastive Clustering",
    "mae": "Masked Autoencoders Are Scalable Vision Learners",
    "simmim": "SimMIM: A Simple Framework for Masked Image Modeling",

    # 优化/训练技术
    "adam": "Adam: A Method for Stochastic Optimization",
    "adamw": "Decoupled Weight Decay Regularization",
    "dropout": "Dropout: A Simple Way to Prevent Neural Networks from Overfitting",
    "layer norm": "Layer Normalization",

    # 其他
    "unet": "U-Net: Convolutional Networks for Biomedical Image Segmentation",
    "pix2pix": "Image-to-Image Translation with Conditional Adversarial Networks",
    "cyclegan": "Unpaired Image-to-Image Translation using Cycle-Consistent Adversarial Networks",
    "inception": "Going Deeper with Convolutions",
}


class SmartInputStep(WorkflowStep):
    """智能输入处理步骤

    处理用户输入，自动识别并补充文献资源。
    """

    def __init__(
        self,
        auto_search: bool = True,
        max_auto_papers: int = 5,
        known_arxiv_titles: Optional[Dict[str, str]] = None,
    ):
        """初始化智能输入处理器

        Args:
            auto_search: 是否自动搜索补充文献
            max_auto_papers: 自动搜索的最大文献数量
            known_arxiv_titles: 已知的中文 arXiv ID 到标题的映射
        """
        super().__init__(
            name="smart_input",
            description="智能解析用户输入，识别关键词并自动搜索补充文献"
        )
        self.auto_search = auto_search
        self.max_auto_papers = max_auto_papers
        self.known_arxiv_titles = known_arxiv_titles or {}

    def execute(self, context: WorkflowContext) -> Dict[str, Any]:
        """执行智能输入处理

        Returns:
            {
                "paper_sources": List[str] - 解析出的文献源
                "keywords": List[str] - 提取的关键词
                "auto_search_query": str - 自动搜索查询词
                "has_local_files": bool - 是否包含本地文件
                "has_arxiv_ids": bool - 是否包含 arXiv ID
            }
        """
        # 从配置和状态中获取用户输入
        user_input = self._get_user_input(context)

        if not user_input and not self._has_existing_sources(context):
            raise ValueError(
                "No user input provided. Please provide research topic, keywords, "
                "arXiv URLs/IDs, or local file paths."
            )

        # 解析输入
        parsed = self._parse_input(user_input, context)

        # 存储解析结果到上下文
        context.set_state("paper_sources", parsed["paper_sources"])
        context.set_state("research_keywords", parsed["keywords"])
        context.set_state("auto_search_query", parsed["auto_search_query"])
        context.set_state("smart_input_processed", True)

        logger.info(f"SmartInput processed: {len(parsed['paper_sources'])} sources, "
                    f"keywords: {parsed['keywords']}")

        return parsed

    def validate(self, context: WorkflowContext) -> List[str]:
        """验证输入"""
        errors = []

        user_input = self._get_user_input(context)
        has_sources = self._has_existing_sources(context)

        if not user_input and not has_sources:
            errors.append(
                "No user input provided. Please provide research topic, keywords, "
                "arXiv URLs/IDs, or local file paths."
            )

        return errors

    def _get_user_input(self, context: WorkflowContext) -> Optional[str]:
        """从上下文中获取用户输入"""
        # 优先从 params 获取
        if input_text := context.config.get("input", ""):
            return input_text
        if input_text := context.config.get("topic", ""):
            return input_text
        if input_text := context.config.get("research_direction", ""):
            return input_text
        if input_text := context.config.get("description", ""):
            return input_text

        # 兼容旧的 papers 参数（字符串）
        if papers := context.config.get("papers", ""):
            if isinstance(papers, str):
                return papers
            if isinstance(papers, list):
                return "\n".join(str(p) for p in papers)

        return None

    def _has_existing_sources(self, context: WorkflowContext) -> bool:
        """检查是否已有文献源"""
        sources = context.get_state("paper_sources", [])
        config_sources = context.config.get("paper_sources", [])
        return bool(sources or config_sources)

    def _parse_input(
        self, user_input: Optional[str], context: WorkflowContext
    ) -> Dict[str, Any]:
        """解析用户输入"""
        paper_sources: List[str] = []
        keywords: List[str] = []
        auto_search_queries: List[str] = []

        if not user_input:
            # 尝试从已有配置获取
            paper_sources = context.config.get("paper_sources", [])
            return {
                "paper_sources": paper_sources,
                "keywords": keywords,
                "auto_search_query": "",
                "has_local_files": any(self._is_local_path(s) for s in paper_sources),
                "has_arxiv_ids": any(self._is_arxiv_id(s) for s in paper_sources),
            }

        # 按行分割处理
        lines = user_input.strip().split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 1. 检查是否是 arXiv URL
            if self._is_arxiv_url(line):
                paper_sources.append(self._normalize_arxiv_url(line))
                continue

            # 2. 检查是否是本地文件路径
            if self._is_local_path(line):
                if os.path.exists(line):
                    paper_sources.append(line)
                else:
                    logger.warning(f"Local file not found: {line}")
                continue

            # 3. 尝试解析为算法/领域关键词
            parsed_keywords = self._extract_keywords(line)
            keywords.extend(parsed_keywords)

            # 4. 如果看起来像自然语言描述，加入自动搜索
            if self._is_natural_language(line):
                auto_search_queries.append(line)

        # 如果有关键词但没有 arXiv 源，扩展关键词用于搜索
        if keywords and not paper_sources:
            search_query = " ".join(keywords[:5])
            auto_search_queries.append(search_query)

        # 去重
        paper_sources = list(dict.fromkeys(paper_sources))
        keywords = list(dict.fromkeys(k for k in keywords if k))

        return {
            "paper_sources": paper_sources,
            "keywords": keywords,
            "auto_search_query": " OR ".join(auto_search_queries[:3]),
            "has_local_files": any(self._is_local_path(s) for s in paper_sources),
            "has_arxiv_ids": any(self._is_arxiv_id(s) for s in paper_sources),
        }

    def _extract_keywords(self, text: str) -> List[str]:
        """从文本中提取关键词"""
        keywords = []
        text_lower = text.lower()

        # 检查是否是已知算法
        for abbr, full_name in ALGORITHM_KEYWORDS.items():
            if abbr in text_lower:
                keywords.append(abbr.upper() if len(abbr) <= 4 else abbr)
                # 同时添加可能的缩写
                if len(abbr) <= 4:
                    keywords.append(abbr.upper())

        # 检查研究领域缩写
        for abbr, domains in DOMAIN_KEYWORDS.items():
            if abbr.lower() in text_lower:
                keywords.append(abbr.upper() if len(abbr) <= 4 else abbr)
                # 添加相关领域词
                for domain in domains[:2]:
                    # 取第一个词作为简短关键词
                    short = domain.split()[0]
                    if len(short) >= 3:
                        keywords.append(short.capitalize())

        # 提取连续的字母数字组合（可能的缩写或术语）
        abbr_pattern = r'\b([A-Z]{2,8}|[a-z]{2,6})\b'
        matches = re.findall(abbr_pattern, text)
        for match in matches:
            if match.lower() not in ['the', 'and', 'for', 'with', 'from', 'this', 'that']:
                keywords.append(match)

        # 提取技术术语模式
        tech_pattern = r'\b(\w+(?:-\w+)*(?:net|model|learning|network|transformer|gan|vae|diffusion))\b'
        tech_matches = re.findall(tech_pattern, text_lower)
        keywords.extend(tech_matches)

        return list(set(keywords))

    def _is_natural_language(self, text: str) -> bool:
        """判断是否是自然语言描述"""
        # 排除已是 URL、文件路径、关键词的内容
        if self._is_arxiv_url(text) or self._is_local_path(text):
            return False

        # 检查是否包含常见自然语言特征
        natural_language_indicators = [
            len(text.split()) >= 3,  # 至少3个词
            any(word in text.lower() for word in ['研究', '探索', '分析', '基于', '关于', '如何', 'what', 'how', 'research', 'explore', 'study', 'analyze']),
            text.lower().startswith(('我想', '我想研究', '我想探索', '研究', '探索', '分析', '基于', '关于')),
            '?' in text or '？' in text,
            len(text) > 20,  # 较长的描述性文本
        ]

        return sum(natural_language_indicators) >= 2

    def _is_arxiv_url(self, text: str) -> bool:
        """检查是否是 arXiv URL"""
        text = text.strip()
        patterns = [
            r'^https?://arxiv\.org/abs/\d+\.\d+',
            r'^https?://arxiv\.org/pdf/\d+\.\d+',
            r'^https?://export\.arxiv\.org/abs/\d+\.\d+',
        ]
        return any(re.match(p, text) for p in patterns)

    def _is_arxiv_id(self, text: str) -> bool:
        """检查是否是 arXiv ID"""
        text = text.strip()
        return bool(re.match(r'^\d+\.\d+$', text))

    def _normalize_arxiv_url(self, text: str) -> str:
        """标准化 arXiv URL"""
        text = text.strip()
        # 如果是 PDF URL，转换为 abs URL
        if '/pdf/' in text:
            text = text.replace('/pdf/', '/abs/')
        # 如果没有协议，添加 https
        if text.startswith('arxiv.org/'):
            text = 'https://' + text
        if text.startswith('export.arxiv.org/'):
            text = text.replace('export.arxiv.org/', 'arxiv.org/')
            text = 'https://' + text
        return text

    def _is_local_path(self, text: str) -> bool:
        """检查是否是本地文件路径"""
        text = text.strip()
        # Windows 或 Unix 路径
        if re.match(r'^[A-Za-z]:[/\\]', text):  # Windows 绝对路径
            return True
        if text.startswith('/') or text.startswith('~/'):  # Unix 绝对路径
            return True
        if text.startswith('./') or text.startswith('../'):  # 相对路径
            return True
        # 常见文件扩展名
        if any(text.lower().endswith(ext) for ext in ['.pdf', '.txt', '.md', '.tex', '.docx']):
            return True
        return False


class AutoArxivSearchStep(WorkflowStep):
    """自动 ArXiv 文献搜索步骤

    当用户只提供关键词时，自动搜索并补充相关文献。
    """

    def __init__(
        self,
        max_results: int = 5,
        search_by_keywords: bool = True,
    ):
        """初始化自动搜索步骤

        Args:
            max_results: 最大搜索结果数
            search_by_keywords: 是否通过关键词搜索
        """
        super().__init__(
            name="auto_arxiv_search",
            description="自动搜索 ArXiv 补充相关文献"
        )
        self.max_results = max_results
        self.search_by_keywords = search_by_keywords

    def execute(self, context: WorkflowContext) -> Dict[str, Any]:
        """执行自动搜索"""
        # 检查是否已有足够的文献
        existing_sources = context.get_state("paper_sources", [])
        existing_count = len(existing_sources)

        if existing_count >= 3:
            logger.info(f"Already have {existing_count} sources, skipping auto search")
            return {"auto_search_results": [], "skipped": True}

        # 获取关键词
        keywords = context.get_state("research_keywords", [])
        search_query = context.get_state("auto_search_query", "")

        if not keywords and not search_query:
            logger.info("No keywords for auto search")
            return {"auto_search_results": [], "skipped": True}

        # 组合搜索词
        query = search_query or " ".join(keywords[:5])
        logger.info(f"Auto searching arXiv for: {query}")

        try:
            results = self._search_arxiv(query)
        except Exception as e:
            logger.error(f"ArXiv search failed: {e}")
            results = []

        # 添加搜索结果
        new_sources = []
        for result in results[:self.max_results]:
            url = result.get("url") or result.get("arxiv_url")
            if url and url not in existing_sources:
                new_sources.append(url)

        # 更新上下文
        if new_sources:
            context.set_state("paper_sources", existing_sources + new_sources)
            context.set_state("auto_search_results", new_sources)
            logger.info(f"Added {len(new_sources)} papers from auto search")

        return {
            "auto_search_results": new_sources,
            "query": query,
            "skipped": len(new_sources) == 0,
        }

    def _search_arxiv(self, query: str) -> List[Dict[str, Any]]:
        """搜索 arXiv API

        使用 arXiv OpenSearch API 搜索论文。
        """
        import urllib.parse
        import urllib.request
        import xml.etree.ElementTree as ET

        try:
            # 构建 arXiv API 查询
            base_url = "http://export.arxiv.org/api/query"
            params = urllib.parse.urlencode({
                "search_query": f"all:{query}",
                "start": 0,
                "max_results": self.max_results,
                "sortBy": "relevance",
                "sortOrder": "descending",
            })
            url = f"{base_url}?{params}"

            logger.info(f"Searching arXiv: {url}")

            with urllib.request.urlopen(url, timeout=10) as response:
                data = response.read().decode("utf-8")

            # 解析 XML 响应
            root = ET.fromstring(data)
            ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

            results = []
            for entry in root.findall("atom:entry", ns):
                title = entry.find("atom:title", ns)
                summary = entry.find("atom:summary", ns)
                link_elem = entry.find('atom:link[@title="pdf"]', ns)
                id_elem = entry.find("atom:id", ns)

                # 提取 arXiv ID
                arxiv_id = ""
                if id_elem is not None:
                    arxiv_id = id_elem.text.split("/")[-1]

                # 构建 arXiv URL
                arxiv_url = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else ""

                results.append({
                    "title": title.text.strip().replace("\n", " ") if title is not None else "",
                    "abstract": summary.text.strip() if summary is not None else "",
                    "url": arxiv_url,
                    "arxiv_url": arxiv_url,
                    "arxiv_id": arxiv_id,
                })

            logger.info(f"ArXiv search returned {len(results)} results for query: {query}")
            return results

        except Exception as e:
            logger.error(f"ArXiv search failed: {e}")
            return []

    def validate(self, context: WorkflowContext) -> List[str]:
        """验证前提条件"""
        errors = []

        if not context.get_state("smart_input_processed", False):
            errors.append("SmartInputStep must run before AutoArxivSearchStep")

        return errors


__all__ = ["SmartInputStep", "AutoArxivSearchStep", "DOMAIN_KEYWORDS", "ALGORITHM_KEYWORDS"]
