import sqlite3

db_path = "f:\\roulette-1\\test_comments.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("Recent posts in local SQLite:")
cursor.execute("SELECT url, title, prizes, is_active, updated_at FROM posts ORDER BY updated_at DESC LIMIT 5")
for row in cursor.fetchall():
    print(f"URL: {row['url']}")
    print(f"Title: {row['title']}")
    print(f"Active: {row['is_active']}")
    print("-" * 20)

cursor.execute("SELECT url FROM posts WHERE url LIKE '%67661%'")
match = cursor.fetchone()
if match:
    print(f"Found match for 67661: {match['url']}")

conn.close()
