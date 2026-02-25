import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Any, Tuple

class CommentDatabase:
    """네이버 카페 댓글 데이터를 URL별로 저장하고 관리하는 SQLite 핸들러"""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(base_dir, "comments.db")
        
        self.db_path = db_path
        self._initialize_db()

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

    def save_data(self, url: str, participants_dict: Dict[str, int], last_comment_id: str, 
                  all_commenters: List[str] = None, title: str = None, prizes: str = None, winners: str = None, allow_duplicates: bool = None):
        """수집된 데이터를 저장하거나 업데이트"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 게시글 정보 저장/업데이트
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
            
            # 참여자 정보 저장 (덮어쓰기 로직: 제거된 참가자 반영)
            if participants_dict is not None and len(participants_dict) > 0:
                # 명단이 비어있지 않은 경우에만 전체 교체 (설정 저장 시 영향을 주지 않기 위함)
                cursor.execute("DELETE FROM participants WHERE url = ?", (url,))
                for author, count in participants_dict.items():
                    cursor.execute('''
                        INSERT INTO participants (url, author, count)
                        VALUES (?, ?, ?)
                    ''', (url, author, count))
            elif participants_dict == {}:
                # 명시적으로 빈 사전을 보낸 경우 (전원 제거 상황)
                cursor.execute("DELETE FROM participants WHERE url = ?", (url,))
            
            # 모든 작성자 정보 저장
            if all_commenters:
                for author in all_commenters:
                    cursor.execute('''
                        INSERT OR IGNORE INTO commenters (url, author)
                        VALUES (?, ?)
                    ''', (url, author))
            
            conn.commit()
            print(f"DEBUG: [DB] Saved {len(participants_dict) if participants_dict else 0} participants and {len(all_commenters) if all_commenters else 0} commenters for URL: {url}")

    def get_data(self, url: str) -> Tuple[Dict[str, int], List[str], str, str, str, str, bool]:
        """특정 URL의 저장된 데이터 조회"""
        participants = {}
        all_commenters = []
        last_id = None
        title = None
        prizes = None
        winners = None
        allow_duplicates = True
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 게시글 정보 조회
            cursor.execute("SELECT last_comment_id, title, prizes, winners, allow_duplicates FROM posts WHERE url = ?", (url,))
            row = cursor.fetchone()
            if row:
                last_id, title, prizes, winners, allow_duplicates = row
                if allow_duplicates is None: allow_duplicates = True
            
            # 참여자 목록 조회
            cursor.execute("SELECT author, count FROM participants WHERE url = ?", (url,))
            rows = cursor.fetchall()
            for author, count in rows:
                participants[author] = count
                
            # 모든 작성자 목록 조회
            cursor.execute("SELECT author FROM commenters WHERE url = ?", (url,))
            all_commenters = [r[0] for r in cursor.fetchall()]
                
        return participants, all_commenters, last_id, title, prizes, winners, allow_duplicates

    def get_all_urls(self) -> List[str]:
        """저장된 모든 URL 목록 조회"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT url FROM posts ORDER BY updated_at DESC")
            return [row[0] for row in cursor.fetchall()]
