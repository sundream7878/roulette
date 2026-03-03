import requests
import json

BASE_URL = "http://localhost:5000"
URL = "https://cafe.naver.com/ca-fe/web/cafes/27870803/articles/67357"

try:
    print(f"Triggering fetch_comments for {URL}...")
    # This matches the frontend call to /api/fetch_comments
    resp = requests.post(f"{BASE_URL}/api/fetch_comments", json={'url': URL, 'incremental': True})
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text}")
except Exception as e:
    print(f"Error: {e}")
