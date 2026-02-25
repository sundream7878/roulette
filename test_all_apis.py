import requests
import json
from urllib.parse import urlencode

def test_all_comment_apis():
    """
    여러 네이버 카페 댓글 API 엔드포인트 테스트
    실제 44개 댓글을 모두 가져올 수 있는 API 찾기
    """
    clubid = "27870803"
    articleid = "67767"
    
    print("=" * 80)
    print("네이버 카페 댓글 API 전체 테스트")
    print("=" * 80)
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://cafe.naver.com/",
        "Accept": "application/json, text/plain, */*",
    }
    
    # 테스트할 API 목록
    apis = [
        {
            "name": "v2 API (current)",
            "url": f"https://apis.naver.com/cafe-web/cafe-articleapi/v2/cafes/{clubid}/articles/{articleid}/comments",
            "params": {"page": 1, "size": 100, "orderBy": "asc"}
        },
        {
            "name": "v2 API (no page)",
            "url": f"https://apis.naver.com/cafe-web/cafe-articleapi/v2/cafes/{clubid}/articles/{articleid}/comments",
            "params": {"size": 100, "orderBy": "asc"}
        },
        {
            "name": "v2.1 API",
            "url": f"https://apis.naver.com/cafe-web/cafe-articleapi/v2.1/cafes/{clubid}/articles/{articleid}/comments",
            "params": {"page": 1, "size": 100, "orderBy": "asc"}
        },
        {
            "name": "Article Detail API",
            "url": f"https://apis.naver.com/cafe-web/cafe-articleapi/v2/cafes/{clubid}/articles/{articleid}",
            "params": {"useCafeId": "false", "requestFrom": "A"}
        },
        {
            "name": "CommentList.nhn",
            "url": f"https://apis.naver.com/cafe-web/cafe2/CommentList.json",
            "params": {"search.clubid": clubid, "search.articleid": articleid, "search.page": 1, "search.menuid": 1}
        },
    ]
    
    for api in apis:
        print(f"\n{'=' * 80}")
        print(f"Testing: {api['name']}")
        print(f"URL: {api['url']}")
        print(f"Params: {api['params']}")
        print("-" * 80)
        
        try:
            response = requests.get(api['url'], params=api['params'], headers=headers, timeout=10)
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    
                    # 댓글 개수 찾기 (다양한 경로 시도)
                    comment_count = 0
                    comment_items = []
                    
                    # v2/v2.1 API 구조
                    if "result" in data:
                        result = data["result"]
                        if "comments" in result:
                            comment_items = result["comments"].get("items", [])
                            comment_count = len(comment_items)
                        elif "commentList" in result:
                            comment_items = result["commentList"]
                            comment_count = len(comment_items)
                        elif "article" in result:
                            article = result["article"]
                            if "commentList" in article:
                                comment_items = article["commentList"].get("items", [])
                                comment_count = len(comment_items)
                    
                    # CommentList.nhn 구조
                    elif "message" in data:
                        if "result" in data["message"]:
                            comment_items = data["message"]["result"].get("commentList", [])
                            comment_count = len(comment_items)
                    
                    print(f"✓ Comments found: {comment_count}")
                    
                    if comment_count > 0:
                        print(f"  First 3 comments:")
                        for i, item in enumerate(comment_items[:3]):
                            writer = item.get("writer", item.get("memberNickName", "Unknown"))
                            if isinstance(writer, dict):
                                writer = writer.get("nick", "Unknown")
                            content = item.get("content", item.get("commentContent", ""))[:30]
                            print(f"    {i+1}. {writer}: {content}...")
                    
                    # JSON 구조 출력 (처음 500자)
                    json_str = json.dumps(data, ensure_ascii=False, indent=2)
                    print(f"\n  JSON structure (first 500 chars):")
                    print(f"  {json_str[:500]}...")
                    
                except json.JSONDecodeError:
                    print(f"✗ Not JSON response")
                    print(f"  Response preview: {response.text[:200]}")
            else:
                print(f"✗ Error response")
                try:
                    error_data = response.json()
                    print(f"  Error: {error_data}")
                except:
                    print(f"  Response: {response.text[:200]}")
                    
        except Exception as e:
            print(f"✗ Exception: {e}")
    
    print(f"\n{'=' * 80}")
    print("테스트 완료")
    print("=" * 80)

if __name__ == "__main__":
    test_all_comment_apis()
