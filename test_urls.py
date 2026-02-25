from standalone_comment_monitor.scraper import NaverCommentMonitor
import json

def test():
    monitor = NaverCommentMonitor(use_selenium=False) # API 속도 확인용
    
    urls = [
        "https://cafe.naver.com/f-e/cafes/27870803/articles/67793",
        "https://cafe.naver.com/f-e/cafes/27870803/articles/67774"
    ]
    
    for url in urls:
        print(f"\n--- Testing URL: {url} ---")
        comments = monitor.get_new_comments(url)
        print(f"Count: {len(comments)}")
        nicknames = [c['author_nickname'] for c in comments[:3]]
        print(f"Top 3 Nicks: {nicknames}")

if __name__ == "__main__":
    test()
