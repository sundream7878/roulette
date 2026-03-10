import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

# From previous check_active_post.py output
REAL_URL = "https://cafe.naver.com/ca-fe/web/cafes/27870803/articles/64865"

def check_real_upsert():
    print(f"--- Testing Upsert with Real URL: {REAL_URL} ---")
    
    # 1. Test Participants with created_at
    print("1. Testing 'participants' upsert WITH 'created_at'...")
    try:
        data = {"url": REAL_URL, "author": "TesterSync", "count": 1, "created_at": "2024-01-01T00:00:00"}
        res = supabase.table("participants").upsert(data, on_conflict="url,author").execute()
        print("   Success!", res.data)
    except Exception as e:
        print("   FAILED (Expectedly if column missing):", str(e))

    # 2. Test Participants WITHOUT created_at
    print("\n2. Testing 'participants' upsert WITHOUT 'created_at'...")
    try:
        data = {"url": REAL_URL, "author": "TesterSync", "count": 2} # Changed count to see update
        res = supabase.table("participants").upsert(data, on_conflict="url,author").execute()
        print("   Success!", res.data)
    except Exception as e:
        print("   FAILED:", str(e))

    # 3. Test Commenters WITHOUT created_at
    print("\n3. Testing 'commenters' upsert WITHOUT 'created_at'...")
    try:
        data = {"url": REAL_URL, "author": "TesterSync"}
        res = supabase.table("commenters").upsert(data, on_conflict="url,author").execute()
        print("   Success!", res.data)
    except Exception as e:
        print("   FAILED:", str(e))

if __name__ == "__main__":
    check_real_upsert()
