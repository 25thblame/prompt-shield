import httpx
from typing import Optional, Literal

from .models import ShieldResult, AttackType
from .detector import PromptDetector


class PromptShield:
    """
    PromptShield client for prompt injection detection.
    
    Can work in two modes:
    1. Local mode: Direct LLM calls (no server needed)
    2. Remote mode: Calls PromptShield API server
    
    Usage:
        # Local mode (direct LLM calls)
        shield = PromptShield(openai_api_key="sk-...")
        result = await shield.check("user input here")
        
        # Remote mode (via API server)
        shield = PromptShield(api_url="http://localhost:8000", api_key="...")
        result = await shield.check("user input here")
        
        if result.is_safe:
            # Process with main LLM
            pass
        elif result.should_block:
            # Block the request
            pass
        elif result.should_flag:
            # Allow but log for review
            pass
    """
    
    def __init__(
        self,
        # Remote mode
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        # Local mode
        openai_api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        openrouter_api_key: Optional[str] = None,
        provider: Literal["openai", "anthropic", "openrouter"] = "openai",
        model: Optional[str] = None,
        # Options
        timeout: float = 30.0,
    ):
        self.api_url = api_url
        self.api_key = api_key
        self.timeout = timeout
        
        if api_url:
            # Remote mode
            self._mode = "remote"
            self._client = httpx.AsyncClient(
                base_url=api_url,
                timeout=timeout,
                headers={"X-API-Key": api_key} if api_key else {},
            )
            self._detector = None
        else:
            # Local mode
            self._mode = "local"
            self._client = None
            self._detector = PromptDetector(
                provider=provider,
                openai_api_key=openai_api_key,
                anthropic_api_key=anthropic_api_key,
                openrouter_api_key=openrouter_api_key,
                model=model,
            )
    
    async def check(self, prompt: str, context: Optional[str] = None) -> ShieldResult:
        """
        Check a prompt for potential injection attacks.
        
        Args:
            prompt: The user input to analyze
            context: Optional context about expected use (helps reduce false positives)
            
        Returns:
            ShieldResult with safety assessment
        """
        if self._mode == "remote":
            return await self._check_remote(prompt, context)
        else:
            return await self._check_local(prompt)
    
    async def _check_remote(self, prompt: str, context: Optional[str]) -> ShieldResult:
        """Check via API server."""
        response = await self._client.post(
            "/check",
            json={"prompt": prompt, "context": context},
        )
        response.raise_for_status()
        data = response.json()
        return ShieldResult(**data["result"])
    
    async def _check_local(self, prompt: str) -> ShieldResult:
        """Check directly using local detector."""
        return await self._detector.analyze(prompt)
    
    async def check_sync(self, prompt: str, context: Optional[str] = None) -> ShieldResult:
        """Synchronous wrapper for check()."""
        import asyncio
        return asyncio.get_event_loop().run_until_complete(self.check(prompt, context))
    
    def check_blocking(self, prompt: str, context: Optional[str] = None) -> ShieldResult:
        """Blocking synchronous check."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(self.check(prompt, context))
    
    async def close(self):
        """Close the client."""
        if self._client:
            await self._client.aclose()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, *args):
        await self.close()


# Convenience function for one-off checks
async def check_prompt(
    prompt: str,
    openai_api_key: Optional[str] = None,
    anthropic_api_key: Optional[str] = None,
    openrouter_api_key: Optional[str] = None,
) -> ShieldResult:
    """
    Quick one-off prompt check.
    
    Usage:
        from prompt_shield import check_prompt
        
        result = await check_prompt("user input", openai_api_key="sk-...")
        # or with OpenRouter:
        result = await check_prompt("user input", openrouter_api_key="sk-or-...")
        if result.is_safe:
            # proceed
    """
    async with PromptShield(
        openai_api_key=openai_api_key,
        anthropic_api_key=anthropic_api_key,
        openrouter_api_key=openrouter_api_key,
    ) as shield:
        return await shield.check(prompt)
