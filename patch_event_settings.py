import sqlite3
import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

conn = sqlite3.connect('standalone_comment_monitor/comments.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Get all posts with titles or prizes
cursor.execute("SELECT url, title, prizes FROM posts WHERE title IS NOT NULL OR prizes IS NOT NULL")
posts = cursor.fetchall()

print(f"Found {len(posts)} posts with titles/prizes in local DB.")

for p in posts:
    data = dict(p)
    # Only update title and prizes
    update_data = {}
    if data['title']:
        update_data['title'] = data['title']
    if data['prizes']:
        update_data['prizes'] = data['prizes']
    
    if update_data:
        print(f"Updating {data['url']} with {update_data}")
        try:
            supabase.table('posts').update(update_data).eq('url', data['url']).execute()
        except Exception as e:
            print(f"Failed to update {data['url']}: {e}")

print("Done patching.")
