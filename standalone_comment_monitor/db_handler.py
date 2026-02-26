import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Any, Tuple
from supabase import create_client, Client
from dotenv import load_dotenv

# .env 로드
load_dotenv()

class CommentDatabase:
    """네이버 카페 댓글 데이터를 URL별로 저장하고 관리하는 SQLite 핸들러"""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(base_dir, "comments.db")
        
        self.db_path = db_path
        self._initialize_db()
        
        # Supabase 초기화
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_KEY")
        self.supabase: Client = None
        
        if self.supabase_url and self.supabase_key:
            try:
                self.supabase = create_client(self.supabase_url, self.supabase_key)
                print(f"DEBUG: [Supabase] Client initialized for {self.supabase_url}")
            except Exception as e:
                print(f"DEBUG: [Supabase Error] Initialization failed: {e}")

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _initialize_db(self):
        """테이블 초기화"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # WAL(Write-Ahead Logging) 모드 활성화 (실시간성 및 동시성 향상)
            cursor.execute('PRAGMA journal_mode = WAL;')
            cursor.execute('PRAGMA busy_timeout = 5000;')
            
            # 게시글(URL) 정보 테이블
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS posts (
                    url TEXT PRIMARY KEY,
                    title TEXT,
                    prizes TEXT,
                    winners TEXT,
                    allow_duplicates BOOLEAN DEFAULT 1,
                    is_active BOOLEAN DEFAULT 0,
                    last_comment_id TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 마이그레이션: 기존 테이블에 title, prizes 컬럼이 없는 경우 추가
            cursor.execute("PRAGMA table_info(posts)")
            columns = [info[1] for info in cursor.fetchall()]
            if 'title' not in columns:
                try:
                    cursor.execute("ALTER TABLE posts ADD COLUMN title TEXT")
                    print("DEBUG: [DB Migration] Added 'title' column to posts table.")
                except Exception as e:
                    print(f"DEBUG: [DB Migration Error] {e}")
            if 'prizes' not in columns:
                try:
                    cursor.execute("ALTER TABLE posts ADD COLUMN prizes TEXT")
                    print("DEBUG: [DB Migration] Added 'prizes' column to posts table.")
                except Exception as e:
                    print(f"DEBUG: [DB Migration Error] {e}")
            if 'winners' not in columns:
                try:
                    cursor.execute("ALTER TABLE posts ADD COLUMN winners TEXT")
                    print("DEBUG: [DB Migration] Added 'winners' column to posts table.")
                except Exception as e:
                    print(f"DEBUG: [DB Migration Error] {e}")
            if 'allow_duplicates' not in columns:
                try:
                    cursor.execute("ALTER TABLE posts ADD COLUMN allow_duplicates BOOLEAN DEFAULT 1")
                    print("DEBUG: [DB Migration] Added 'allow_duplicates' column to posts table.")
                except Exception as e:
                    print(f"DEBUG: [DB Migration Error] {e}")
            if 'is_active' not in columns:
                try:
                    cursor.execute("ALTER TABLE posts ADD COLUMN is_active BOOLEAN DEFAULT 0")
                    print("DEBUG: [DB Migration] Added 'is_active' column to posts table.")
                except Exception as e:
                    print(f"DEBUG: [DB Migration Error] {e}")

            # 참여자 및 댓글 수 테이블 (룰렛용 - 가치중치 포함)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS participants (
                    url TEXT,
                    author TEXT,
                    count INTEGER,
                    PRIMARY KEY (url, author),
                    FOREIGN KEY (url) REFERENCES posts (url) ON DELETE CASCADE
                )
            ''')

            # 모든 댓글 작성자 테이블 (모니터링용)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS commenters (
                    url TEXT,
                    author TEXT,
                    PRIMARY KEY (url, author),
                    FOREIGN KEY (url) REFERENCES posts (url) ON DELETE CASCADE
                )
            ''')
            conn.commit()

    def clear_data(self, url: str):
        """특정 URL의 데이터를 삭제 (새로운 수집 시 리셋용)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM participants WHERE url = ?", (url,))
            cursor.execute("DELETE FROM commenters WHERE url = ?", (url,))
            cursor.execute("DELETE FROM posts WHERE url = ?", (url,))
            conn.commit()
            print(f"DEBUG: [DB] Cleared data for URL: {url}")

    def _sync_to_supabase(self, url: str, participants_dict: Dict[str, int], last_comment_id: str, 
                         all_commenters: List[str] = None, title: str = None, prizes: str = None, 
                         winners: str = None, allow_duplicates: bool = None):
        """Supabase로 데이터 동기화"""
        if not self.supabase: return

        try:
            # 1. posts 테이블 업데이트 (upsert)
            post_data = {
                "url": url,
                "updated_at": datetime.now().isoformat()
            }
            if title is not None: post_data["title"] = title
            if prizes is not None: post_data["prizes"] = prizes
            if winners is not None: post_data["winners"] = winners
            if allow_duplicates is not None: post_data["allow_duplicates"] = allow_duplicates
            if last_comment_id and last_comment_id != '': post_data["last_comment_id"] = last_comment_id

            self.supabase.table("posts").upsert(post_data).execute()

            # 2. participants 테이블 업데이트
            if participants_dict is not None:
                # 기존 데이터 삭제 후 삽입 (Supabase는 delete + insert 가 가장 확실)
                self.supabase.table("participants").delete().eq("url", url).execute()
                if participants_dict:
                    p_batch = [{"url": url, "author": author, "count": count} for author, count in participants_dict.items()]
                    self.supabase.table("participants").insert(p_batch).execute()

            # 3. commenters 테이블 업데이트
            if all_commenters:
                # Insert or ignore (upsert with unique constraint)
                c_batch = [{"url": url, "author": author} for author in all_commenters]
                self.supabase.table("commenters").upsert(c_batch).execute()

            print(f"DEBUG: [Supabase Sync] Successfully synced data for {url}")
        except Exception as e:
            print(f"DEBUG: [Supabase Sync Error] {e}")

    def save_data(self, url: str, participants_dict: Dict[str, int], last_comment_id: str, 
                  all_commenters: List[str] = None, title: str = None, prizes: str = None, winners: str = None, allow_duplicates: bool = None):
        """수집된 데이터를 저장하거나 업데이트 (Local + Supabase)"""
        # 로컬 저장
        self._save_to_local(url, participants_dict, last_comment_id, all_commenters, title, prizes, winners, allow_duplicates)
        
        # Supabase 동기화
        self._sync_to_supabase(url, participants_dict, last_comment_id, all_commenters, title, prizes, winners, allow_duplicates)

    def _save_to_local(self, url: str, participants_dict: Dict[str, int], last_comment_id: str, 
                      all_commenters: List[str] = None, title: str = None, prizes: str = None, winners: str = None, allow_duplicates: bool = None):
        """SQLite 저장 로직"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO posts (url, title, prizes, winners, allow_duplicates, last_comment_id, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    title = COALESCE(excluded.title, posts.title),
                    prizes = COALESCE(excluded.prizes, posts.prizes),
                    winners = COALESCE(excluded.winners, posts.winners),
                    allow_duplicates = COALESCE(excluded.allow_duplicates, posts.allow_duplicates),
                    last_comment_id = CASE WHEN excluded.last_comment_id != '' THEN excluded.last_comment_id ELSE posts.last_comment_id END,
                    updated_at = excluded.updated_at
            ''', (url, title, prizes, winners, allow_duplicates, last_comment_id, datetime.now()))
            
            if participants_dict is not None and len(participants_dict) > 0:
                cursor.execute("DELETE FROM participants WHERE url = ?", (url,))
                for author, count in participants_dict.items():
                    cursor.execute('INSERT INTO participants (url, author, count) VALUES (?, ?, ?)', (url, author, count))
            elif participants_dict == {}:
                cursor.execute("DELETE FROM participants WHERE url = ?", (url,))
            
            if all_commenters:
                for author in all_commenters:
                    cursor.execute('INSERT OR IGNORE INTO commenters (url, author) VALUES (?, ?)', (url, author))
            
            conn.commit()
            print(f"DEBUG: [Local DB] Saved data for URL: {url}")

    def save_data(self, url: str, participants_dict: Dict[str, int], last_comment_id: str, 
                  all_commenters: List[str] = None, title: str = None, prizes: str = None, winners: str = None, allow_duplicates: bool = None):
        """수집된 데이터를 저장하거나 업데이트 (Local + Supabase)"""
        self._save_to_local(url, participants_dict, last_comment_id, all_commenters, title, prizes, winners, allow_duplicates)
        self._sync_to_supabase(url, participants_dict, last_comment_id, all_commenters, title, prizes, winners, allow_duplicates)

    def set_active_url(self, url: str):
        """특정 URL을 활성 이벤트로 설정 (Local + Supabase)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE posts SET is_active = 0")
            cursor.execute("UPDATE posts SET is_active = 1 WHERE url = ?", (url,))
            conn.commit()
            print(f"DEBUG: [Local DB] Set active URL: {url}")

        if self.supabase:
            try:
                self.supabase.table("posts").update({"is_active": False}).execute()
                self.supabase.table("posts").update({"is_active": True}).eq("url", url).execute()
                print(f"DEBUG: [Supabase] Active URL set: {url}")
            except Exception as e:
                print(f"DEBUG: [Supabase Sync Error] set_active_url: {e}")

    def get_active_url(self) -> str:
        """현재 활성화된 이벤트 URL을 가져옵니다 (Supabase 우선)."""
        if self.supabase:
            try:
                res = self.supabase.table("posts").select("url").eq("is_active", True).limit(1).execute()
                if res.data: return res.data[0]["url"]
                res = self.supabase.table("posts").select("url").order("updated_at", desc=True).limit(1).execute()
                if res.data: return res.data[0]["url"]
            except Exception as e:
                print(f"DEBUG: [Supabase Error] get_active_url: {e}")

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT url FROM posts WHERE is_active = 1 LIMIT 1")
            row = cursor.fetchone()
            if row: return row[0]
            cursor.execute("SELECT url FROM posts ORDER BY updated_at DESC LIMIT 1")
            row = cursor.fetchone()
            return row[0] if row else None

    def update_timestamp(self, url: str):
        """특정 URL의 updated_at 필드를 현재 시간으로 갱신합니다."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE posts SET updated_at = ? WHERE url = ?', (datetime.now(), url))
            conn.commit()

    def get_data(self, url: str) -> Tuple[Dict[str, int], List[str], str, str, str, str, bool]:
        """특정 URL의 저장된 데이터 조회 (Supabase 우선)"""
        participants = {}
        all_commenters = []
        last_id = None
        title = None
        prizes = None
        winners = None
        allow_duplicates = True
        
        if self.supabase:
            try:
                res = self.supabase.table("posts").select("*").eq("url", url).execute()
                if res.data:
                    row = res.data[0]
                    last_id = row.get("last_comment_id", last_id)
                    title = row.get("title", title)
                    prizes = row.get("prizes", prizes)
                    winners = row.get("winners", winners)
                    allow_duplicates = row.get("allow_duplicates", True)

                res = self.supabase.table("participants").select("author, count").eq("url", url).execute()
                if res.data:
                    participants = {r["author"]: r["count"] for r in res.data}
                
                res = self.supabase.table("commenters").select("author").eq("url", url).execute()
                if res.data:
                    all_commenters = [r["author"] for r in res.data]
                
                return participants, all_commenters, last_id, title, prizes, winners, allow_duplicates
            except Exception as e:
                print(f"DEBUG: [Supabase Error] get_data: {e}")

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT last_comment_id, title, prizes, winners, allow_duplicates FROM posts WHERE url = ?", (url,))
            row = cursor.fetchone()
            if row:
                last_id, title, prizes, winners, allow_duplicates = row
                if allow_duplicates is None: allow_duplicates = True
            
            cursor.execute("SELECT author, count FROM participants WHERE url = ?", (url,))
            for author, count in cursor.fetchall():
                participants[author] = count
                
            cursor.execute("SELECT author FROM commenters WHERE url = ?", (url,))
            all_commenters = [r[0] for r in cursor.fetchall()]
                
        return participants, all_commenters, last_id, title, prizes, winners, allow_duplicates

    def get_all_urls(self) -> List[str]:
        """저장된 모든 URL 목록 조회"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT url FROM posts ORDER BY updated_at DESC")
            return [row[0] for row in cursor.fetchall()]
