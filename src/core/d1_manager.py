"""Cloudflare D1 Manager - Sync accounts & history to Cloudflare D1 via Wrangler CLI"""
import json
import subprocess
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class D1Manager:
    """Manage Cloudflare D1 database via wrangler CLI (already authenticated)."""
    
    def __init__(self, database_name: str = "grok-video-db"):
        self.database_name = database_name
        self._connected = False
        self._database_id: Optional[str] = None
    
    def _run_wrangler(self, args: List[str], timeout: int = 30) -> Optional[str]:
        """Run wrangler command and return stdout."""
        cmd = ["wrangler"] + args
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout
            )
            if result.returncode != 0:
                logger.error(f"[D1] wrangler error: {result.stderr.strip()}")
                return None
            return result.stdout.strip()
        except FileNotFoundError:
            logger.error("[D1] wrangler not found in PATH")
            return None
        except subprocess.TimeoutExpired:
            logger.error("[D1] wrangler command timed out")
            return None
        except Exception as e:
            logger.error(f"[D1] wrangler error: {e}")
            return None
    
    def test_connection(self) -> tuple[bool, str]:
        """Test wrangler D1 connection. Returns (success, message)."""
        output = self._run_wrangler(["d1", "list", "--json"])
        if output is None:
            return False, "Không thể kết nối wrangler. Kiểm tra cài đặt."
        
        try:
            databases = json.loads(output)
            # Tìm database theo tên
            for db in databases:
                if db.get("name") == self.database_name:
                    self._database_id = db.get("uuid")
                    self._connected = True
                    return True, f"Đã kết nối: {self.database_name} ({self._database_id[:8]}...)"
            
            # Database chưa tồn tại
            db_names = [db.get("name", "?") for db in databases]
            return False, f"Database '{self.database_name}' không tìm thấy. Có: {', '.join(db_names) or 'trống'}"
        except json.JSONDecodeError:
            return False, f"Lỗi parse JSON từ wrangler"
    
    def create_database(self) -> tuple[bool, str]:
        """Create D1 database if not exists."""
        output = self._run_wrangler(["d1", "create", self.database_name, "--json"])
        if output is None:
            return False, "Không thể tạo database"
        
        try:
            data = json.loads(output)
            self._database_id = data.get("uuid")
            self._connected = True
            return True, f"Đã tạo database: {self.database_name}"
        except:
            # Có thể đã tồn tại
            ok, msg = self.test_connection()
            if ok:
                return True, f"Database đã tồn tại: {self.database_name}"
            return False, f"Lỗi tạo database: {output}"
    
    def init_tables(self) -> tuple[bool, str]:
        """Create tables in D1."""
        if not self._connected:
            ok, msg = self.test_connection()
            if not ok:
                return False, msg
        
        sql = """
        CREATE TABLE IF NOT EXISTS accounts (
            email TEXT PRIMARY KEY,
            password_encrypted TEXT NOT NULL,
            fingerprint_id TEXT,
            status TEXT DEFAULT 'logged_out',
            cookies TEXT,
            last_login TEXT,
            error_message TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        );
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
            error_message TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        );
        """
        
        output = self._run_wrangler([
            "d1", "execute", self.database_name,
            "--command", sql
        ])
        
        if output is None:
            return False, "Lỗi tạo tables"
        return True, "Đã tạo tables: accounts, video_history"
    
    def execute_sql(self, sql: str) -> Optional[List[Dict]]:
        """Execute SQL and return results."""
        if not self._connected:
            self.test_connection()
        
        output = self._run_wrangler([
            "d1", "execute", self.database_name,
            "--command", sql, "--json"
        ])
        
        if output is None:
            return None
        
        try:
            data = json.loads(output)
            if isinstance(data, list) and len(data) > 0:
                return data[0].get("results", [])
            return []
        except json.JSONDecodeError:
            return None
    
    def sync_account_to_d1(self, account_data: dict) -> bool:
        """Upsert account to D1."""
        email = account_data.get("email", "")
        pwd = account_data.get("password_encrypted", "")
        fid = account_data.get("fingerprint_id", "")
        status = account_data.get("status", "logged_out")
        cookies = json.dumps(account_data.get("cookies") or {})
        last_login = account_data.get("last_login") or ""
        error = account_data.get("error_message") or ""
        now = datetime.now().isoformat()
        
        # Escape single quotes
        for val in [email, pwd, fid, status, cookies, last_login, error]:
            val = val.replace("'", "''")
        
        sql = f"""
        INSERT OR REPLACE INTO accounts 
        (email, password_encrypted, fingerprint_id, status, cookies, last_login, error_message, updated_at)
        VALUES ('{email}', '{pwd}', '{fid}', '{status}', '{cookies}', '{last_login}', '{error}', '{now}')
        """
        
        result = self.execute_sql(sql)
        return result is not None
    
    def sync_history_to_d1(self, task_data: dict) -> bool:
        """Upsert video history to D1."""
        tid = task_data.get("id", "")
        email = task_data.get("account_email", "")
        prompt = task_data.get("prompt", "").replace("'", "''")
        ar = task_data.get("aspect_ratio", "16:9")
        vl = task_data.get("video_length", 6)
        res = task_data.get("resolution", "720p")
        status = task_data.get("status", "")
        pid = task_data.get("post_id") or ""
        url = task_data.get("media_url") or ""
        opath = task_data.get("output_path") or ""
        cat = task_data.get("created_at") or ""
        comp = task_data.get("completed_at") or ""
        err = (task_data.get("error_message") or "").replace("'", "''")
        now = datetime.now().isoformat()
        
        sql = f"""
        INSERT OR REPLACE INTO video_history
        (id, account_email, prompt, aspect_ratio, video_length, resolution, 
         status, post_id, media_url, output_path, created_at, completed_at, error_message, updated_at)
        VALUES ('{tid}', '{email}', '{prompt}', '{ar}', {vl}, '{res}',
                '{status}', '{pid}', '{url}', '{opath}', '{cat}', '{comp}', '{err}', '{now}')
        """
        
        result = self.execute_sql(sql)
        return result is not None
    
    def get_accounts_from_d1(self) -> Optional[List[Dict]]:
        """Get all accounts from D1."""
        return self.execute_sql("SELECT * FROM accounts ORDER BY email")
    
    def get_history_from_d1(self) -> Optional[List[Dict]]:
        """Get all history from D1."""
        return self.execute_sql("SELECT * FROM video_history ORDER BY created_at DESC LIMIT 500")
    
    def get_stats(self) -> Optional[Dict]:
        """Get D1 stats."""
        accounts = self.execute_sql("SELECT COUNT(*) as cnt FROM accounts")
        history = self.execute_sql("SELECT COUNT(*) as cnt FROM video_history")
        
        if accounts is None or history is None:
            return None
        
        return {
            "accounts": accounts[0]["cnt"] if accounts else 0,
            "videos": history[0]["cnt"] if history else 0,
        }
    
    @property
    def is_connected(self) -> bool:
        return self._connected
