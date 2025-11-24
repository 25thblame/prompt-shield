from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class AttackType(str, Enum):
    NONE = "none"
    PROMPT_EXTRACTION = "prompt_extraction"
    PROMPT_INJECTION = "prompt_injection"
    JAILBREAK = "jailbreak"
    INSTRUCTION_OVERRIDE = "instruction_override"
    ROLEPLAY_MANIPULATION = "roleplay_manipulation"
    UNKNOWN = "unknown"


class ShieldResult(BaseModel):
    """Result from prompt shield analysis."""
    
    is_safe: bool = Field(description="Whether the input is safe to process")
    attack_detected: bool = Field(description="Whether an attack was detected")
    attack_type: AttackType = Field(default=AttackType.NONE)
    confidence: float = Field(ge=0, le=1, description="Confidence score 0-1")
    reason: Optional[str] = Field(default=None, description="Explanation of detection")
    flagged: bool = Field(default=False, description="Flagged for review (low confidence)")
    cached: bool = Field(default=False, description="Result was from cache")
    
    @property
    def should_block(self) -> bool:
        """High confidence attack - should block."""
        return self.attack_detected and self.confidence >= 0.8
    
    @property
    def should_flag(self) -> bool:
        """Low confidence - allow but log for review."""
        return self.attack_detected and 0.4 <= self.confidence < 0.8


class CheckRequest(BaseModel):
    """Request to check a prompt."""
    
    prompt: str = Field(min_length=1, max_length=50000)
    context: Optional[str] = Field(default=None, description="Optional context about the expected use")


class CheckResponse(BaseModel):
    """API response for prompt check."""
    
    result: ShieldResult
    request_id: str


class AttackLog(BaseModel):
    """Logged attack for analysis."""
    
    timestamp: str
    prompt_hash: str
    prompt_preview: str  # First 200 chars
    attack_type: AttackType
    confidence: float
    reason: Optional[str]
