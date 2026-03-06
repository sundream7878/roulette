import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

def check_counts():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    supabase = create_client(url, key)
    
    res = supabase.table("posts").select("url, last_comment_id").execute()
    print("Posts:")
    for post in res.data:
        p_count = supabase.table("participants").select("count", count="exact").eq("url", post['url']).execute()
        c_count = supabase.table("commenters").select("count", count="exact").eq("url", post['url']).execute()
        print(f"URL: {post['url']}")
        print(f"  Last Comment ID: {post['last_comment_id']}")
        print(f"  Participants: {p_count.count}")
        print(f"  Commenters: {c_count.count}")

if __name__ == "__main__":
    check_counts()
