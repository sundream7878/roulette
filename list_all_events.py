import sqlite3
import os

base_dir = r"f:\roulette-1\standalone_comment_monitor"
db_path = os.path.join(base_dir, "comments.db")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT url, title, prizes FROM posts")
rows = cursor.fetchall()

print(f"Total rows in posts: {len(rows)}")
for row in rows:
    print(f"URL: {row[0]}")
    print(f"  Title: {row[1]}")
    print(f"  Prizes: {row[2]}")
    print("-" * 20)

conn.close()
