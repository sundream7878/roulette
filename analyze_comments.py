import requests
import json

def analyze_comments():
    """
    네이버 카페 댓글 API 응답 구조 분석
    실제 댓글 44개인데 120개가 수집되는 이유 파악
    """
    clubid = "27870803"
    articleid = "67767"
    
    # v2 API 테스트
    url = f"https://apis.naver.com/cafe-web/cafe-articleapi/v2/cafes/{clubid}/articles/{articleid}/comments?page=1&size=100&orderBy=asc"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://cafe.naver.com/",
    }
    
    print(f"Testing URL: {url}\n")
    
    response = requests.get(url, headers=headers)
    print(f"Status: {response.status_code}\n")
    
    if response.status_code == 200:
        data = response.json()
        result = data.get("result", {})
        comments_data = result.get("comments", {})
        items = comments_data.get("items", [])
        
        print(f"Total items returned: {len(items)}\n")
        
        # 댓글 구조 분석
        print("=== Comment Structure Analysis ===")
        
        # 원댓글과 답글 구분
        original_comments = []
        reply_comments = []
        
        for item in items:
            comment_id = item.get("id")
            ref_id = item.get("refId")
            is_ref = item.get("isRef", False)
            writer = item.get("writer", {})
            nick = writer.get("nick", "")
            content = item.get("content", "")[:30]
            
            if comment_id == ref_id or not is_ref:
                original_comments.append(item)
                print(f"[원댓글] ID:{comment_id} | {nick} | {content}...")
            else:
                reply_comments.append(item)
                print(f"  [답글] ID:{comment_id} (ref:{ref_id}) | {nick} | {content}...")
        
        print(f"\n=== Summary ===")
        print(f"원댓글 (Original): {len(original_comments)}개")
        print(f"답글 (Replies): {len(reply_comments)}개")
        print(f"전체 (Total): {len(items)}개")
        
        # 중복 확인
        print(f"\n=== Duplicate Check ===")
        comment_ids = [item.get("id") for item in items]
        unique_ids = set(comment_ids)
        print(f"Total IDs: {len(comment_ids)}")
        print(f"Unique IDs: {len(unique_ids)}")
        if len(comment_ids) != len(unique_ids):
            print("⚠️ DUPLICATES FOUND!")
        
        # 작성자 분석
        print(f"\n=== Writer Analysis ===")
        writers = {}
        for item in items:
            writer = item.get("writer", {})
            nick = writer.get("nick", "Unknown")
            writers[nick] = writers.get(nick, 0) + 1
        
        print(f"Unique writers: {len(writers)}")
        print("Top writers:")
        for nick, count in sorted(writers.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {nick}: {count}개")
        
        # 페이징 정보
        print(f"\n=== Paging Info ===")
        paging = comments_data.get("paging", {})
        print(f"isLastPage: {paging.get('isLastPage')}")
        print(f"nextCursor: {paging.get('nextCursor')}")
        
    else:
        print(f"Error: {response.status_code}")
        print(response.text[:500])

if __name__ == "__main__":
    analyze_comments()
