from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


VoiceMode = Literal["scientific", "mystical"]
VoiceTone = Literal["straight", "balanced", "humorous"]
VoiceGuide = Literal["cat", "robot", "dog", "none"]
VoiceChannel = Literal["app_summary", "app_detail", "social_public", "web_dashboard", "notification"]


@dataclass(frozen=True)
class VoiceProfile:
    mode: VoiceMode = "scientific"
    tone: VoiceTone = "balanced"
    guide: VoiceGuide = "none"
    channel: VoiceChannel = "app_summary"

    @classmethod
    def app_summary_default(cls) -> "VoiceProfile":
        return cls(mode="scientific", tone="balanced", guide="none", channel="app_summary")

    @classmethod
    def public_playful(cls) -> "VoiceProfile":
        return cls(mode="scientific", tone="humorous", guide="none", channel="social_public")

    @property
    def humor_enabled(self) -> bool:
        return self.tone == "humorous" or self.channel == "social_public"

    @property
    def metaphor_ok(self) -> bool:
        return self.mode == "mystical" or self.channel == "social_public"

    @property
    def persona_strength(self) -> str:
        if self.guide == "none":
            return "none"
        if self.channel == "notification":
            return "very_light"
        if self.tone == "straight":
            return "light"
        return "light"

    def caution_line(self) -> str:
        if self.channel == "social_public":
            return "Watch the pattern, not the panic."
        if self.tone == "humorous" and self.guide == "robot":
            return "Useful pattern. Not a verdict."
        return "These are patterns to watch, not certainties."
