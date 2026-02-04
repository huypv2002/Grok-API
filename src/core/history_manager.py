"""History Manager - SQLite storage for video history"""
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional
from .models import VideoTask, VideoSettings

DB_PATH = Path("data/history.db")

class HistoryManager:
    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(DB_PATH))
        self._create_table()
    
    def _create_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS video_history (
                id TEXT PRIMARY KEY,
                account_email TEXT,
                prompt TEXT,
                aspect_ratio TEXT,
                video_length INTEGER,
                resolution TEXT,
                status TEXT,
                post_id TEXT,
                media_url TEXT,
                output_path TEXT,
                created_at TEXT,
                completed_at TEXT,
                error_message TEXT
            )
        """)
        self.conn.commit()
    
    def add_history(self, task: VideoTask) -> None:
        self.conn.execute("""
            INSERT OR REPLACE INTO video_history 
            (id, account_email, prompt, aspect_ratio, video_length, resolution, 
             status, post_id, media_url, output_path, created_at, completed_at, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task.id,
            task.account_email,
            task.prompt,
            task.settings.aspect_ratio,
            task.settings.video_length,
            task.settings.resolution,
            task.status,
            task.post_id,
            task.media_url,
            task.output_path,
            task.created_at.isoformat() if task.created_at else None,
            task.completed_at.isoformat() if task.completed_at else None,
            task.error_message
        ))
        self.conn.commit()
    
    def get_all_history(self) -> list[VideoTask]:
        cursor = self.conn.execute("""
            SELECT * FROM video_history ORDER BY created_at DESC
        """)
        tasks = []
        for row in cursor.fetchall():
            task = VideoTask(
                id=row[0],
                account_email=row[1],
                prompt=row[2],
                settings=VideoSettings(
                    aspect_ratio=row[3],
                    video_length=row[4],
                    resolution=row[5]
                ),
                status=row[6],
                post_id=row[7],
                media_url=row[8],
                output_path=row[9],
                created_at=datetime.fromisoformat(row[10]) if row[10] else None,
                completed_at=datetime.fromisoformat(row[11]) if row[11] else None,
                error_message=row[12]
            )
            tasks.append(task)
        return tasks
    
    def delete_history(self, task_id: str) -> bool:
        cursor = self.conn.execute("DELETE FROM video_history WHERE id = ?", (task_id,))
        self.conn.commit()
        return cursor.rowcount > 0
    
    def close(self):
        self.conn.close()
