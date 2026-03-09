import os
import sqlite3
import time
import random
from datetime import datetime
from typing import List, Dict, Any, Tuple
from supabase import create_client, Client
from dotenv import load_dotenv

# .env 로드
load_dotenv()

def retry_supabase(func):
    """Supabase 작업 재시도 데코레이터"""
    def wrapper(*args, **kwargs):
        max_retries = 3
        base_delay = 1.0
        for i in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if i < max_retries - 1:
                    time.sleep(base_delay * (2 ** i))
                    continue
                # Supabase 에러는 로그만 남기고 주 흐름(SQLite)을 방해하지 않음
                print(f"DEBUG: [Supabase Sync Skip] {e}")
                return None
    return wrapper

class CommentDatabase:
    """네이버 카페 댓글 데이터를 로컬 SQLite에 저장하고 Supabase에 선택적으로 동기화하는 핸들러"""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            # 기본 경로 소스 디렉토리
            base_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(base_dir, 'comments.db')
        
        self.db_path = db_path
        self._initialize_sqlite()
        
        # Supabase 설정 (선택 사항)
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_KEY")
        self.supabase: Client = None
        
        if self.supabase_url and self.supabase_key:
            try:
                self.supabase = create_client(self.supabase_url.strip("'\""), self.supabase_key.strip("'\""))
                print(f"DEBUG: [Supabase] Sync enabled for {self.supabase_url}")
            except Exception as e:
                print(f"DEBUG: [Supabase Init Error] {e}")

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _initialize_sqlite(self):
        """로컬 SQLite 테이블 초기화"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 1. Posts 테이블
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS posts (
                    url TEXT PRIMARY KEY,
                    title TEXT,
                    prizes TEXT,
                    memo TEXT,
                    winners TEXT,
                    last_comment_id TEXT,
                    is_active BOOLEAN DEFAULT 0,
                    allow_duplicates BOOLEAN DEFAULT 1,
                    allowed_list TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # 2. Participants 테이블
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS participants (
                    url TEXT,
                    author TEXT,
                    count INTEGER DEFAULT 1,
                    created_at TEXT,
                    PRIMARY KEY (url, author)
                )
            ''')
            # 3. Commenters 테이블 (전체 명단)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS commenters (
                    url TEXT,
                    author TEXT,
                    created_at TEXT,
                    PRIMARY KEY (url, author)
                )
            ''')
            conn.commit()
        print(f"DEBUG: [SQLite] Initialized at {self.db_path}")

    def clear_data(self, url: str):
        """로컬 및 Supabase에서 데이터 삭제"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM participants WHERE url = ?", (url,))
            cursor.execute("DELETE FROM commenters WHERE url = ?", (url,))
            cursor.execute("DELETE FROM posts WHERE url = ?", (url,))
            conn.commit()
        
        if self.supabase:
            self._sync_clear_supabase(url)

    @retry_supabase
    def _sync_clear_supabase(self, url):
        self.supabase.table("participants").delete().eq("url", url).execute()
        self.supabase.table("commenters").delete().eq("url", url).execute()
        self.supabase.table("posts").delete().eq("url", url).execute()

    def save_data(self, url: str, participants_dict, last_comment_id,
                  all_commenters=None, title=None, prizes=None, memo=None, winners=None, allow_duplicates=None, allowed_list=None):
        """데이터 저장 (SQLite 우선, Supabase 비동기적 동기화 지향)"""
        
        # 1. SQLite 업데이트
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Post 정보 Upsert
            cursor.execute("SELECT url FROM posts WHERE url = ?", (url,))
            if cursor.fetchone():
                update_fields = []
                values = []
                if title is not None: update_fields.append("title = ?"); values.append(title)
                if prizes is not None: update_fields.append("prizes = ?"); values.append(prizes)
                if memo is not None: update_fields.append("memo = ?"); values.append(memo)
                if winners is not None: update_fields.append("winners = ?"); values.append(winners)
                if last_comment_id is not None: update_fields.append("last_comment_id = ?"); values.append(last_comment_id)
                if allow_duplicates is not None: update_fields.append("allow_duplicates = ?"); values.append(1 if allow_duplicates else 0)
                if allowed_list is not None: update_fields.append("allowed_list = ?"); values.append(allowed_list)
                
                update_fields.append("updated_at = ?")
                values.append(datetime.now().isoformat())
                values.append(url)
                
                if update_fields:
                    cursor.execute(f"UPDATE posts SET {', '.join(update_fields)} WHERE url = ?", values)
            else:
                cursor.execute("""
                    INSERT INTO posts (url, title, prizes, memo, winners, last_comment_id, allow_duplicates, allowed_list, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (url, title, prizes, memo, winners, last_comment_id, 1 if allow_duplicates else 0, allowed_list, datetime.now().isoformat()))

            # Participants Upsert
            if participants_dict:
                for author, v in participants_dict.items():
                    count = v[0] if isinstance(v, (tuple, list)) else v
                    created_at = v[1] if isinstance(v, (tuple, list)) else None
                    cursor.execute("""
                        INSERT INTO participants (url, author, count, created_at)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(url, author) DO UPDATE SET count = excluded.count, created_at = excluded.created_at
                    """, (url, author, count, created_at))

            # Commenters Upsert
            if all_commenters:
                for item in all_commenters:
                    name = item['name'] if isinstance(item, dict) else item
                    c_at = item.get('created_at') if isinstance(item, dict) else None
                    cursor.execute("""
                        INSERT INTO commenters (url, author, created_at)
                        VALUES (?, ?, ?)
                        ON CONFLICT(url, author) DO UPDATE SET created_at = excluded.created_at
                    """, (url, name, c_at))
            
            conn.commit()

        # 2. Supabase 동기화 (최적화된 방식 유지)
        if self.supabase:
            self._sync_save_supabase(url, participants_dict, last_comment_id, all_commenters, title, prizes, memo, winners, allow_duplicates, allowed_list)

    @retry_supabase
    def _sync_save_supabase(self, url, participants_dict, last_comment_id, all_commenters, title, prizes, memo, winners, allow_duplicates, allowed_list):
        post_data = {"url": url, "updated_at": datetime.now().isoformat()}
        if title is not None: post_data["title"] = title
        if prizes is not None: post_data["prizes"] = prizes
        if memo is not None: post_data["memo"] = memo
        if winners is not None: post_data["winners"] = winners
        if allowed_list is not None: post_data["allowed_list"] = allowed_list
        if allow_duplicates is not None: post_data["allow_duplicates"] = allow_duplicates
        if last_comment_id is not None: post_data["last_comment_id"] = last_comment_id
        
        self.supabase.table("posts").upsert(post_data, on_conflict="url").execute()

        if participants_dict:
            p_batch = []
            for author, v in participants_dict.items():
                count = v[0] if isinstance(v, (tuple, list)) else v
                c_at = v[1] if isinstance(v, (tuple, list)) else None
                p_batch.append({"url": url, "author": author, "count": count, "created_at": c_at})
            for i in range(0, len(p_batch), 500):
                self.supabase.table("participants").upsert(p_batch[i:i+500], on_conflict="url,author").execute()

        if all_commenters:
            c_batch = []
            for item in all_commenters:
                name = item['name'] if isinstance(item, dict) else item
                c_at = item.get('created_at') if isinstance(item, dict) else None
                c_batch.append({"url": url, "author": name, "created_at": c_at})
            for i in range(0, len(c_batch), 1000):
                self.supabase.table("commenters").upsert(c_batch[i:i+1000], on_conflict="url,author").execute()

    def get_data(self, url: str) -> Tuple[Dict, str, List, str, str, str, str, bool, str]:
        """SQLite에서 데이터 로드"""
        participants = {}
        all_commenters = []
        last_id, title, prizes, memo, winners, allowed_list_str = None, None, None, None, '', None
        allow_duplicates = True

        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Post
            cursor.execute("SELECT * FROM posts WHERE url = ?", (url,))
            row = cursor.fetchone()
            if row:
                last_id = row['last_comment_id']
                title = row['title']
                prizes = row['prizes']
                memo = row['memo']
                winners = row['winners']
                allow_duplicates = bool(row['allow_duplicates'])
                allowed_list_str = row['allowed_list']

            # Participants
            cursor.execute("SELECT author, count, created_at FROM participants WHERE url = ?", (url,))
            for row in cursor.fetchall():
                participants[row['author']] = (row['count'], row['created_at'])

            # Commenters
            cursor.execute("SELECT author, created_at FROM commenters WHERE url = ?", (url,))
            for row in cursor.fetchall():
                all_commenters.append({'name': row['author'], 'created_at': row['created_at']})

        return participants, last_id, all_commenters, title, prizes, memo, winners, allow_duplicates, allowed_list_str

    def set_active_url(self, url: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE posts SET is_active = 0")
            if url:
                cursor.execute("SELECT url FROM posts WHERE url = ?", (url,))
                if cursor.fetchone():
                    cursor.execute("UPDATE posts SET is_active = 1 WHERE url = ?", (url,))
                else:
                    cursor.execute("INSERT INTO posts (url, is_active) VALUES (?, 1)", (url,))
            conn.commit()
        
        if self.supabase:
            self._sync_active_url_supabase(url)

    @retry_supabase
    def _sync_active_url_supabase(self, url):
        self.supabase.table("posts").update({"is_active": False}).neq("url", "void").execute()
        if url:
            self.supabase.table("posts").upsert({"url": url, "is_active": True}, on_conflict="url").execute()

    def get_active_url(self) -> str:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT url FROM posts WHERE is_active = 1 LIMIT 1")
            row = cursor.fetchone()
            return row[0] if row else None

    def get_all_urls(self) -> List[str]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT url FROM posts ORDER BY updated_at DESC")
            return [row[0] for row in cursor.fetchall()]

    def delete_participant(self, url: str, author: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM participants WHERE url = ? AND author = ?", (url, author))
            conn.commit()
        if self.supabase:
            self._sync_delete_p_supabase(url, author)

    @retry_supabase
    def _sync_delete_p_supabase(self, url, author):
        self.supabase.table("participants").delete().eq("url", url).eq("author", author).execute()

    def update_timestamp(self, url: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE posts SET updated_at = ? WHERE url = ?", (datetime.now().isoformat(), url))
            conn.commit()
