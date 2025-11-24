import sqlite3
import logging
from typing import Optional
from datetime import datetime, timedelta

from .models import AttackLog, AttackType

logger = logging.getLogger(__name__)


class AttackStorage:
    """SQLite storage for attack logs and analysis."""
    
    def __init__(self, db_path: str = "attacks.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS attacks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    prompt_hash TEXT NOT NULL,
                    prompt_preview TEXT,
                    attack_type TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    reason TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_attacks_timestamp 
                ON attacks(timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_attacks_type 
                ON attacks(attack_type)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_attacks_hash 
                ON attacks(prompt_hash)
            """)
            conn.commit()
    
    def log_attack(self, log: AttackLog):
        """Store an attack log entry."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO attacks 
                    (timestamp, prompt_hash, prompt_preview, attack_type, confidence, reason)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        log.timestamp,
                        log.prompt_hash,
                        log.prompt_preview,
                        log.attack_type.value,
                        log.confidence,
                        log.reason,
                    ),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to log attack: {e}")
    
    def get_stats(self, days: int = 7) -> dict:
        """Get attack statistics for the last N days."""
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # Total attacks
            total = conn.execute(
                "SELECT COUNT(*) as count FROM attacks WHERE timestamp >= ?",
                (since,),
            ).fetchone()["count"]
            
            # By type
            by_type = conn.execute(
                """
                SELECT attack_type, COUNT(*) as count 
                FROM attacks 
                WHERE timestamp >= ?
                GROUP BY attack_type
                ORDER BY count DESC
                """,
                (since,),
            ).fetchall()
            
            # High confidence attacks
            high_confidence = conn.execute(
                """
                SELECT COUNT(*) as count 
                FROM attacks 
                WHERE timestamp >= ? AND confidence >= 0.8
                """,
                (since,),
            ).fetchone()["count"]
            
            return {
                "period_days": days,
                "total_attacks": total,
                "high_confidence_attacks": high_confidence,
                "by_type": {row["attack_type"]: row["count"] for row in by_type},
            }
    
    def get_recent_attacks(self, limit: int = 100) -> list[dict]:
        """Get recent attack logs."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM attacks 
                ORDER BY timestamp DESC 
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            
            return [dict(row) for row in rows]
    
    def get_repeat_offenders(self, min_count: int = 3, days: int = 7) -> list[dict]:
        """Find prompt hashes that appear multiple times (possible automated attacks)."""
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT prompt_hash, prompt_preview, COUNT(*) as count,
                       MAX(confidence) as max_confidence
                FROM attacks 
                WHERE timestamp >= ?
                GROUP BY prompt_hash
                HAVING count >= ?
                ORDER BY count DESC
                """,
                (since, min_count),
            ).fetchall()
            
            return [dict(row) for row in rows]
