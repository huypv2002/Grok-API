"""Data models for X Grok Video Generator"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional
from uuid import uuid4

@dataclass
class Account:
    email: str
    password: str  # encrypted
    status: Literal["logged_in", "logged_out", "error"] = "logged_out"
    cookies: Optional[dict] = None
    fingerprint_id: str = field(default_factory=lambda: str(uuid4()))
    last_login: Optional[datetime] = None
    error_message: Optional[str] = None

@dataclass
class VideoSettings:
    aspect_ratio: str = "16:9"  # 2:3, 3:2, 1:1, 9:16, 16:9
    video_length: Literal[6, 10] = 6
    resolution: Literal["480p", "720p"] = "480p"
    
    def validate(self) -> bool:
        return (
            self.aspect_ratio in ["2:3", "3:2", "1:1", "9:16", "16:9"] and
            self.video_length in [6, 10] and
            self.resolution in ["480p", "720p"]
        )

@dataclass
class VideoTask:
    id: str = field(default_factory=lambda: str(uuid4()))
    account_email: str = ""
    prompt: str = ""
    image_path: Optional[str] = None  # Path to image for image-to-video mode
    settings: VideoSettings = field(default_factory=VideoSettings)
    status: Literal["pending", "creating", "completed", "failed"] = "pending"
    post_id: Optional[str] = None
    conversation_id: Optional[str] = None
    media_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    output_path: Optional[str] = None
    user_data_dir: Optional[str] = None  # Browser profile dir for download
    account_cookies: Optional[dict] = None  # Account cookies for download
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
