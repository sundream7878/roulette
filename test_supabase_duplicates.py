import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

post_data = {
    "url": "test_duplicate_check",
    "allow_duplicates": True
}

print(f"Attempting to upsert allow_duplicates to Supabase: {post_data}")
try:
    res = supabase.table("posts").upsert(post_data).execute()
    print("Success! Response data:", res.data)
except Exception as e:
    print(f"Failed! Error: {e}")
