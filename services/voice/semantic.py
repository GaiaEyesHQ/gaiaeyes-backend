from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Literal


ClaimStrength = Literal["observe_only", "may_notice", "likely_notice", "strong_repeat_pattern"]
ConfidenceLevel = Literal["low", "moderate", "high"]
UrgencyLevel = Literal["quiet", "notable", "watch", "high"]


@dataclass(frozen=True)
class SemanticAction:
    key: str
    priority: int
    reason: str
    label: str


@dataclass(frozen=True)
class SemanticGuardrails:
    confidence_overall: ConfidenceLevel = "low"
    claim_strength: ClaimStrength = "observe_only"
    evidence_basis: List[str] = field(default_factory=list)
    medical_disclaimer_level: str = "light"
    avoid_fear_language: bool = True
    avoid_causal_language: bool = True
    max_urgency: UrgencyLevel = "quiet"


@dataclass(frozen=True)
class SemanticRenderHints:
    preferred_summary_length: str = "short"
    preferred_detail_sections: List[str] = field(default_factory=list)
    humor_ok: bool = False
    metaphor_ok: bool = False
    persona_strength: str = "light"


@dataclass(frozen=True)
class SemanticPayload:
    schema_version: str
    kind: str
    date: str
    user_context: Dict[str, Any] = field(default_factory=dict)
    facts: Dict[str, Any] = field(default_factory=dict)
    interpretation: Dict[str, Any] = field(default_factory=dict)
    actions: Dict[str, Any] = field(default_factory=dict)
    guardrails: SemanticGuardrails = field(default_factory=SemanticGuardrails)
    render_hints: SemanticRenderHints = field(default_factory=SemanticRenderHints)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
