import os
import sqlite3
from supabase import create_client

# Credentials
url = "https://kbnszmnmvppfbdpdefqw.supabase.co"
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtibnN6bW5tdnBwZmJkcGRlZnF3Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MjA3NTYwOCwiZXhwIjoyMDg3NjUxNjA4fQ.64uvX8k3lUNAtdXpcenSWv2ofuUzDja9_VdJtabkKsw"
supabase = create_client(url, key)

target_url = "https://cafe.naver.com/ca-fe/web/cafes/27870803/articles/67661"

# Get data from local SQLite
db_path = "f:\\roulette-1\\test_comments.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()
cursor.execute("SELECT * FROM posts WHERE url = ?", (target_url,))
row = cursor.fetchone()

if row:
    print(f"Found local data for {target_url}")
    post_data = {
        "url": target_url,
        "title": row["title"],
        "prizes": row["prizes"],
        "memo": row["memo"],
        "is_active": True,
        "allow_duplicates": bool(row["allow_duplicates"]),
        "winners": row["winners"]
    }
    print(f"Syncing to Supabase: {post_data['title']}")
    supabase.table("posts").upsert(post_data, on_conflict="url").execute()
    print("Verification:")
    res = supabase.table("posts").select("*").eq("url", target_url).execute()
    print(res.data)
else:
    print(f"No local data found for {target_url}")

conn.close()
StandardError: (1, 'no such table: posts')
