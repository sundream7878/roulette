import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")

if not url or not key:
    print("Error: SUPABASE_URL or SUPABASE_KEY missing")
    exit()

supabase: Client = create_client(url, key)

print("Fetching active posts from Supabase...")
res = supabase.table("posts").select("url, title, prizes, is_active, updated_at").order("updated_at", desc=True).limit(5).execute()
for row in res.data:
    print(row)
