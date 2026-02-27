import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

res = supabase.table('posts').select('*').order('updated_at', desc=True).limit(5).execute()
print("Top 5 recent posts in Supabase:")
for r in res.data:
    print(f"URL: {r['url']}, Title: {r['title']}, Prizes: {r['prizes']}, Active: {r['is_active']}")
