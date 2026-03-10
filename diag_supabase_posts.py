import os
import json
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

def check_posts():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_ANON_KEY")
    if not url or not key:
        print("Missing Supabase credentials")
        return

    supabase: Client = create_client(url, key)
    
    # Get active URL first
    active_res = supabase.table("active_event").select("*").limit(1).execute()
    active_url = active_res.data[0].get("url") if active_res.data else None
    print(f"Active URL in Supabase: {active_url}")
    
    if active_url:
        # Check posts table for this URL
        post_res = supabase.table("posts").select("*").eq("url", active_url).execute()
        if post_res.data:
            post = post_res.data[0]
            print("\n--- Post Content in Supabase ---")
            print(f"URL: {post.get('url')}")
            print(f"Title: {post.get('title')}")
            print(f"Prizes: {post.get('prizes')}")
            print(f"Memo: {post.get('memo')}")
            print(f"Winners: {post.get('winners')}")
            print(f"Allow Duplicates: {post.get('allow_duplicates')}")
            print(f"Updated At: {post.get('updated_at')}")
        else:
            print(f"No entry found in 'posts' table for URL: {active_url}")

if __name__ == "__main__":
    check_posts()
