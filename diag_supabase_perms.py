import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

if not url or not key:
    print("Error: SUPABASE_URL or SUPABASE_KEY not found in .env")
    exit(1)

supabase: Client = create_client(url, key)

test_url = "https://blog.naver.com/test/123"

def test_sync():
    print(f"--- Testing Supabase Sync for {test_url} ---")
    
    try:
        # 1. Test Posts
        print("1. Testing 'posts' upsert...")
        res = supabase.table("posts").upsert({
            "url": test_url,
            "title": "Diagnostic Test",
            "is_active": True
        }, on_conflict="url").execute()
        print("   Success:", res.data)

        # 2. Test Participants
        print("2. Testing 'participants' insert...")
        # Clear first
        supabase.table("participants").delete().eq("url", test_url).execute()
        res = supabase.table("participants").insert([
            {"url": test_url, "author": "Tester1", "count": 1},
            {"url": test_url, "author": "Tester2", "count": 2}
        ]).execute()
        print("   Success:", res.data)

        # 3. Test Commenters
        print("3. Testing 'commenters' insert...")
        # Clear first
        supabase.table("commenters").delete().eq("url", test_url).execute()
        res = supabase.table("commenters").insert([
            {"url": test_url, "author": "Tester1"},
            {"url": test_url, "author": "Tester3"}
        ]).execute()
        print("   Success:", res.data)

        print("\n--- All tests completed successfully! ---")
        print("Please check your Supabase dashboard to see if these 3 tables have data for the test URL.")

    except Exception as e:
        print("\n--- Test FAILED! ---")
        print("Error details:", str(e))

if __name__ == "__main__":
    test_sync()
