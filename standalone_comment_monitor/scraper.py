import requests
import json
import time
from typing import List, Dict, Optional, Any
from datetime import datetime
from urllib.parse import urlencode
from .parsers import parse_post_ids_from_url

# 타입 힌트용
CommentData = Dict[str, Any]

class NaverCommentMonitor:
    """
    네이버 카페 댓글 모니터링 모듈 (새 API 버전)
    """
    
    BASE_API_URL = "https://apis.naver.com/cafe-web/cafe-articleapi/v2.1/cafes/{}/articles/{}"
    
    def __init__(self, user_agent: str = None):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://cafe.naver.com/",
            "Origin": "https://cafe.naver.com",
        })

    def get_new_comments(self, post_url: str, last_comment_id: Optional[str] = None) -> List[CommentData]:
        """
        특정 게시글의 모든 댓글을 수집합니다 (새 API 버전 - 페이지네이션 지원).
        """
        clubid, articleid = parse_post_ids_from_url(post_url)
        print(f"DEBUG: Parsed IDs - clubid: {clubid}, articleid: {articleid}")
        
        if not clubid or not articleid:
            # URL 파싱 실패 시 직접 추출 시도
            import re
            club_match = re.search(r'cafes/(\d+)', post_url)
            article_match = re.search(r'articles/(\d+)', post_url)
            if club_match and article_match:
                clubid = club_match.group(1)
                articleid = article_match.group(1)
                print(f"DEBUG: Fallback Parsed IDs - clubid: {clubid}, articleid: {articleid}")
            else:
                raise ValueError(f"Invalid URL format: {post_url}")
            
        new_comments = []
        
        # 새 API URL 생성
        base_api_url = self.BASE_API_URL.format(clubid, articleid)
        
        try:
            # 페이지네이션 루프 (올바른 구현)
            next_cursor = None
            page_num = 1
            MAX_PAGES = 50  # 안전장치
            seen_cursors = set()  # 중복 커서 감지
            
            while page_num <= MAX_PAGES:
                # API URL 생성
                if next_cursor:
                    # next_cursor가 딕셔너리면 JSON 문자열로 변환
                    if isinstance(next_cursor, dict):
                        cursor_str = json.dumps(next_cursor, separators=(',', ':'))
                    else:
                        cursor_str = str(next_cursor)
                    
                    # 이미 본 커서면 중단
                    if cursor_str in seen_cursors:
                        print(f"DEBUG: Duplicate cursor detected, stopping")
                        break
                    seen_cursors.add(cursor_str)
                    
                    params = {'commentCursor': cursor_str}
                    api_url = f"{base_api_url}?{urlencode(params)}"
                else:
                    api_url = base_api_url
                
                print(f"DEBUG: Page {page_num} - Requesting: {api_url[:100]}...")
                response = self.session.get(api_url, timeout=10)
                print(f"DEBUG: Response Status: {response.status_code}")
                response.raise_for_status()
                
                try:
                    data = response.json()
                except json.JSONDecodeError:
                    print("DEBUG: JSON decode error")
                    break
                    
                result = data.get("result", {})
                if not result:
                    print("DEBUG: No result in response")
                    break
                    
                comments_data = result.get("comments", {})
                comment_list = comments_data.get("items", [])
                
                print(f"DEBUG: Page {page_num} - Received {len(comment_list)} comments")
                
                if not comment_list:
                    print("DEBUG: No more comments")
                    break
                
                # 댓글 데이터 처리
                before_count = len(new_comments)
                for raw in comment_list:
                    normalized = self._normalize_comment(raw)
                    new_comments.append(normalized)
                
                added_count = len(new_comments) - before_count
                print(f"DEBUG: Added {added_count} comments (total: {len(new_comments)})")
                
                # 다음 커서 확인
                next_cursor = comments_data.get("next")
                print(f"DEBUG: Next cursor: {next_cursor}")
                
                # 종료 조건
                if not next_cursor or next_cursor == "":
                    print(f"DEBUG: No more pages")
                    break
                
                page_num += 1
                time.sleep(0.3)  # 서버 부하 방지
            
            print(f"DEBUG: Total collected: {len(new_comments)} comments from {page_num} pages")
            
            # ID 오름차순 정렬
            new_comments.sort(key=lambda x: int(x['comment_id']))
            
        except Exception as e:
            print(f"[Error] Failed to fetch comments: {e}")
            import traceback
            traceback.print_exc()
        
        return new_comments

    def _normalize_comment(self, raw: dict) -> CommentData:
        """API 원본 데이터를 표준 포맷으로 변환 (새 API 버전)"""
        
        # writer 객체에서 정보 추출
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
            "post_id": "",  # 게시글 ID는 별도로 관리
            "author_nickname": writer.get("nick", ""),
            "author_id": writer.get("memberKey", ""),
            "content": raw.get("content", ""),
            "created_at": iso_date,
            "is_deleted": raw.get("isDeleted", False),
            "is_secret": False,
            "ref_comment_id": str(raw.get("refId")) if raw.get("refId") != raw.get("id") else None
        }
