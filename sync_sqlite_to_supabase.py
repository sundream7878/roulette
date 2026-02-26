import sqlite3
import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

db_path = "standalone_comment_monitor/comments.db"
if not os.path.exists(db_path):
    print("SQLite DB not found.")
    exit()

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("Starting sync to Supabase...")

# 1. Sync Posts
cursor.execute("SELECT * FROM posts")
posts = cursor.fetchall()
for p in posts:
    post_data = dict(p)
    supabase.table("posts").upsert(post_data).execute()
    print(f"Synced post: {post_data['url']}")

# 2. Sync participants
cursor.execute("SELECT * FROM participants")
participants = cursor.fetchall()
if participants:
    p_batch = [dict(p) for p in participants]
    # batch insert can sometimes have limits, but we have a small amount
    for i in range(0, len(p_batch), 100):
        supabase.table("participants").upsert(p_batch[i:i+100]).execute()
    print(f"Synced {len(participants)} participants")

# 3. Sync commenters
cursor.execute("SELECT * FROM commenters")
commenters = cursor.fetchall()
if commenters:
    c_batch = [dict(c) for c in commenters]
    for i in range(0, len(c_batch), 100):
        supabase.table("commenters").upsert(c_batch[i:i+100]).execute()
    print(f"Synced {len(commenters)} commenters")

print("Sync complete!")
