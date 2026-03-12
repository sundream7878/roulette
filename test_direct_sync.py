import os
import sys
from dotenv import load_dotenv
from supabase import create_client, Client

# Add path for imports
sys.path.append(os.getcwd())

load_dotenv()

def test_supabase():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    
    print(f"Connecting to: {url}")
    print(f"Key length: {len(key) if key else 0}")
    
    if not url or not key:
        print("Error: Missing credentials")
        return

    try:
        supabase = create_client(url.strip("'\""), key.strip("'\""))
        
        # Test 1: Fetch from posts
        print("\nTest 1: Fetching all posts...")
        res = supabase.table("posts").select("*").execute()
        print(f"Total posts in Supabase: {len(res.data)}")
        for post in res.data:
            print(f"- {post['url']} (Title: {post.get('title')}, Active: {post.get('is_active')})")

        # Test 1.1: Fetch 67661 specifically
        print("\nTest 1.1: Fetching 67661 specifically...")
        res_67661 = supabase.table("posts").select("*").ilike("url", "%67661%").execute()
        if res_67661.data:
            p = res_67661.data[0]
            print(f"Found 67661: {p['url']}")
            print(f"Title: {p.get('title')}")
            print(f"Participants count in local db check? (Need to check participants table)")
            
            p_count = supabase.table("participants").select("count", count="exact").eq("url", p['url']).execute()
            print(f"Participants in Supabase for 67661: {p_count.count}")
        else:
            print("Event 67661 NOT found in Supabase.")

        # Test 2: Try a dummy upsert
        dummy_url = "https://cafe.naver.com/test_sync_check"
        print(f"\nTest 2: Upserting dummy post to {dummy_url}...")
        upsert_res = supabase.table("posts").upsert({
            "url": dummy_url,
            "title": "Sync Test",
            "prizes": "Prize 1, Prize 2",
            "memo": "This is a test",
            "is_active": False,
            "updated_at": "2026-03-10T14:56:00"
        }, on_conflict="url").execute()
        print("Upsert successful!")

        # Test 3: Try upserting a participant
        print("\nTest 3: Upserting dummy participant...")
        p_res = supabase.table("participants").upsert({
            "url": dummy_url,
            "author": "tester123",
            "count": 1
        }, on_conflict="url,author").execute()
        print("Participant upsert successful!")

        # Cleanup
        # print("\nCleaning up...")
        # supabase.table("participants").delete().eq("url", dummy_url).execute()
        # supabase.table("posts").delete().eq("url", dummy_url).execute()
        # print("Cleanup successful.")

    except Exception as e:
        print(f"\nFAILED: {e}")

if __name__ == "__main__":
    test_supabase()
