import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

res = supabase.table("posts").select("url, is_active").execute()
for r in res.data:
    print(r)
