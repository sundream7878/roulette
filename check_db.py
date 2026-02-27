import sqlite3
import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# Check SQLite
conn = sqlite3.connect('standalone_comment_monitor/comments.db')
c = conn.cursor()
c.execute("SELECT url, title, prizes FROM posts WHERE url='test_sync_url'")
sqlite_data = c.fetchone()
print(f"SQLite Data: {sqlite_data}")

# Check Supabase
res = supabase.table('posts').select('*').eq('url', 'test_sync_url').execute()
print(f"Supabase Data: {res.data}")
