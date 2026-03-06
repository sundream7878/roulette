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
    """Supabase 작업 재시도 데코레이터 ([Errno 11] 및 네트워크 오류 대응)"""
    def wrapper(*args, **kwargs):
        max_retries = 5
        base_delay = 1.0
        for i in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_str = str(e)
                # Resource temporarily unavailable ([Errno 11]), connection errors, or timeouts
                retryable_errors = ["[Errno 11]", "connection", "timeout", "server disconnected", "connection closed", "broken pipe"]
                if any(err in error_str.lower() for err in retryable_errors):
                    if i < max_retries - 1:
                        delay = base_delay * (2 ** i) + random.uniform(0.0, 1.0)
                        print(f"DEBUG: [Supabase Retry] Error detected: {e}. Retrying in {delay:.2f}s... ({i+1}/{max_retries})")
                        time.sleep(delay)
                        continue
                raise e
    return wrapper

class CommentDatabase:
    """네이버 카페 댓글 데이터를 Supabase(클라우드 DB)에 저장하고 관리하는 핸들러"""
    
    def __init__(self, db_path: str = None):
        # db_path는 하위 호환성을 위해 남겨두지만 사용하지 않음
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
        else:
            print("WARNING: [Supabase] URL or KEY missing in environment variables.")

    @retry_supabase
    def clear_data(self, url: str):
        """특정 URL의 데이터를 Supabase에서 완전히 삭제"""
        if not self.supabase: return
        
        # 완전한 초기화를 위해 관련 테이블 데이터 삭제
        # 외래키 제약 조건에 따라 순서대로 삭제 (participants/commenters -> posts)
        try:
            self.supabase.table("participants").delete().eq("url", url).execute()
            self.supabase.table("commenters").delete().eq("url", url).execute()
            self.supabase.table("posts").delete().eq("url", url).execute() 
            print(f"DEBUG: [Supabase] Fully cleared data for URL: {url}")
        except Exception as e:
            print(f"DEBUG: [Supabase Error] clear_data FAIL: {e}")

    @retry_supabase
    def save_data(self, url: str, participants_dict, last_comment_id,
                  all_commenters=None, title=None, prizes=None, memo=None, winners=None, allow_duplicates=None, allowed_list=None):
        """수집된 데이터를 Supabase에 직접 저장 (동기형)"""
        if not self.supabase: return

        # 1. Post 정보 준비 및 저장 (upsert)
        current_time = datetime.now().isoformat()
        post_data = {"url": url, "updated_at": current_time}
        
        # None이 아닌 필드만 업데이트 데이터에 포함
        if title is not None: post_data["title"] = title
        if prizes is not None: post_data["prizes"] = prizes
        if memo is not None: post_data["memo"] = memo
        if winners is not None: post_data["winners"] = winners
        if allowed_list is not None: post_data["allowed_list"] = allowed_list
        if allow_duplicates is not None: post_data["allow_duplicates"] = allow_duplicates
        if last_comment_id is not None: post_data["last_comment_id"] = last_comment_id

        # post upsert
        self.supabase.table("posts").upsert(post_data, on_conflict="url").execute()
        print(f"DEBUG: [Supabase] Saved post data for {url}")

        # 2. Participants 저장 (upsert 방식이 훨씬 빠름)
        if participants_dict is not None and participants_dict:
            p_batch = []
            for author, v in participants_dict.items():
                count = v[0] if isinstance(v, (tuple, list)) else v
                created_at = v[1] if isinstance(v, (tuple, list)) else None
                item = {"url": url, "author": author, "count": count}
                if created_at: item["created_at"] = created_at
                p_batch.append(item)
            
            if p_batch:
                # 50개씩 청크 분할하여 upsert
                for i in range(0, len(p_batch), 50):
                    batch = p_batch[i:i+50]
                    try:
                        self.supabase.table("participants").upsert(batch, on_conflict="url,author").execute()
                    except Exception as e:
                        # created_at 컬럼 유무 또는 on_conflict 지원 여부에 따른 폴백
                        if "on_conflict" in str(e).lower() or "unique" in str(e).lower():
                            # 명시적 delete 후 insert (단, 매번이 아니라 에러 시에만)
                            self.supabase.table("participants").delete().eq("url", url).execute()
                            self.supabase.table("participants").insert(p_batch).execute()
                            break
                        elif "created_at" in str(e).lower():
                            for item in batch: item.pop("created_at", None)
                            self.supabase.table("participants").upsert(batch, on_conflict="url,author").execute()
                        else: raise e

        # 3. Commenters 저장 (upsert 방식 사용)
        if all_commenters:
            c_batch = []
            seen = set()
            for item in all_commenters:
                name = item['name'] if isinstance(item, dict) else item
                if name in seen: continue
                seen.add(name)
                
                c_item = {"url": url, "author": name}
                if isinstance(item, dict) and item.get('created_at'):
                    c_item['created_at'] = item['created_at']
                c_batch.append(c_item)
            
            if c_batch:
                # 대량 삽입 시 100개씩 청크 분할하여 upsert
                for i in range(0, len(c_batch), 100):
                    batch = c_batch[i:i+100]
                    try:
                        self.supabase.table("commenters").upsert(batch, on_conflict="url,author").execute()
                    except Exception as e:
                        # 에러 시 폴백
                        if "on_conflict" in str(e).lower() or "unique" in str(e).lower():
                             # 기존 방식(위험하지만 작동은 함)
                             pass # 무시하고 다음 배치 시도하거나 로그
                        elif "created_at" in str(e).lower():
                            for item in batch: item.pop("created_at", None)
                            self.supabase.table("commenters").upsert(batch, on_conflict="url,author").execute()
                        else: raise e

    @retry_supabase
    def get_data(self, url: str, local_only: bool = False) -> Tuple[Dict[str, int], str, List[dict], str, str, str, str, bool, str]:
        """Supabase에서 특정 URL의 모든 데이터 조회"""
        participants = {}
        all_commenters = []
        last_id = None
        title = None
        prizes = None
        memo = None
        winners = None
        allow_duplicates = True
        allowed_list = None

        if not self.supabase:
            return participants, last_id, all_commenters, title, prizes, memo, winners, allow_duplicates, allowed_list

        try:
            # 1. Post 정보
            res = self.supabase.table("posts").select("*").eq("url", url).execute()
            if res.data:
                post = res.data[0]
                last_id = post.get('last_comment_id')
                title = post.get('title')
                prizes = post.get('prizes')
                memo = post.get('memo')
                winners = post.get('winners')
                allowed_list = post.get('allowed_list')
                if post.get('allow_duplicates') is not None:
                    allow_duplicates = bool(post['allow_duplicates'])

            # 2. Participants
            try:
                res = self.supabase.table("participants").select("author, count, created_at").eq("url", url).execute()
            except:
                res = self.supabase.table("participants").select("author, count").eq("url", url).execute()
            
            if res.data:
                participants = {row['author']: (row['count'], row.get('created_at')) for row in res.data}

            # 3. Commenters
            try:
                res = self.supabase.table("commenters").select("author, created_at").eq("url", url).execute()
            except:
                res = self.supabase.table("commenters").select("author").eq("url", url).execute()
            
            if res.data:
                all_commenters = [{'name': row['author'], 'created_at': row.get('created_at')} for row in res.data]

        except Exception as e:
            print(f"DEBUG: [Supabase Get Data Error] {e}")

        return participants, last_id, all_commenters, title, prizes, memo, winners, allow_duplicates, allowed_list

    @retry_supabase
    def set_active_url(self, url: str):
        """활성 이벤트 URL 설정"""
        if not self.supabase: return
        
        # 모든 활성 플래그 해제
        self.supabase.table("posts").update({"is_active": False}).neq("url", "void_bypass").execute()
        
        if url:
            self.supabase.table("posts").upsert({"url": url, "is_active": True}, on_conflict="url").execute()
            print(f"DEBUG: [Supabase] Active URL set: {url}")

    @retry_supabase
    def get_active_url(self) -> str:
        """현재 활성화된 이벤트 URL 조회"""
        if not self.supabase: return None
        
        res = self.supabase.table("posts").select("url").eq("is_active", True).limit(1).execute()
        if res.data:
            return res.data[0]["url"]
        return None

    @retry_supabase
    def update_timestamp(self, url: str):
        """업데이트 타임스탬프 갱신"""
        if not self.supabase: return
        self.supabase.table("posts").update({"updated_at": datetime.now().isoformat()}).eq("url", url).execute()

    @retry_supabase
    def get_all_urls(self) -> List[str]:
        """저장된 모든 URL 목록 조회"""
        if not self.supabase: return []
        
        res = self.supabase.table("posts").select("url").order("updated_at", desc=True).execute()
        return [row["url"] for row in res.data] if res.data else []
