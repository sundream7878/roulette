import sys
import os
import requests
import re
from urllib.parse import urlparse

# Add current dir to path
sys.path.append(os.getcwd())

from standalone_comment_monitor.scraper import NaverCommentMonitor
from standalone_comment_monitor.parsers import parse_post_ids_from_url

URL = "https://cafe.naver.com/f-e/cafes/27870803/articles/67793?boardtype=L&menuid=23&referrerAllArticles=false"

def diagnostic():
    print(f"--- Diagnostic for URL: {URL} ---")
    
    # 1. Parsing Check
    clubid, articleid = parse_post_ids_from_url(URL)
    print(f"Parsed clubid: {clubid}, articleid: {articleid}")
    
    # 2. Verify clubid via HTTP request to cafe
    print("Verifying clubid via HTTP...")
    try:
        resp = requests.get("https://cafe.naver.com/f-e", timeout=10)
        match = re.search(r'g_sClubId\s*=\s*"(\d+)"', resp.text)
        if match:
            real_clubid = match.group(1)
            print(f"Found clubid in page: {real_clubid}")
            if real_clubid != clubid:
                print(f"WARNING: Mismatch! Page says {real_clubid}, parser says {clubid}")
        else:
            print("Could not find clubid in page source using g_sClubId")
    except Exception as e:
        print(f"HTTP request failed: {e}")

    # 3. Test API collection
    print("\nTesting API-only collection...")
    monitor_api = NaverCommentMonitor(use_selenium=False)
    try:
        api_comments = monitor_api.get_new_comments(URL)
        print(f"API returned {len(api_comments)} comments.")
        if api_comments:
            print(f"First comment author: {api_comments[0].get('author_nickname')}")
    except Exception as e:
        print(f"API failed: {e}")

    # 4. Test Selenium collection
    print("\nTesting Selenium-enabled collection...")
    monitor_sel = NaverCommentMonitor(use_selenium=True)
    try:
        # We expect a print from scraper.py: "DEBUG: [Selenium] Starting browser collection..."
        sel_comments = monitor_sel.get_new_comments(URL)
        print(f"Final result (likely Selenium if > 0): {len(sel_comments)} comments.")
        
        # Check if selenium_scraper actually ran
        if monitor_sel.selenium_scraper:
            print("Selenium scraper was initialized.")
        else:
            print("Selenium scraper was NOT initialized.")
            
    except Exception as e:
        print(f"Selenium/Full collection failed: {e}")

if __name__ == "__main__":
    diagnostic()
