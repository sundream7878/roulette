import requests
import json
import os
import time
from typing import List, Dict, Optional, Any
from datetime import datetime
from urllib.parse import urlencode
from .parsers import parse_post_ids_from_url

# 타입 힌트용
CommentData = Dict[str, Any]

class NaverCommentMonitor:
    """
    네이버 카페 댓글 모니터링 모듈 (다중 API 전략 + Selenium 폴백)
    """
    
    BASE_API_URL = "https://apis.naver.com/cafe-web/cafe-articleapi/v2/cafes/{}/articles/{}/comments"
    
    def __init__(self, user_agent: str = None, use_selenium: bool = True):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://cafe.naver.com/",
            "Origin": "https://cafe.naver.com",
        })
        
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.cookie_path = os.path.join(self.base_dir, "cookies.json")
        
        # 쿠키 로드 (있으면)
        self.load_cookies()
        
        # Selenium 폴백 활성화 여부
        self.use_selenium = use_selenium
        self.selenium_scraper = None
        if use_selenium:
            try:
                from .selenium_scraper import SeleniumCommentScraper
                self.selenium_scraper = SeleniumCommentScraper()
                print("DEBUG: Selenium fallback enabled")
            except ImportError:
                print("DEBUG: Selenium not available, API-only mode")
                self.use_selenium = False

    def load_cookies(self):
        """저장된 쿠키가 있으면 세션에 적용"""
        if os.path.exists(self.cookie_path):
            try:
                with open(self.cookie_path, 'r', encoding='utf-8') as f:
                    cookies = json.load(f)
                    for cookie in cookies:
                        self.session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain', '.naver.com'))
                print(f"DEBUG: [API] Loaded cookies from {self.cookie_path}")
            except Exception as e:
                print(f"DEBUG: [API] Failed to load cookies: {e}")

    def clear_session(self):
        """세션 쿠키 및 상태 초기화 (다른 게시글 수집 시 간섭 방지)"""
        self.session.cookies.clear()
        self.load_cookies() # 다시 기본 로그인 쿠키는 로드
        print("DEBUG: [API] Session cookies cleared and reloaded")

    def get_new_comments(self, post_url: str, last_comment_id: Optional[str] = None) -> List[CommentData]:
        """
        특정 게시글의 모든 댓글을 수집합니다 (다중 전략 + 폴백).
        """
        # 세션 초기화 (캐시/상태 간섭 방지)
        if not last_comment_id:
            self.clear_session()
            
        clubid, articleid = parse_post_ids_from_url(post_url)
        print(f"DEBUG: [Scraper] Target IDs - clubid: {clubid}, articleid: {articleid} (URL: {post_url})")
        
        if not clubid or not articleid:
            # URL 파싱 실패 시 직접 추출 시도 (다양한 패턴 대응)
            import re
            print(f"DEBUG: parse_post_ids_from_url failed, trying regex fallback for {post_url}")
            
            # 패턴 1: 카페 ID와 글 ID가 모두 있는 경우 (cafes/123/articles/456)
            match = re.search(r'cafes/(\d+)/articles/(\d+)', post_url)
            if match:
                clubid, articleid = match.group(1), match.group(2)
            else:
                # 패턴 2: URL 마지막이 숫자 스트링인 경우 (글 ID로 간주)
                # 예: https://cafe.naver.com/joonggonara/1234567
                article_match = re.search(r'/(\d{5,})$', post_url.split('?')[0])
                if article_match:
                    articleid = article_match.group(1)
                    print(f"DEBUG: Identified articleid from end of URL: {articleid}")
            
            if not articleid:
                raise ValueError(f"URL에서 게시글 ID를 찾을 수 없습니다: {post_url}")
            
            # clubid가 여전히 없으면(별명 주소), API를 통해 clubid를 알아내야 함 (추후 개선)
            # 일단은 parse_post_ids_from_url이 대부분 처리할 것임
        
        # 전략 1: 다중 API 시도
        print("DEBUG: [Strategy] Trying multiple API approaches...")
        api_comments = self._try_all_api_strategies(clubid, articleid)
        
        # 중복 제거 후 실제 고유 댓글 수 확인
        unique_api_comments = self._deduplicate_by_id(api_comments)
        
        # 필터링 로직 추가 (Incremental Fetch 지원)
        final_comments = unique_api_comments
        if last_comment_id:
            try:
                # Naver ID는 보통 숫자 형태이므로 숫자로 변환하여 비교 시도
                last_id_int = int(last_comment_id)
                def get_numeric_id(c):
                    cid = str(c.get('comment_id', 0))
                    # 'selenium_123' 같은 경우 숫자 부분만 추출 시도 (보강)
                    if '_' in cid: 
                        import re
                        match = re.search(r'\d+', cid)
                        return int(match.group()) if match else 0
                    return int(cid) if cid.isdigit() else 0

                final_comments = [c for c in unique_api_comments if get_numeric_id(c) > last_id_int]
            except ValueError:
                # 숫자가 아닌 경우 리스트 인덱스로 접근
                found = False
                for i, c in enumerate(unique_api_comments):
                    if c.get('comment_id') == last_comment_id:
                        final_comments = unique_api_comments[i+1:]
                        found = True
                        break
                if not found:
                    final_comments = unique_api_comments


        print(f"DEBUG: [API Result] Collected {len(api_comments)} total, {len(unique_api_comments)} unique, {len(final_comments)} new filtered via API")
        
        # 전략 2: Selenium 폴백
        if self.use_selenium and self.selenium_scraper:
            print(f"DEBUG: [Selenium] Starting browser collection for accurate results...")
            try:
                selenium_comments = self.selenium_scraper.get_comments_from_browser(post_url)
                if len(selenium_comments) > 0:
                    # Selenium 결과 필터링
                    filtered_selenium = selenium_comments
                    if last_comment_id:
                        try:
                            last_id_int = int(last_comment_id)
                            # 위 API 필터링과 동일한 로직 사용
                            def get_uid(c):
                                cid = str(c.get('comment_id', 0))
                                if '_' in cid: 
                                    import re
                                    match = re.search(r'\d+', cid)
                                    return int(match.group()) if match else 0
                                return int(cid) if cid.isdigit() else 0
                                
                            filtered_selenium = [c for c in selenium_comments if get_uid(c) > last_id_int]
                        except ValueError:
                            found = False
                            for i, c in enumerate(selenium_comments):
                                if c.get('comment_id') == last_comment_id:
                                    filtered_selenium = selenium_comments[i+1:]
                                    found = True
                                    break

                    
                    print(f"DEBUG: [Result] SUCCESS via Selenium ({len(selenium_comments)} items, {len(filtered_selenium)} filtered)")
                    return filtered_selenium
                else:
                    print(f"DEBUG: [Result] Selenium returned 0, FALLBACK to API ({len(final_comments)} items)")
                    return final_comments
                
            except Exception as e:
                print(f"DEBUG: [Selenium Error] {e}")
                return final_comments
        
        return final_comments

    
    def _try_all_api_strategies(self, clubid: str, articleid: str) -> List[CommentData]:
        """여러 API 전략 시도하여 최적의 결과 반환"""
        strategies = [
            ("v2 with pagination", lambda: self._try_v2_with_pagination(clubid, articleid)),
            ("v2 single request", lambda: self._try_v2_single(clubid, articleid)),
            ("v2 with cursor", lambda: self._try_v2_with_cursor(clubid, articleid)),
        ]
        
        best_result = []
        
        for strategy_name, strategy_func in strategies:
            try:
                print(f"DEBUG: [API Strategy] Trying {strategy_name}...")
                comments = strategy_func()
                print(f"DEBUG: [API Strategy] {strategy_name} returned {len(comments)} comments")
                
                if len(comments) > len(best_result):
                    best_result = comments
                    
                # 충분한 결과를 얻었으면 중단
                if len(comments) >= 40:
                    print(f"DEBUG: [API Strategy] Sufficient comments collected, stopping")
                    break
                    
            except Exception as e:
                print(f"DEBUG: [API Strategy] {strategy_name} failed: {e}")
                continue
        
        return best_result
    
    def _try_v2_with_pagination(self, clubid: str, articleid: str) -> List[CommentData]:
        """v2 API + 페이지네이션 (중복 감지)"""
        base_url = self.BASE_API_URL.format(clubid, articleid)
        all_comments = []
        seen_ids = set()
        
        for page in range(1, 11):  # 최대 10페이지
            params = {'page': page, 'size': 100, 'orderBy': 'asc'}
            url = f"{base_url}?{urlencode(params)}"
            
            response = self.session.get(url, timeout=10)
            if response.status_code != 200:
                break
            
            data = response.json()
            items = data.get("result", {}).get("comments", {}).get("items", [])
            
            if not items:
                break
            
            # 중복 감지
            new_items_count = 0
            for raw in items:
                comment_id = str(raw.get("id", ""))
                if comment_id and comment_id not in seen_ids:
                    seen_ids.add(comment_id)
                    all_comments.append(self._normalize_comment(raw, articleid))
                    new_items_count += 1
            
            print(f"DEBUG: [Pagination] Page {page}: {new_items_count} new comments (total: {len(all_comments)})")
            
            # 새로운 댓글이 없으면 중단 (같은 페이지 반복)
            if new_items_count == 0:
                print(f"DEBUG: [Pagination] No new comments on page {page}, stopping")
                break
            
            # 마지막 페이지 체크
            paging = data.get("result", {}).get("comments", {}).get("paging", {})
            if paging.get("isLastPage", False):
                break
            
            time.sleep(0.3)
        
        return all_comments
    
    def _try_v2_single(self, clubid: str, articleid: str) -> List[CommentData]:
        """v2 API + 단일 요청 (size=100)"""
        base_url = self.BASE_API_URL.format(clubid, articleid)
        params = {'size': 100, 'orderBy': 'asc'}
        url = f"{base_url}?{urlencode(params)}"
        
        response = self.session.get(url, timeout=10)
        if response.status_code != 200:
            return []
        
        data = response.json()
        items = data.get("result", {}).get("comments", {}).get("items", [])
        
        return [self._normalize_comment(raw, articleid) for raw in items]
    
    def _try_v2_with_cursor(self, clubid: str, articleid: str) -> List[CommentData]:
        """v2 API + 커서 기반 페이지네이션"""
        base_url = self.BASE_API_URL.format(clubid, articleid)
        all_comments = []
        cursor = None
        
        for _ in range(10):  # 최대 10회 시도
            params = {'size': 100, 'orderBy': 'asc'}
            if cursor:
                params['cursor'] = cursor
            
            url = f"{base_url}?{urlencode(params)}"
            response = self.session.get(url, timeout=10)
            
            if response.status_code != 200:
                break
            
            data = response.json()
            items = data.get("result", {}).get("comments", {}).get("items", [])
            
            if not items:
                break
            
            for raw in items:
                all_comments.append(self._normalize_comment(raw, articleid))
            
            # 다음 커서 확인
            paging = data.get("result", {}).get("comments", {}).get("paging", {})
            next_cursor = paging.get("nextCursor")
            
            if not next_cursor or paging.get("isLastPage", False):
                break
            
            cursor = next_cursor
            time.sleep(0.3)
        
        return all_comments
    
    def _deduplicate_by_id(self, comments: List[CommentData]) -> List[CommentData]:
        """comment_id 기반 중복 제거"""
        seen_ids = set()
        unique = []
        
        for comment in comments:
            comment_id = comment.get('comment_id', '')
            if comment_id and comment_id not in seen_ids:
                seen_ids.add(comment_id)
                unique.append(comment)
        
        return unique
    
    def _merge_and_deduplicate(self, api_comments: List[CommentData], selenium_comments: List[CommentData]) -> List[CommentData]:
        """API와 Selenium 결과 병합 및 중복 제거"""
        seen_keys = set()
        merged = []
        
        # API 댓글 우선 (더 정확한 데이터)
        for comment in api_comments:
            key = self._get_comment_key(comment)
            if key not in seen_keys:
                seen_keys.add(key)
                merged.append(comment)
        
        # Selenium 댓글 추가 (중복 제외)
        for comment in selenium_comments:
            key = self._get_comment_key(comment)
            if key not in seen_keys:
                seen_keys.add(key)
                merged.append(comment)
        
        return merged
    
    def _get_comment_key(self, comment: CommentData) -> tuple:
        """댓글 고유 키 생성 (중복 제거용)"""
        return (
            comment.get('comment_id', ''),
            comment.get('author_nickname', ''),
            comment.get('content', '')[:50],  # 내용 일부
            comment.get('created_at', '')
        )

    def _normalize_comment(self, raw: dict, articleid: str) -> CommentData:
        """API 원본 데이터를 표준 포맷으로 변환"""
        writer = raw.get("writer", {})
        
        # 날짜는 timestamp (milliseconds)
        update_date = raw.get("updateDate", 0)
        iso_date = ""
        try:
            if update_date:
                dt = datetime.fromtimestamp(update_date / 1000.0)
                iso_date = dt.isoformat()
        except:
            pass

        return {
            "comment_id": str(raw.get("id", "")),
            "post_id": articleid,
            "author_nickname": writer.get("nick", ""),
            "author_id": writer.get("memberKey", ""),
            "content": raw.get("content", ""),
            "created_at": iso_date,
            "is_deleted": raw.get("isDeleted", False),
            "is_secret": False,
            "ref_comment_id": str(raw.get("refId")) if raw.get("refId") != raw.get("id") else None,
            "source": "api"
        }
