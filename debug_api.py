import requests
import json

def test_v2_comment_structure():
    clubid = "27870803"
    articleid = "67767"
    url = f"https://apis.naver.com/cafe-web/cafe-articleapi/v2/cafes/{clubid}/articles/{articleid}/comments?size=2"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://m.cafe.naver.com/",
    }
    
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        items = data.get('result', {}).get('comments', {}).get('items', [])
        if items:
            print("Full structure of first comment:")
            print(json.dumps(items[0], indent=2, ensure_ascii=False))
        else:
            print("No comments found in v2 response.")
    else:
        print(f"Error: {response.status_code}")

if __name__ == "__main__":
    test_v2_comment_structure()
