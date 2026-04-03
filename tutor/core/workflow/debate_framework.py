"""Enhanced Debate Framework for Research Idea Evaluation

Provides multi-dimensional debate analysis with:
- 5 scoring dimensions: METHODOLOGY, DATA_SUPPORT, GENERALIZABILITY, INNOVATION, REPRODUCIBILITY
- Argument quality evaluation (credibility, relevance, logic)
- Cross-examination / rebuttal generation
- Visualization data for radar charts and timelines
- Multi-model support (different LLM for different positions)

Inspired by RAP's debate_framework.py and standardized_debate.py.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class DimensionType(Enum):
    """Five core debate dimensions for research idea evaluation."""
    METHODOLOGY = "methodology"       # 方法论有效性
    DATA_SUPPORT = "data_support"     # 数据支持度
    GENERALIZABILITY = "generalizability"  # 结论普适性
    INNOVATION = "innovation"        # 创新性
    REPRODUCIBILITY = "reproducibility"  # 可复现性


class ArgumentQuality(Enum):
    """Argument quality grade."""
    EXCELLENT = 5
    GOOD = 4
    FAIR = 3
    POOR = 2
    INVALID = 1


@dataclass
class Argument:
    """A single argument in a debate."""
    content: str
    source: str          # Source (e.g. "literature", "web", "reasoning")
    dimension: DimensionType
    # Quality scores (0-1)
    credibility_score: float = 0.0
    relevance_score: float = 0.0
    logic_score: float = 0.0
    # Evidence and citations
    evidence: List[str] = field(default_factory=list)
    citations: List[str] = field(default_factory=list)
    # Evaluated quality grade
    quality: ArgumentQuality = ArgumentQuality.FAIR
    # Metadata
    speaker: str = ""
    round: int = 0

    def overall_score(self) -> float:
        return (self.credibility_score + self.relevance_score + self.logic_score) / 3


@dataclass
class DebatePosition:
    """A debate position with multiple arguments."""
    position_id: str
    name: str           # e.g. "Innovator", "Skeptic"
    description: str
    arguments: List[Argument] = field(default_factory=list)
    dimension_scores: Dict[DimensionType, float] = field(default_factory=dict)
    overall_score: float = 0.0

    def add_argument(self, arg: Argument):
        self.arguments.append(arg)

    def compute_dimension_scores(self):
        """Compute average score per dimension from all arguments."""
        for dim in DimensionType:
            dim_args = [a for a in self.arguments if a.dimension == dim]
            if dim_args:
                self.dimension_scores[dim] = sum(a.overall_score() for a in dim_args) / len(dim_args)
            else:
                self.dimension_scores[dim] = 0.0
        if self.dimension_scores:
            self.overall_score = sum(self.dimension_scores.values()) / len(self.dimension_scores)


@dataclass
class DebateRound:
    """A single round of debate with rebuttals."""
    round_number: int
    position_arguments: Dict[str, List[Argument]] = field(default_factory=dict)
    rebuttals: List[Tuple[str, str, str]] = field(default_factory=list)  # (from, to, content)
    round_scores: Dict[str, float] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat() + "Z")


@dataclass
class DebateResult:
    """Complete debate result with visualization data."""
    debate_id: str
    topic: str
    positions: List[DebatePosition] = field(default_factory=list)
    rounds: List[DebateRound] = field(default_factory=list)
    final_conclusion: str = ""
    confidence_level: str = "unknown"   # high / medium / low
    # Visualization payload
    radar_chart: Dict[str, Any] = field(default_factory=dict)
    timeline: List[Dict[str, Any]] = field(default_factory=list)
    quality_distribution: Dict[str, int] = field(default_factory=dict)
    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat() + "Z")
    total_duration: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "debate_id": self.debate_id,
            "topic": self.topic,
            "created_at": self.created_at,
            "total_duration": self.total_duration,
            "confidence_level": self.confidence_level,
            "final_conclusion": self.final_conclusion,
            "positions": [
                {
                    "name": p.name,
                    "description": p.description,
                    "overall_score": p.overall_score,
                    "dimension_scores": {d.value: s for d, s in p.dimension_scores.items()},
                }
                for p in self.positions
            ],
            "rounds": [
                {
                    "round_number": r.round_number,
                    "round_scores": r.round_scores,
                    "rebuttal_count": len(r.rebuttals),
                }
                for r in self.rounds
            ],
            "quality_distribution": self.quality_distribution,
            "visualization": {
                "radar_chart": self.radar_chart,
                "timeline": self.timeline,
            },
        }


class ArgumentEvaluator:
    """Evaluates argument quality across credibility, relevance, and logic."""

    AUTHORITATIVE_SOURCES = {"nature", "science", "ieee", "acm", "arxiv", "cvpr", "iclr", "neurips"}

    @classmethod
    def evaluate(cls, argument: Argument, topic: str = "") -> ArgumentQuality:
        """Evaluate an argument and set its quality grade."""
        argument.credibility_score = cls._evaluate_credibility(argument)
        argument.relevance_score = cls._evaluate_relevance(argument, topic)
        argument.logic_score = cls._evaluate_logic(argument)

        overall = argument.overall_score()
        if overall >= 0.8:
            argument.quality = ArgumentQuality.EXCELLENT
        elif overall >= 0.65:
            argument.quality = ArgumentQuality.GOOD
        elif overall >= 0.5:
            argument.quality = ArgumentQuality.FAIR
        elif overall >= 0.35:
            argument.quality = ArgumentQuality.POOR
        else:
            argument.quality = ArgumentQuality.INVALID
        return argument.quality

    @staticmethod
    def _evaluate_credibility(argument: Argument) -> float:
        score = 0.5
        src_lower = argument.source.lower()
        if any(s in src_lower for s in ArgumentEvaluator.AUTHORITATIVE_SOURCES):
            score += 0.2
        if len(argument.evidence) >= 3:
            score += 0.15
        elif len(argument.evidence) >= 1:
            score += 0.1
        if len(argument.citations) >= 2:
            score += 0.15
        elif len(argument.citations) >= 1:
            score += 0.1
        return min(score, 1.0)

    @staticmethod
    def _evaluate_relevance(argument: Argument, topic: str) -> float:
        if not topic:
            return 0.5
        topic_words = set(topic.lower().split())
        content_words = set(argument.content.lower().split())
        if not topic_words:
            return 0.5
        overlap = len(topic_words & content_words) / len(topic_words)
        return min(overlap * 1.5, 1.0)

    @staticmethod
    def _evaluate_logic(argument: Argument) -> float:
        score = 0.5
        content = argument.content.lower()
        logic_words = [
            "because", "therefore", "thus", "hence", "since",
            "因为", "所以", "因此", "由于", "导致",
            "because", "therefore", "thus", "hence",
        ]
        count = sum(1 for w in logic_words if w in content)
        if count >= 2:
            score += 0.2
        elif count >= 1:
            score += 0.1
        if any(w in content for w in ["evidence", "data", "实验", "结果"]):
            score += 0.15
        if "conclusion" in content or "结论" in content:
            score += 0.1
        return min(score, 1.0)


class MultiDimensionalDebate:
    """
    Orchestrates multi-dimensional debate with cross-examination.

    Each position is assigned a dimension to defend, and all positions
    engage in cross-examination rounds. Produces structured DebateResult
    with visualization data.
    """

    def __init__(
        self,
        topic: str,
        positions: List[DebatePosition],
        max_rounds: int = 3,
        model_gateway=None,
    ):
        self.topic = topic
        self.positions = {p.position_id: p for p in positions}
        self.max_rounds = max_rounds
        self.model_gateway = model_gateway
        self.rounds: List[DebateRound] = []
        self.evaluator = ArgumentEvaluator()
        self.debate_id = f"debate_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    async def conduct_round(self, round_number: int) -> DebateRound:
        """Execute one round of debate with cross-examination."""
        debate_round = DebateRound(round_number=round_number)

        # Each position presents arguments
        for pos_id, position in self.positions.items():
            role_args = [a for a in position.arguments if a.round == round_number]
            if role_args:
                debate_round.position_arguments[pos_id] = role_args
            else:
                debate_round.position_arguments[pos_id] = []

            # Evaluate
            for arg in debate_round.position_arguments[pos_id]:
                self.evaluator.evaluate(arg, self.topic)

            if debate_round.position_arguments[pos_id]:
                scores = [a.overall_score() for a in debate_round.position_arguments[pos_id]]
                debate_round.round_scores[pos_id] = sum(scores) / len(scores)

        # Generate cross-examination rebuttals
        debate_round.rebuttals = self._generate_rebuttals(debate_round)

        self.rounds.append(debate_round)
        return debate_round

    def _generate_rebuttals(self, debate_round: DebateRound) -> List[Tuple[str, str, str]]:
        """Generate rebuttals: strong positions challenge weak ones."""
        rebuttals = []
        sorted_pos = sorted(
            debate_round.round_scores.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        if len(sorted_pos) >= 2:
            strong_id = sorted_pos[0][0]
            weak_id = sorted_pos[-1][0]
            rebuttals.append((
                strong_id,
                weak_id,
                f"Position '{self.positions[strong_id].name}' challenges '{self.positions[weak_id].name}' "
                f"on evidence sufficiency and methodology.",
            ))
        return rebuttals

    def generate_conclusion(self) -> str:
        """Generate final debate conclusion with dimension scores."""
        for position in self.positions.values():
            position.compute_dimension_scores()

        sorted_positions = sorted(
            self.positions.values(),
            key=lambda p: p.overall_score,
            reverse=True,
        )
        if not sorted_positions:
            return "辩论未产生有效结论"

        winner = sorted_positions[0]
        lines = [
            f"辩论结论：",
            f"============",
            f"获胜立场：{winner.name}",
            f"总体评分：{winner.overall_score:.2f}/1.0",
            "",
            "各维度评分：",
        ]
        for dim, score in winner.dimension_scores.items():
            lines.append(f"  - {dim.value}: {score:.2f}")
        lines.append(f"\n置信度：{self._compute_confidence()}")
        return "\n".join(lines)

    def _compute_confidence(self) -> str:
        if len(self.positions) < 2:
            return "low"
        scores = [p.overall_score for p in self.positions.values()]
        if not scores:
            return "low"
        sorted_scores = sorted(scores, reverse=True)
        gap = sorted_scores[0] - (sorted_scores[1] if len(sorted_scores) > 1 else 0)
        if gap > 0.3:
            return "high"
        elif gap > 0.15:
            return "medium"
        return "low"

    def build_visualization(self) -> Dict[str, Any]:
        """Build radar chart and timeline data for visualization."""
        # Radar chart: each position's scores across 5 dimensions
        radar = {
            "dimensions": [d.value for d in DimensionType],
            "positions": [],
        }
        for pos in self.positions.values():
            pos.compute_dimension_scores()
            radar["positions"].append({
                "name": pos.name,
                "scores": [pos.dimension_scores.get(d, 0.0) for d in DimensionType],
            })

        # Timeline: round-by-round scores
        timeline = []
        for r in self.rounds:
            timeline.append({
                "round": r.round_number,
                "scores": r.round_scores,
                "rebuttals": len(r.rebuttals),
            })

        # Quality distribution
        quality_dist = {"excellent": 0, "good": 0, "fair": 0, "poor": 0, "invalid": 0}
        for pos in self.positions.values():
            for arg in pos.arguments:
                quality_dist[arg.quality.name.lower()] += 1

        return {
            "radar_chart": radar,
            "timeline": timeline,
            "quality_distribution": quality_dist,
        }

    async def run(self) -> DebateResult:
        """Execute the full multi-round debate and return structured result."""
        for round_num in range(1, self.max_rounds + 1):
            logger.info(f"Executing debate round {round_num}")
            await self.conduct_round(round_num)

        conclusion = self.generate_conclusion()
        visualization = self.build_visualization()

        result = DebateResult(
            debate_id=self.debate_id,
            topic=self.topic,
            positions=list(self.positions.values()),
            rounds=self.rounds,
            final_conclusion=conclusion,
            confidence_level=self._compute_confidence(),
            radar_chart=visualization["radar_chart"],
            timeline=visualization["timeline"],
            quality_distribution=visualization["quality_distribution"],
        )
        return result


def build_research_debate_positions(
    topic: str,
    idea: str,
    literature_context: str,
) -> List[DebatePosition]:
    """
    Build 4 debate positions for a research idea.
    Each position focuses on a different evaluation dimension.
    """
    base_context = f"Topic: {topic}\n\nLiterature context:\n{literature_context}\n\nIdea under debate:\n{idea}"

    positions = [
        DebatePosition(
            position_id="innovator",
            name="Innovator",
            description="Creative researcher proposing novel approaches",
            arguments=[
                Argument(
                    content=f"Proposes innovative extensions to: {idea[:200]}",
                    source="reasoning",
                    dimension=DimensionType.INNOVATION,
                    speaker="Innovator",
                    round=0,
                ),
            ],
        ),
        DebatePosition(
            position_id="skeptic",
            name="Skeptic",
            description="Critical thinker challenging assumptions and evidence",
            arguments=[
                Argument(
                    content=f"Questions methodology and evidence for: {idea[:200]}",
                    source="reasoning",
                    dimension=DimensionType.DATA_SUPPORT,
                    speaker="Skeptic",
                    round=0,
                ),
            ],
        ),
        DebatePosition(
            position_id="pragmatist",
            name="Pragmatist",
            description="Practical researcher focused on feasibility",
            arguments=[
                Argument(
                    content=f"Evaluates feasibility of: {idea[:200]}",
                    source="reasoning",
                    dimension=DimensionType.REPRODUCIBILITY,
                    speaker="Pragmatist",
                    round=0,
                ),
            ],
        ),
        DebatePosition(
            position_id="expert",
            name="Domain Expert",
            description="Expert providing state-of-the-art insights",
            arguments=[
                Argument(
                    content=f"Contextualizes within existing literature: {idea[:200]}",
                    source="literature",
                    dimension=DimensionType.METHODOLOGY,
                    speaker="Expert",
                    round=0,
                ),
            ],
        ),
    ]
    return positions
