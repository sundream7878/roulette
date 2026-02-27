"""
Supabase posts 테이블을 로컬 SQLite에서 복구하는 스크립트
"""
import sqlite3
import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

DB_PATH = "standalone_comment_monitor/comments.db"
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
c = conn.cursor()

# 1. posts 테이블 복구
print("=== posts 복구 ===")
c.execute("SELECT * FROM posts")
posts = c.fetchall()
for row in posts:
    data = dict(row)
    # boolean 처리
    data['is_active'] = bool(data.get('is_active', False))
    data['allow_duplicates'] = bool(data.get('allow_duplicates', True))
    print(f"  upsert post: {data['url'][:60]} | title={data['title']} | prizes={data['prizes']}")
    supabase.table('posts').upsert(data).execute()

# 2. participants 복구
print("\n=== participants 복구 ===")
c.execute("SELECT * FROM participants")
participants = c.fetchall()
if participants:
    batch = [dict(r) for r in participants]
    supabase.table('participants').upsert(batch).execute()
    print(f"  {len(batch)} participants upserted")
else:
    print("  participants 없음")

# 3. commenters 복구
print("\n=== commenters 복구 ===")
c.execute("SELECT * FROM commenters")
commenters = c.fetchall()
if commenters:
    batch = [dict(r) for r in commenters]
    supabase.table('commenters').upsert(batch).execute()
    print(f"  {len(batch)} commenters upserted")
else:
    print("  commenters 없음")

conn.close()
print("\n✅ 복구 완료! Supabase posts 확인:")
res = supabase.table('posts').select('url, title, prizes, is_active').execute()
for r in res.data:
    print(f"  Active={r['is_active']} | Title={r['title']} | URL={r['url'][:60]}")
