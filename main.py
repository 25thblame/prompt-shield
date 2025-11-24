"""
PromptShield API Server

Run with:
    uvicorn main:app --reload --port 8000
    
Or:
    python main.py
"""

import uvicorn
from prompt_shield.api import app

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
