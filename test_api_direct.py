import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

def test_api():
    clubid = "27870803"
    articleid = "67661"
    url = f"https://apis.naver.com/cafe-web/cafe-articleapi/v2/cafes/{clubid}/articles/{articleid}/comments"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": f"https://cafe.naver.com/ca-fe/web/cafes/{clubid}/articles/{articleid}",
    }
    
    # Try without cookies first
    print(f"Testing API (No Cookies): {url}")
    res = requests.get(url, headers=headers)
    print(f"Status: {res.status_code}")
    try:
        data = res.json()
        print(f"Comment Count: {data.get('result', {}).get('totalCount', 0)}")
        if data.get('result', {}).get('comments', {}).get('items'):
            print("Found comments!")
        else:
            print("No comments found in JSON.")
            # print(json.dumps(data, indent=2, ensure_ascii=False))
    except:
        print("Failed to parse JSON or unexpected format.")
        print(res.text[:500])

    # Try with cookies if available
    cookie_path = r"f:\roulette-1\standalone_comment_monitor\cookies.json"
    if os.path.exists(cookie_path):
        print(f"\nTesting API (With Cookies): {url}")
        with open(cookie_path, 'r', encoding='utf-8') as f:
            cookies_list = json.load(f)
            cookies = {c['name']: c['value'] for c in cookies_list}
            
        res = requests.get(url, headers=headers, cookies=cookies)
        print(f"Status: {res.status_code}")
        try:
            data = res.json()
            print(f"Comment Count: {data.get('result', {}).get('totalCount', 0)}")
        except:
            print("Failed to parse JSON.")

if __name__ == "__main__":
    test_api()
