import sys
import os
# Add current directory to path
sys.path.append(os.getcwd())

from standalone_comment_monitor.scraper import NaverCommentMonitor

def test_scraper():
    url = "https://cafe.naver.com/ca-fe/web/cafes/27870803/articles/67806"
    monitor = NaverCommentMonitor(use_selenium=False)
    print(f"Testing scraper for URL: {url}")
    try:
        comments = monitor.get_new_comments(url)
        print(f"Found {len(comments)} comments!")
        if comments:
            print(f"First comment: {comments[0]['author_nickname']}: {comments[0]['content'][:20]}")
    except Exception as e:
        print(f"Scraper FAILED: {e}")

if __name__ == "__main__":
    test_scraper()
