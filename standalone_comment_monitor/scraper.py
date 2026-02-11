import requests
import json
import time
from typing import List, Dict, Optional, Any
from datetime import datetime
from .parsers import parse_post_ids_from_url

# 타입 힌트용
CommentData = Dict[str, Any]

class NaverCommentMonitor:
    """
    네이버 카페 댓글 모니터링 모듈
    - 상태(마지막 수집 ID)를 관리하지 않음 (함수 인자로 받음)
    - 순수하게 데이터를 가져오고 정제하여 반환함
    """
    
    BASE_API_URL = "https://cafe.naver.com/CommentView.nhn"
    
    def __init__(self, user_agent: str = None):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": "https://cafe.naver.com/",
        })

    def get_new_comments(self, post_url: str, last_comment_id: Optional[str] = None) -> List[CommentData]:
        """
        특정 게시글의 새로운 댓글을 수집합니다.
        
        Args:
            post_url (str): 게시글 URL
            last_comment_id (str, optional): 마지막으로 수집했던 댓글의 comment_id. 
                                           이 ID보다 나중에 작성된(ID가 더 큰) 댓글만 반환합니다.
        
        Returns:
            List[CommentData]: 정제된 댓글 리스트 (오래된 순서대로 정렬됨)
        """
        clubid, articleid = parse_post_ids_from_url(post_url)
        if not clubid or not articleid:
            raise ValueError(f"Invalid URL format: {post_url}")
            
        new_comments = []
        page = 1
        
        # 마지막 ID가 있으면 정수로 변환해둠 (비교용)
        last_id_int = int(last_comment_id) if last_comment_id and str(last_comment_id).isdigit() else -1
        
        while True:
            # 1. API 요청
            params = {
                "search.clubid": clubid,
                "search.articleid": articleid,
                "search.page": page,
                "search.orderBy": "desc" # 최신순으로 가져와서 끊기
            }
            
            try:
                response = self.session.get(self.BASE_API_URL, params=params, timeout=10)
                response.raise_for_status()
                
                # 네이버는 가끔 JSON을 jsonp 형태나 HTML 섞어서 줄 때가 있음. 순수 JSON 파싱 시도.
                try:
                    data = response.json()
                except json.JSONDecodeError:
                    # JSONP 등의 경우 텍스트 처리 필요할 수 있음 (현재 표준 API는 JSON 반환)
                    # 혹시 모를 에러 처리
                    break
                    
                result = data.get("result", {})
                if not result:
                    break
                    
                comment_list = result.get("list", [])
                if not comment_list:
                    break
                
                # 2. 데이터 처리
                # 이번 페이지에서 유효한 댓글 추출
                page_valid_comments = []
                stop_fetching = False
                
                for raw in comment_list:
                    cmt_id_str = str(raw.get("commentid") or raw.get("id") or "0")
                    if not cmt_id_str.isdigit():
                        continue
                        
                    cmt_id_int = int(cmt_id_str)
                    
                    # 이미 수집한 지점(last_id) 이하거나 같으면 중단 (최신순 정렬이므로)
                    if last_id_int >= 0 and cmt_id_int <= last_id_int:
                        stop_fetching = True
                        continue # 이 루프에서는 건너뛰지만, for문 밖에서 break 필요
                        
                    # 수집 대상
                    normalized = self._normalize_comment(raw)
                    page_valid_comments.append(normalized)
                
                # 수집된 것들을 전체 리스트에 추가
                new_comments.extend(page_valid_comments)
                
                if stop_fetching:
                    break
                
                # 다음 페이지 확인
                # result['hasNext'] 가 false이면 종료
                if not result.get("hasNext"):
                    break
                    
                page += 1
                time.sleep(0.2) # 서버 부하 방지
                
            except Exception as e:
                # 네트워크 에러 등 발생 시, 지금까지 수집한 것만이라도 반환할지, 에러를 낼지 결정
                # 여기선 안전하게 빈 리스트 혹은 수집분 반환
                print(f"[Error] Failed to fetch comments: {e}")
                break
        
        # 반환할 때는 ID 오름차순(과거->최신)으로 정렬하여 제공하는 것이 일반적
        # (호출자가 마지막 ID를 갱신하기 좋도록)
        new_comments.sort(key=lambda x: int(x['comment_id']))
        
        return new_comments

    def _normalize_comment(self, raw: dict) -> CommentData:
        """API 원본 데이터를 표준 포맷으로 변환"""
        
        # 날짜 포맷 변환 (ISO 8601)
        # 네이버 API는 보통 "2024.02.11. 12:34" 또는 timestamp로 줌
        reg_date = raw.get("reg_date") or raw.get("regDate")
        iso_date = str(reg_date)
        
        # 간단한 포맷 정규화 시도
        try:
            if reg_date:
                # 2024.02.11. 12:34:56
                dt = datetime.strptime(str(reg_date), "%Y.%m.%d. %H:%M:%S")
                iso_date = dt.isoformat()
        except:
            pass

        return {
            "comment_id": str(raw.get("commentid") or raw.get("id")),
            "post_id": str(raw.get("articleid") or raw.get("articleId")),
            "author_nickname": str(raw.get("writernick") or raw.get("writerNickname")),
            "author_id": str(raw.get("writerid") or raw.get("writerId")),
            "content": str(raw.get("content") or ""),
            "created_at": iso_date,
            "is_deleted": bool(raw.get("deleted")),
            "is_secret": bool(raw.get("isSecret")),
            "ref_comment_id": str(raw.get("refcommentid") or "") if raw.get("refcommentid") else None # 대댓글인 경우 부모 ID
        }
