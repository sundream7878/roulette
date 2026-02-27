import sqlite3
import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

conn = sqlite3.connect('standalone_comment_monitor/comments.db')
c = conn.cursor()

c.execute("SELECT url, title, prizes FROM posts WHERE url='test_encoding_url'")
sqlite_data = c.fetchone()
print(f"SQLite Data (test_encoding_url): {sqlite_data}")

# check the one the user reported: '67774'
c.execute("SELECT url, title, prizes FROM posts WHERE url LIKE '%67774%'")
user_data = c.fetchall()
for row in user_data:
    print(f"SQLite Data (user reported): {row}")

# Check Supabase
res = supabase.table('posts').select('url, title, prizes').eq('url', 'test_encoding_url').execute()
print(f"Supabase Data (test_encoding_url): {res.data}")

# check Supabase for user reported
res = supabase.table('posts').select('url, title, prizes').like('url', '%67774%').execute()
print(f"Supabase Data (user reported): {res.data}")
