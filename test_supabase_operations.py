import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

try:
    print("Testing update without filter...")
    res = supabase.table("posts").update({"is_active": False}).execute()
    print("Success:", res)
except Exception as e:
    print("Error on update without filter:", e)

try:
    print("\nTesting update with neq filter...")
    res = supabase.table("posts").update({"is_active": False}).neq("url", "dummy").execute()
    print("Success:", res)
except Exception as e:
    print("Error on update with filter:", e)
