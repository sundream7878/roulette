import os
import sqlite3
import time
import random
from datetime import datetime
from typing import List, Dict, Any, Tuple
from supabase import create_client, Client
from dotenv import load_dotenv
import threading

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
                
                # 로그 파일에 에러 상세 기록
                try:
                    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    log_file = os.path.join(base_dir, "monitor_debug.log")
                    with open(log_file, "a", encoding="utf-8") as f:
                        f.write(f"[{datetime.now()}] ERROR: [Supabase Sync Failed] {func.__name__}: {str(e)}\n")
                except:
                    pass
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
            # [최적화] Supabase 동기화를 백그라운드 스레드에서 실행 (비동기)
            threading.Thread(target=self._sync_clear_supabase, args=(url,), daemon=True).start()

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

        # 2. Supabase 동기화 (백그라운드 스레드에서 실행하여 로컬 지연 방지)
        if self.supabase:
            threading.Thread(
                target=self._sync_save_supabase, 
                args=(url, participants_dict, last_comment_id, all_commenters, title, prizes, memo, winners, allow_duplicates, allowed_list),
                daemon=True
            ).start()

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
                # Supabase 테이블에 created_at 컬럼이 없어 제외함 (스키마 불일치 해결)
                p_batch.append({"url": url, "author": author, "count": count})
            for i in range(0, len(p_batch), 500):
                self.supabase.table("participants").upsert(p_batch[i:i+500], on_conflict="url,author").execute()

        if all_commenters:
            c_batch = []
            for item in all_commenters:
                name = item['name'] if isinstance(item, dict) else item
                # Supabase 테이블에 created_at 컬럼이 없어 제외함 (스키마 불일치 해결)
                c_batch.append({"url": url, "author": name})
            for i in range(0, len(c_batch), 1000):
                self.supabase.table("commenters").upsert(c_batch[i:i+1000], on_conflict="url,author").execute()

    def get_data(self, url: str) -> Tuple[Dict, str, List, str, str, str, str, bool, str]:
        """SQLite에서 데이터 로드 (없으면 Supabase에서 가져오기 시도)"""
        participants = {}
        all_commenters = []
        last_id, title, prizes, memo, winners, allowed_list_str = None, None, None, None, '', None
        allow_duplicates = True

        # 1. SQLite 시도
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
                for p_row in cursor.fetchall():
                    participants[p_row['author']] = (p_row['count'], p_row['created_at'])

                # Commenters
                cursor.execute("SELECT author, created_at FROM commenters WHERE url = ?", (url,))
                for c_row in cursor.fetchall():
                    all_commenters.append({'name': c_row['author'], 'created_at': c_row['created_at']})
                
                return participants, last_id, all_commenters, title, prizes, memo, winners, allow_duplicates, allowed_list_str

        # 2. SQLite에 데이터가 없고 Supabase가 활성화된 경우 Supabase 시도
        if self.supabase:
            print(f"DEBUG: [Supabase Fallback] Fetching data for {url}")
            try:
                # Post 정보 가져오기
                res = self.supabase.table("posts").select("*").eq("url", url).execute()
                if res.data:
                    post = res.data[0]
                    last_id = post.get('last_comment_id')
                    title = post.get('title')
                    prizes = post.get('prizes')
                    memo = post.get('memo')
                    winners = post.get('winners', '')
                    allow_duplicates = bool(post.get('allow_duplicates', True))
                    allowed_list_str = post.get('allowed_list')

                    # Participants 가져오기
                    p_res = self.supabase.table("participants").select("*").eq("url", url).execute()
                    for p in p_res.data:
                        participants[p['author']] = (p['count'], p.get('created_at'))

                    # Commenters 가져오기
                    c_res = self.supabase.table("commenters").select("*").eq("url", url).execute()
                    for c in c_res.data:
                        all_commenters.append({'name': c['author'], 'created_at': c.get('created_at')})

                    # SQLite에 캐싱 (Hydration)
                    print(f"DEBUG: [Hydration] Saving {len(participants)} participants to local SQLite")
                    self._hydrate_local_from_supabase(url, post, participants, all_commenters)
                    
                    return participants, last_id, all_commenters, title, prizes, memo, winners, allow_duplicates, allowed_list_str
            except Exception as e:
                print(f"DEBUG: [Supabase Fallback Error] {e}")

        return participants, last_id, all_commenters, title, prizes, memo, winners, allow_duplicates, allowed_list_str

    def _hydrate_local_from_supabase(self, url, post, participants, all_commenters):
        """Supabase 데이터를 로컬 SQLite로 복사"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # Post
                cursor.execute("""
                    INSERT OR REPLACE INTO posts (url, title, prizes, memo, winners, last_comment_id, allow_duplicates, allowed_list, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    url, post.get('title'), post.get('prizes'), post.get('memo'), 
                    post.get('winners'), post.get('last_comment_id'), 
                    1 if post.get('allow_duplicates') else 0, 
                    post.get('allowed_list'), post.get('updated_at') or datetime.now().isoformat()
                ))
                
                # Participants
                for author, v in participants.items():
                    cursor.execute("""
                        INSERT OR REPLACE INTO participants (url, author, count, created_at)
                        VALUES (?, ?, ?, ?)
                    """, (url, author, v[0], v[1]))
                
                # Commenters
                for c in all_commenters:
                    cursor.execute("""
                        INSERT OR REPLACE INTO commenters (url, author, created_at)
                        VALUES (?, ?, ?)
                    """, (url, c['name'], c['created_at']))
                
                conn.commit()
        except Exception as e:
            print(f"DEBUG: [Hydration Error] {e}")

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
            # [최적화] 활성 URL 동기화를 백그라운드 스레드에서 실행
            threading.Thread(target=self._sync_active_url_supabase, args=(url,), daemon=True).start()

    @retry_supabase
    def _sync_active_url_supabase(self, url):
        self.supabase.table("posts").update({"is_active": False}).neq("url", "void").execute()
        if url:
            self.supabase.table("posts").upsert({"url": url, "is_active": True}, on_conflict="url").execute()

    def set_active_url_local_only(self, url: str):
        """Supabase 동기화 없이 로컬 SQLite의 활성 상태만 변경합니다. (폴링 루프용)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE posts SET is_active = 0")
            if url:
                cursor.execute("SELECT url FROM posts WHERE url = ?", (url,))
                if cursor.fetchone():
                    cursor.execute("UPDATE posts SET is_active = 1 WHERE url = ?", (url,))
                else:
                    cursor.execute("INSERT INTO posts (url, is_active, updated_at) VALUES (?, 1, ?)", 
                                 (url, datetime.now().isoformat()))
            conn.commit()
            print(f"DEBUG: [LocalSync] Local active URL synchronized to: {url}")

    def get_active_url(self) -> str:
        """현재 활성화된 이벤트 URL을 가져옵니다. (Supabase 우선 순위)"""
        # 1. Supabase 확인 (글로벌 상태 우선)
        if self.supabase:
            try:
                res = self.supabase.table("posts").select("url").eq("is_active", True).limit(1).execute()
                if res.data and res.data[0].get('url'):
                    return res.data[0]['url']
            except Exception as e:
                print(f"DEBUG: [get_active_url Supabase Error] {e}")
        
        # 2. SQLite 확인 (오프라인 또는 Supabase에 없을 경우 Fallback)
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT url FROM posts WHERE is_active = 1 LIMIT 1")
                row = cursor.fetchone()
                if row:
                    return row[0]
        except Exception as e:
            print(f"DEBUG: [get_active_url SQLite Error] {e}")
            
        return None

    def get_all_urls(self) -> List[str]:
        urls = set()
        # 1. SQLite
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT url FROM posts ORDER BY updated_at DESC")
            for row in cursor.fetchall():
                urls.add(row[0])
        
        # 2. Supabase
        if self.supabase:
            try:
                res = self.supabase.table("posts").select("url").execute()
                for item in res.data:
                    urls.add(item['url'])
            except:
                pass
        
        return list(urls)

    def delete_participant(self, url: str, author: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM participants WHERE url = ? AND author = ?", (url, author))
            conn.commit()
        if self.supabase:
            # [최적화] 참가자 삭제 동기화를 백그라운드 스레드에서 실행
            threading.Thread(target=self._sync_delete_p_supabase, args=(url, author), daemon=True).start()

    @retry_supabase
    def _sync_delete_p_supabase(self, url, author):
        self.supabase.table("participants").delete().eq("url", url).eq("author", author).execute()

    def update_timestamp(self, url: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE posts SET updated_at = ? WHERE url = ?", (datetime.now().isoformat(), url))
            conn.commit()
