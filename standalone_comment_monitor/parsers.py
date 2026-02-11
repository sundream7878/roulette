import re
from urllib.parse import urlparse, parse_qs
from typing import Optional, Tuple

def parse_post_ids_from_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    네이버 카페 게시글 URL에서 clubid와 articleid를 추출합니다.
    
    Args:
        url (str): 카페 게시글 URL (모바일/PC/단축URL 등)
        
    Returns:
        (clubid, articleid) 튜플. 실패 시 (None, None) 반환.
    """
    if not url:
        return None, None
        
    try:
        # 1. PC 버전 (/ArticleRead.nhn)
        if "ArticleRead.nhn" in url:
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            clubid = query.get("clubid", [None])[0]
            articleid = query.get("articleid", [None])[0]
            if clubid and articleid:
                return str(clubid), str(articleid)

        # 2. 모바일/RESTful 경로 (/cafes/.../articles/...)
        # 예: https://m.cafe.naver.com/ca-fe/web/cafes/12345/articles/67890
        match = re.search(r'/cafes/(\d+)/articles/(\d+)', url)
        if match:
            return match.group(1), match.group(2)
            
        # 3. 구형 단축 경로 (/카페이름/글번호)
        # 이 경우 clubid를 URL만으로 알 수 없으므로, 크롤러 내부에서 추가 조회가 필요할 수 있음.
        # 현 모듈은 순수 URL 파싱만 담당하므로, 이 패턴은 cafe_name -> clubid 매핑 없이는 지원 제한됨.
        # 다만, 일반적인 브라우저 주소창 URL은 위 1, 2번 패턴임.
        
        return None, None
        
    except Exception:
        return None, None
