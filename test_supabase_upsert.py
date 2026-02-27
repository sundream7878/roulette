import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

post_data = {
    "url": "test_sync_url_2",
    "title": "Should Sync",
    "prizes": "Prize 1\nPrize 2",
    "allow_duplicates": False,
    "updated_at": "2026-02-26T00:00:00.000000"
}

print("Upserting:", post_data)
try:
    res = supabase.table("posts").upsert(post_data).execute()
    print("Response data:", res.data)
except Exception as e:
    print(f"Exception: {e}")

