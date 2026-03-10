import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

def check_posts():
    res = supabase.table("posts").select("url, title, is_active, updated_at").order("updated_at", desc=True).execute()
    print("--- Current Posts in Supabase ---")
    for row in res.data:
        status = "[ACTIVE]" if row.get("is_active") else "[inactive]"
        print(f"{status} {row['updated_at']} | {row['title']} | {row['url']}")

if __name__ == "__main__":
    check_posts()
