import sqlite3
import os

# 디렉토리 설정
base_dir = r"f:\roulette-1\standalone_comment_monitor"
db_path = os.path.join(base_dir, "comments.db")

url = "https://cafe.naver.com/ca-fe/web/cafes/27870803/articles/67357"

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print(f"Checking data for URL: {url}")
cursor.execute("SELECT title, prizes, winners FROM posts WHERE url = ?", (url,))
row = cursor.fetchone()

if row:
    print(f"Title: {row[0]}")
    print(f"Prizes: {row[1]}")
    print(f"Winners: {row[2]}")
else:
    print("No data found for this URL.")

conn.close()
