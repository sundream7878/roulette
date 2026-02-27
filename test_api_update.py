import requests

url = "http://127.0.0.1:5000/api/update_event_settings"
data = {
    "url": "test_sync_url",
    "title": "My Title 2",
    "prizes": "Prize 1\nPrize 2",
    "allow_duplicates": False
}

try:
    response = requests.post(url, json=data)
    print(response.status_code)
    print(response.json())
except Exception as e:
    print(f"Error: {e}")

