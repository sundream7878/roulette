import requests
import json

url = "http://127.0.0.1:5000/api/update_event_settings"
data = {
    "url": "test_encoding_url",
    "title": "한글 테스트 제목",
    "prizes": "한글 사은품 1\n한글 사은품 2",
    "allow_duplicates": False
}

try:
    print("Testing with requests...")
    response = requests.post(url, json=data)
    print(response.status_code)
    print(response.json())
except Exception as e:
    print(f"Error: {e}")
