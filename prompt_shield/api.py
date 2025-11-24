import uuid
import logging
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic_settings import BaseSettings

from .models import CheckRequest, CheckResponse, ShieldResult
from .detector import PromptDetector
from .cache import CacheBackend, create_cache
from .storage import AttackStorage

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings from environment."""
    
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    redis_url: Optional[str] = None
    llm_provider: str = "openai"  # or "anthropic" or "openrouter"
    llm_model: Optional[str] = None
    api_key: Optional[str] = None  # Optional API key for this service
    db_path: str = "attacks.db"
    cache_ttl: int = 3600
    
    class Config:
        env_file = ".env"


# Global instances
settings: Optional[Settings] = None
detector: Optional[PromptDetector] = None
cache: Optional[CacheBackend] = None
storage: Optional[AttackStorage] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services on startup."""
    global settings, detector, cache, storage
    
    settings = Settings()
    
    # Validate we have at least one LLM key
    if not settings.openai_api_key and not settings.anthropic_api_key and not settings.openrouter_api_key:
        raise ValueError("At least one of OPENAI_API_KEY, ANTHROPIC_API_KEY, or OPENROUTER_API_KEY must be set")
    
    # Auto-select provider based on available key
    provider = settings.llm_provider
    if provider == "openai" and not settings.openai_api_key:
        provider = "openrouter" if settings.openrouter_api_key else "anthropic"
    elif provider == "anthropic" and not settings.anthropic_api_key:
        provider = "openrouter" if settings.openrouter_api_key else "openai"
    elif provider == "openrouter" and not settings.openrouter_api_key:
        provider = "openai" if settings.openai_api_key else "anthropic"
    
    detector = PromptDetector(
        provider=provider,
        openai_api_key=settings.openai_api_key,
        anthropic_api_key=settings.anthropic_api_key,
        openrouter_api_key=settings.openrouter_api_key,
        model=settings.llm_model,
    )
    
    cache = create_cache(settings.redis_url)
    storage = AttackStorage(settings.db_path)
    
    logger.info(f"PromptShield started with {provider} provider")
    yield
    
    logger.info("PromptShield shutting down")


app = FastAPI(
    title="PromptShield API",
    description="Prompt injection detection service",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def verify_api_key(x_api_key: Optional[str] = Header(None)):
    """Optional API key verification."""
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": "PromptShield API",
        "version": "0.1.0",
        "docs": "/docs",
        "endpoints": {
            "check": "POST /check - Analyze a prompt for attacks",
            "stats": "GET /stats - Attack statistics",
            "health": "GET /health - Health check",
        }
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "version": "0.1.0"}


@app.post("/check", response_model=CheckResponse, dependencies=[Depends(verify_api_key)])
async def check_prompt(request: CheckRequest):
    """
    Analyze a prompt for potential injection attacks.
    
    Returns safety assessment with confidence score and attack type.
    """
    request_id = str(uuid.uuid4())[:8]
    prompt_hash = PromptDetector.hash_prompt(request.prompt)
    
    # Check cache first
    cached_result = await cache.get(prompt_hash)
    if cached_result:
        logger.debug(f"[{request_id}] Cache hit for {prompt_hash}")
        return CheckResponse(result=cached_result, request_id=request_id)
    
    # Analyze with LLM
    result = await detector.analyze(request.prompt)
    
    # Cache result
    await cache.set(prompt_hash, result, settings.cache_ttl)
    
    # Log attacks for analysis
    if result.attack_detected:
        log_entry = PromptDetector.create_log_entry(request.prompt, result)
        storage.log_attack(log_entry)
        logger.info(
            f"[{request_id}] Attack detected: {result.attack_type.value} "
            f"(confidence: {result.confidence:.2f})"
        )
    
    return CheckResponse(result=result, request_id=request_id)


@app.get("/stats", dependencies=[Depends(verify_api_key)])
async def get_stats(days: int = 7):
    """Get attack statistics."""
    return storage.get_stats(days)


@app.get("/attacks", dependencies=[Depends(verify_api_key)])
async def get_attacks(limit: int = 100):
    """Get recent attack logs."""
    return storage.get_recent_attacks(limit)


@app.get("/repeat-offenders", dependencies=[Depends(verify_api_key)])
async def get_repeat_offenders(min_count: int = 3, days: int = 7):
    """Find repeated attack patterns."""
    return storage.get_repeat_offenders(min_count, days)


def create_app() -> FastAPI:
    """Factory function for creating the app."""
    return app
