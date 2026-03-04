import requests
import json

url = "http://localhost:5000/api/update_event_settings"
data = {
    "url": "https://cafe.naver.com/test_resilience",
    "title": "Test Title",
    "prizes": "Prize 1",
    "memo": "Test Memo",
    "allow_duplicates": True
}

print(f"Testing {url} with data: {data}")
try:
    response = requests.post(url, json=data)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Exception: {e}")
