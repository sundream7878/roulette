import sqlite3
import os
import time
import random
from datetime import datetime
from typing import List, Dict, Any, Tuple
from supabase import create_client, Client
from dotenv import load_dotenv

# .env 로드
load_dotenv()

def retry_supabase(func):
    """Supabase 작업 재시도 데코레이터 ([Errno 11] 대응)"""
    def wrapper(*args, **kwargs):
        max_retries = 3
        base_delay = 1.0
        for i in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_str = str(e)
                # Resource temporarily unavailable 또는 유사한 네트워크 오류인 경우 재시도
                if "[Errno 11]" in error_str or "connection" in error_str.lower() or "timeout" in error_str.lower():
                    if i < max_retries - 1:
                        delay = base_delay * (2 ** i) + random.uniform(0.0, 1.0)
                        print(f"DEBUG: [Supabase Retry] Error detected: {e}. Retrying in {delay:.2f}s... ({i+1}/{max_retries})")
                        time.sleep(delay)
                        continue
                raise e
    return wrapper

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
            self.supabase_url = self.supabase_url.strip().strip("'").strip('"')
            self.supabase_key = self.supabase_key.strip().strip("'").strip('"')
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
                    memo TEXT,
                    winners TEXT,
                    allowed_list TEXT,
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
            if 'allowed_list' not in columns:
                try:
                    cursor.execute("ALTER TABLE posts ADD COLUMN allowed_list TEXT")
                    print("DEBUG: [DB Migration] Added 'allowed_list' column to posts table.")
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
            if 'memo' not in columns:
                try:
                    cursor.execute("ALTER TABLE posts ADD COLUMN memo TEXT")
                    print("DEBUG: [DB Migration] Added 'memo' column to posts table.")
                except Exception as e:
                    print(f"DEBUG: [DB Migration Error] {e}")

            # commenters 테이블 마이그레이션 및 기존 데이터 보정
            cursor.execute("PRAGMA table_info(commenters)")
            c_columns = [info[1] for info in cursor.fetchall()]
            if 'created_at' not in c_columns:
                try:
                    cursor.execute("ALTER TABLE commenters ADD COLUMN created_at TIMESTAMP")
                    print("DEBUG: [DB Migration] Added 'created_at' column to commenters table.")
                except Exception as e: pass
            
            # 기존 NULL 시간 보정 (모든 테이블)
            try:
                cursor.execute("UPDATE commenters SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL")
                cursor.execute("UPDATE participants SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL")
                # print("DEBUG: [DB Migration] Backfilled NULL timestamps.")
            except: pass

            # participants 테이블 마이그레이션
            cursor.execute("PRAGMA table_info(participants)")
            p_columns = [info[1] for info in cursor.fetchall()]
            if 'created_at' not in p_columns:
                try:
                    cursor.execute("ALTER TABLE participants ADD COLUMN created_at TIMESTAMP")
                    print("DEBUG: [DB Migration] Added 'created_at' column to participants table.")
                except Exception as e: pass

            # commenters 테이블 마이그레이션
            cursor.execute("PRAGMA table_info(commenters)")
            c_columns = [info[1] for info in cursor.fetchall()]
            if 'created_at' not in c_columns:
                try:
                    cursor.execute("ALTER TABLE commenters ADD COLUMN created_at TIMESTAMP")
                    print("DEBUG: [DB Migration] Added 'created_at' column to commenters table.")
                except Exception as e:
                    print(f"DEBUG: [DB Migration Error] {e}")

            # participants 테이블 마이그레이션
            cursor.execute("PRAGMA table_info(participants)")
            p_columns = [info[1] for info in cursor.fetchall()]
            if 'created_at' not in p_columns:
                try:
                    cursor.execute("ALTER TABLE participants ADD COLUMN created_at TIMESTAMP")
                    print("DEBUG: [DB Migration] Added 'created_at' column to participants table.")
                except Exception as e:
                    print(f"DEBUG: [DB Migration Error] {e}")

            # 참여자 및 댓글 수 테이블 (룰렛용 - 가치중치 포함)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS participants (
                    url TEXT,
                    author TEXT,
                    count INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (url, author),
                    FOREIGN KEY (url) REFERENCES posts (url) ON DELETE CASCADE
                )
            ''')

            # 모든 댓글 작성자 테이블 (모니터링용)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS commenters (
                    url TEXT,
                    author TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (url, author),
                    FOREIGN KEY (url) REFERENCES posts (url) ON DELETE CASCADE
                )
            ''')
            conn.commit()

    @retry_supabase
    def clear_data(self, url: str):
        """특정 URL의 데이터를 삭제 (새로운 수집 시 리셋용)"""
        if self.supabase:
            try:
                # 완전한 초기화를 위해 포스트 정보(제목, 당첨자 등)도 모두 삭제
                self.supabase.table("participants").delete().eq("url", url).execute()
                self.supabase.table("commenters").delete().eq("url", url).execute()
                self.supabase.table("posts").delete().eq("url", url).execute() 
                print(f"DEBUG: [Supabase] Fully cleared data for URL: {url}")
            except Exception as e:
                print(f"DEBUG: [Supabase Error] clear_data: {e}")
        
        # 로컬 DB도 완전 삭제
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM participants WHERE url = ?", (url,))
            cursor.execute("DELETE FROM commenters WHERE url = ?", (url,))
            cursor.execute("DELETE FROM posts WHERE url = ?", (url,))
            conn.commit()
            print(f"DEBUG: [DB] Fully cleared data for URL: {url}")
        
        # 로컬 DB 저장은 생략
        # with self._get_connection() as conn:
        #     cursor = conn.cursor()
        #     cursor.execute("DELETE FROM participants WHERE url = ?", (url,))
        #     cursor.execute("DELETE FROM commenters WHERE url = ?", (url,))
        #     cursor.execute("DELETE FROM posts WHERE url = ?", (url,))
        #     conn.commit()
        #     print(f"DEBUG: [DB] Cleared data for URL: {url}")

    @retry_supabase
    def _sync_to_supabase_bg(self, url: str, participants_dict, last_comment_id, 
                              all_commenters, title, prizes, memo, winners, allow_duplicates, allowed_list=None):
        """Supabase 동기화 - 백그라운드 스레드에서 실행 (블로킹 방지)"""
        if not self.supabase:
            return
        try:
            # 1. posts 테이블 upsert
            print(f"DEBUG: [Supabase Sync] Upserting post data for {url}...")
            post_data = {"url": url, "updated_at": datetime.now().isoformat()}
            if title is not None: post_data["title"] = title
            if prizes is not None: post_data["prizes"] = prizes
            if memo is not None: post_data["memo"] = memo
            if winners is not None: post_data["winners"] = winners
            if allowed_list is not None: post_data["allowed_list"] = allowed_list
            if allow_duplicates is not None: post_data["allow_duplicates"] = allow_duplicates
            if last_comment_id and last_comment_id != '':
                post_data["last_comment_id"] = last_comment_id
            
            try:
                self.supabase.table("posts").upsert(post_data, on_conflict="url").execute()
                print("DEBUG: [Supabase Sync] Post data upserted.")
            except Exception as e:
                # 특정 컬럼(예: memo)이 DB에 없을 경우 해당 필드를 제외하고 재시도
                error_msg = str(e)
                if "Could not find the" in error_msg and "column" in error_msg:
                    import re
                    match = re.search(r"'([^']+)' column", error_msg)
                    if match:
                        missing_col = match.group(1)
                        print(f"DEBUG: [Supabase] Column '{missing_col}' missing. Retrying without it.")
                        if missing_col in post_data:
                            del post_data[missing_col]
                            self.supabase.table("posts").upsert(post_data, on_conflict="url").execute()
                        else:
                            raise e
                    else:
                        raise e
                else:
                    raise e

            # 2. participants 테이블 - 삭제 후 재삽입 (upsert 중복 키 오류 방지)
            if participants_dict is not None:
                print(f"DEBUG: [Supabase Sync] Updating participants ({len(participants_dict)} entries)...")
                # 기존 데이터 삭제 후 새로 삽입 (upsert 대신 delete+insert 사용)
                self.supabase.table("participants").delete().eq("url", url).execute()
                if participants_dict:
                    # participants_dict may contain (count, created_at) tuples or just counts
                    p_batch = []
                    for a, v in participants_dict.items():
                        count = v[0] if isinstance(v, (tuple, list)) else v
                        created_at = v[1] if isinstance(v, (tuple, list)) else None
                        item = {"url": url, "author": a, "count": count}
                        if created_at: item["created_at"] = created_at
                        p_batch.append(item)
                    
                    if p_batch:
                        try:
                            self.supabase.table("participants").insert(p_batch).execute()
                            print(f"DEBUG: [Supabase Sync] {len(p_batch)} participants inserted.")
                        except Exception as pe:
                            if "column" in str(pe).lower() and "created_at" in str(pe).lower():
                                print("DEBUG: [Supabase] 'created_at' missing in participants. Retrying without it.")
                                for item in p_batch: 
                                    if 'created_at' in item: del item['created_at']
                                self.supabase.table("participants").insert(p_batch).execute()
                            else:
                                raise pe

            # 3. commenters 테이블 - 삭제 후 재삽입 (upsert 제약 조건 모를 때 가장 안전)
            if all_commenters:
                self.supabase.table("commenters").delete().eq("url", url).execute()
                
                # all_commenters may be a list of strings or a list of dicts with {name, created_at}
                c_batch = []
                # 중복 제거 (author 기준)
                seen_authors = set()
                
                for item in all_commenters:
                    name = item['name'] if isinstance(item, dict) else item
                    if name in seen_authors: continue
                    seen_authors.add(name)
                    
                    c_item = {"url": url, "author": name}
                    if isinstance(item, dict) and item.get('created_at'):
                        c_item['created_at'] = item['created_at']
                    c_batch.append(c_item)
                
                if c_batch:
                    # 데이터가 많을 수 있으므로 100개씩 나누어 삽입 (안전)
                    for i in range(0, len(c_batch), 100):
                        batch = c_batch[i:i+100]
                        try:
                            self.supabase.table("commenters").insert(batch).execute()
                        except Exception as ce:
                            if "column" in str(ce).lower() and "created_at" in str(ce).lower():
                                print("DEBUG: [Supabase] 'created_at' missing in commenters. Retrying without it.")
                                for item in batch:
                                    if 'created_at' in item: del item['created_at']
                                self.supabase.table("commenters").insert(batch).execute()
                            else:
                                raise ce

        except Exception as e:
            print(f"DEBUG: [Supabase Sync FAIL] URL: {url}, Error: {e}")
            import traceback
            traceback.print_exc()

    def _sync_to_supabase(self, url: str, participants_dict, last_comment_id, 
                          all_commenters=None, title=None, prizes=None, memo=None,
                          winners=None, allow_duplicates=None, allowed_list=None):
        """Supabase 동기화 - 백그라운드 스레드로 즉시 반환 (블로킹 없음)"""
        if not self.supabase:
            return
        
        # 데이터 유실 방지를 위해 None이 아닌 경우에만 복사
        p_dict_copy = dict(participants_dict) if participants_dict is not None else None
        c_list_copy = list(all_commenters) if all_commenters is not None else None
        
        # print(f"DEBUG: [Supabase] Scheduling sync for {url} (has_p: {p_dict_copy is not None}, has_c: {c_list_copy is not None}, has_al: {allowed_list is not None})")
        
        import threading
        t = threading.Thread(
            target=self._sync_to_supabase_bg,
            args=(url, p_dict_copy, last_comment_id, c_list_copy,
                  title, prizes, memo, winners, allow_duplicates, allowed_list),
            daemon=True
        )
        t.start()

    def save_data(self, url: str, participants_dict, last_comment_id,
                  all_commenters=None, title=None, prizes=None, memo=None, winners=None, allow_duplicates=None, allowed_list=None):
        """수집된 데이터 저장 - Supabase 및 로컬 SQLite 저장"""
        # 1. 로컬 SQLite 저장 (동기)
        self._save_to_local(url, participants_dict, last_comment_id, all_commenters, title, prizes, memo, winners, allow_duplicates, allowed_list)
        
        # 2. Supabase 저장 (비동기)
        # 로컬 우선 순위: 만약 title 등이 None이라면 로컬에서 불러와서 Supabase에 빈 값을 보내지 않도록 할 수도 있음.
        if any(v is None for v in [title, prizes, memo, winners, allow_duplicates, allowed_list]):
            # Supabase 동기화 전, 누락된 필드를 '로컬' DB에서만 가져와서 채움
            # get_data(local_only=True)를 사용하여 Supabase의 오래된 데이터가 섞이는 것을 방지
            _, _, _, l_title, l_prizes, l_memo, l_winners, l_allow_duplicates, l_allowed_list = self.get_data(url, local_only=True)
            if title is None: title = l_title
            if prizes is None: prizes = l_prizes
            if memo is None: memo = l_memo
            if winners is None: winners = l_winners
            if allow_duplicates is None: allow_duplicates = l_allow_duplicates
            if allowed_list is None: allowed_list = l_allowed_list

        self._sync_to_supabase(url, participants_dict, last_comment_id, all_commenters, title, prizes, memo, winners, allow_duplicates, allowed_list)

    def _save_to_local(self, url: str, participants_dict: Dict[str, int], last_comment_id: str, 
                      all_commenters: List[str] = None, title: str = None, prizes: str = None, memo: str = None, winners: str = None, allow_duplicates: bool = None, allowed_list: str = None):
        """SQLite 저장 로직"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # DEBUG: 파라미터 타입 확인
            
            try:
                cursor.execute('''
                    INSERT INTO posts (url, title, prizes, memo, winners, allowed_list, allow_duplicates, last_comment_id, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(url) DO UPDATE SET
                        title = COALESCE(excluded.title, posts.title),
                        prizes = COALESCE(excluded.prizes, posts.prizes),
                        memo = COALESCE(excluded.memo, posts.memo),
                        winners = COALESCE(excluded.winners, posts.winners),
                        allowed_list = COALESCE(excluded.allowed_list, posts.allowed_list),
                        allow_duplicates = COALESCE(excluded.allow_duplicates, posts.allow_duplicates),
                        last_comment_id = CASE WHEN excluded.last_comment_id != '' THEN excluded.last_comment_id ELSE posts.last_comment_id END,
                        updated_at = excluded.updated_at
                ''', (url, title, prizes, memo, winners, allowed_list, allow_duplicates, last_comment_id, datetime.now()))
            except Exception as e:
                print(f"DEBUG: [Local DB Error] posts upsert: {e}")
                raise e
            
            if participants_dict is not None and len(participants_dict) > 0:
                cursor.execute("DELETE FROM participants WHERE url = ?", (url,))
                for author, v in participants_dict.items():
                    count = v[0] if isinstance(v, (tuple, list)) else v
                    created_at = v[1] if isinstance(v, (tuple, list)) else None
                    cursor.execute('INSERT INTO participants (url, author, count, created_at) VALUES (?, ?, ?, ?)', (url, author, count, created_at))
            elif participants_dict == {}:
                cursor.execute("DELETE FROM participants WHERE url = ?", (url,))
            
            if all_commenters:
                for item in all_commenters:
                    if isinstance(item, dict):
                        cursor.execute('INSERT INTO commenters (url, author, created_at) VALUES (?, ?, ?) ON CONFLICT(url, author) DO UPDATE SET created_at = COALESCE(excluded.created_at, commenters.created_at)', 
                                       (url, item['name'], item.get('created_at')))
                    else:
                        cursor.execute('INSERT OR IGNORE INTO commenters (url, author) VALUES (?, ?)', (url, item))
            
            conn.commit()
            print(f"DEBUG: [Local DB] Saved data for URL: {url}")

    # 중복된 save_data 제거

    @retry_supabase
    def set_active_url(self, url: str):
        """특정 URL을 활성 이벤트로 설정 (Supabase 최우선)"""
        if self.supabase:
            # Supabase requires a WHERE clause for updates. We use a dummy .neq() to satisfy this.
            self.supabase.table("posts").update({"is_active": False}).neq("url", "dummy_bypass_string").execute()
            if url:
                self.supabase.table("posts").upsert({"url": url, "is_active": True}, on_conflict="url").execute()
                print(f"DEBUG: [Supabase] Active URL set: {url}")
            else:
                print(f"DEBUG: [Supabase] All URLs deactivated")

        # [로컬 DB] 행위 추가
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE posts SET is_active = 0")
            if url:
                cursor.execute("INSERT OR REPLACE INTO posts (url, is_active) VALUES (?, 1)", (url,))
            conn.commit()

    @retry_supabase
    def get_active_url(self) -> str:
        """현재 활성화된 이벤트 URL을 가져옵니다 (Supabase 우선)."""
        if self.supabase:
            res = self.supabase.table("posts").select("url").eq("is_active", True).limit(1).execute()
            if res.data: return res.data[0]["url"]
            # 삭제된 게시글이 자동으로 되살아나지 않도록 최근 데이터 불러오는 폴백 로직 제거
            # res = self.supabase.table("posts").select("url").order("updated_at", desc=True).limit(1).execute()
            # if res.data: return res.data[0]["url"]

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT url FROM posts WHERE is_active = 1 LIMIT 1")
            row = cursor.fetchone()
            if row: return row[0]
            # [로컬] 최근 데이터 폴백도 제거하여 좀비 현상 방지
            # cursor.execute("SELECT url FROM posts ORDER BY updated_at DESC LIMIT 1")
            # row = cursor.fetchone()
            # return row[0] if row else None
        return None

    @retry_supabase
    def update_timestamp(self, url: str):
        """특정 URL의 updated_at 필드를 현재 시간으로 갱신합니다."""
        if self.supabase:
            self.supabase.table("posts").update({"updated_at": datetime.now().isoformat()}).eq("url", url).execute()
            print(f"DEBUG: [Supabase] Updated timestamp for URL: {url}")
        
        # [수정] 로컬 DB 타임스탬프도 반드시 갱신해야 Stale Protection이 정상 작동함
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE posts SET updated_at = ? WHERE url = ?', (datetime.now(), url))
            conn.commit()
            print(f"DEBUG: [Local DB] Updated timestamp for URL: {url}")

    @retry_supabase
    def get_data(self, url: str, local_only: bool = False) -> Tuple[Dict[str, int], str, List[dict], str, str, str, str, bool, str]:
        """특정 URL의 저장된 데이터 조회 (Local + Supabase Merge)
        local_only=True 인 경우 Supabase 조회를 건너뛰고 로컬 데이터만 반환합니다.
        """
        # 1. 로컬 데이터 조회 (기본값)
        participants = {}
        all_commenters = []
        last_id = None
        title = None
        prizes = None
        memo = None
        winners = None
        allow_duplicates = True
        allowed_list = None

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT last_comment_id, title, prizes, memo, winners, allow_duplicates, allowed_list FROM posts WHERE url = ?", (url,))
            row = cursor.fetchone()
            if row:
                last_id, title, prizes, memo, winners, allow_duplicates, allowed_list = row
                if allow_duplicates is None: allow_duplicates = True
            
            cursor.execute("SELECT author, count, created_at FROM participants WHERE url = ?", (url,))
            for author, count, created_at in cursor.fetchall():
                participants[author] = (count, created_at)
                
            cursor.execute("SELECT author, created_at FROM commenters WHERE url = ?", (url,))
            all_commenters = [{"name": r[0], "created_at": r[1]} for r in cursor.fetchall()]

        # 2. Supabase 데이터 조회 및 병합 (활성화 시 및 local_only가 아닐 때)
        if self.supabase and not local_only:
            try:
                # Post 정보 가져오기
                res = self.supabase.table("posts").select("*").eq("url", url).execute()
                if res.data:
                    post = res.data[0]
                    
                    # [수정] 지능형 Stale Protection: 클라우드 데이터가 로컬보다 과거의 것이라면 덮어쓰지 않음
                    sb_updated_str = post.get('updated_at')
                    is_cloud_stale = False
                    
                    if sb_updated_str:
                        try:
                            # Supabase ISO format (often has T and Z)
                            sb_ts = sb_updated_str.replace('T', ' ').replace('Z', '').split('+')[0].split('.')[0]
                            sb_updated = datetime.strptime(sb_ts, '%Y-%m-%d %H:%M:%S')
                            
                            with self._get_connection() as conn:
                                cursor = conn.cursor()
                                cursor.execute("SELECT updated_at FROM posts WHERE url = ?", (url,))
                                row = cursor.fetchone()
                                if row and row[0]:
                                    ts_str = row[0].split('.')[0]
                                    local_updated = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S')
                                    # 클라우드가 로컬보다 1초 이상 과거면 stale로 간주 (네트워크 시간차 감안)
                                    if sb_updated < local_updated:
                                        is_cloud_stale = True
                                        print(f"DEBUG: Cloud data for {url} is stale (older than local). Protecting local data.")
                        except Exception as e:
                            print(f"DEBUG: Timestamp comparison error: {e}")

                    # 데이터 병합 (stale이 아닐 때만 덮어씀. stale이더라도 로컬이 비어있으면 덮어씀)
                    if post.get('last_comment_id'): last_id = post['last_comment_id']
                    
                    if not is_cloud_stale or not title:
                        if post.get('title') is not None: title = post['title']
                    if not is_cloud_stale or not prizes:
                        if post.get('prizes') is not None: prizes = post['prizes']
                    if not is_cloud_stale or not memo:
                        if post.get('memo') is not None: memo = post['memo']
                    if not is_cloud_stale or not winners:
                        if post.get('winners') is not None: winners = post['winners']
                    if not is_cloud_stale or not allowed_list:
                        if post.get('allowed_list') is not None: allowed_list = post['allowed_list']
                    if not is_cloud_stale or allow_duplicates is None:
                        if post.get('allow_duplicates') is not None: allow_duplicates = bool(post['allow_duplicates'])

                # Participants 가져오기
                try:
                    res = self.supabase.table("participants").select("author, count, created_at").eq("url", url).execute()
                except Exception as e:
                    if "created_at" in str(e).lower():
                        res = self.supabase.table("participants").select("author, count").eq("url", url).execute()
                    else: raise e
                
                if res.data:
                    # [수정] stale protection 중일 때는 Supabase의 데이터로 덮어쓰지 않음
                    if not is_cloud_stale:
                        participants = {row['author']: (row['count'], row.get('created_at')) for row in res.data}
                
                # Commenters 가져오기
                try:
                    res = self.supabase.table("commenters").select("author, created_at").eq("url", url).execute()
                except Exception as e:
                    if "created_at" in str(e).lower():
                        res = self.supabase.table("commenters").select("author").eq("url", url).execute()
                    else: raise e
                
                if res.data:
                    if not is_cloud_stale:
                        all_commenters = [{'name': row['author'], 'created_at': row.get('created_at')} for row in res.data]

            except Exception as e:
                print(f"DEBUG: [Supabase Merge Error] {e}")

        return participants, last_id, all_commenters, title, prizes, memo, winners, allow_duplicates, allowed_list

    def get_all_urls(self) -> List[str]:
        """저장된 모든 URL 목록 조회"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT url FROM posts ORDER BY updated_at DESC")
            return [row[0] for row in cursor.fetchall()]
