import os
from standalone_comment_monitor.scraper import NaverCommentMonitor
from dotenv import load_dotenv

load_dotenv()

def test_scrape():
    url = "https://cafe.naver.com/ca-fe/web/cafes/27870803/articles/67661"
    monitor = NaverCommentMonitor(url)
    
    print(f"Testing scrape for: {url}")
    # get_new_comments(post_url, last_id=None) returns (new_comments, last_id)
    new_comments, last_id = monitor.get_new_comments(url, None)
    
    print(f"Results:")
    print(f"  Count: {len(new_comments)}")
    print(f"  Last ID: {last_id}")
    
    if len(new_comments) > 0:
        print("  First few commenters:", [c['author'] for c in new_comments[:5]])
    else:
        # Check if Selenium fallback is needed or if there's an error
        print("  No comments found. Trying to see why...")
        # monitor.fetch_comments returns empty list if any error occurs or 0 comments.
        pass

if __name__ == "__main__":
    test_scrape()
