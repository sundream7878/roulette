import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(url, key)

target_url = "https://cafe.naver.com/ca-fe/web/cafes/27870803/articles/67482"

print(f"Checking Supabase for URL: {target_url}")
try:
    res = supabase.table("posts").select("*").eq("url", target_url).execute()

    if res.data:
        post = res.data[0]
        print("Post found:")
        for k, v in post.items():
            print(f"  {k}: {v}")
    else:
        print("Post not found in Supabase.")

    print("\nChecking all active posts:")
    res_active = supabase.table("posts").select("*").eq("is_active", True).execute()
    for p in res_active.data:
        print(f"  Active URL: {p['url']}, Title: {p.get('title')}")
except Exception as e:
    print(f"Error: {e}")
