import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

def check_structure():
    print("--- Checking Table Info ---")
    
    # We can't easily get full schema via standard API without RPC or Postgres direct,
    # but we can try to insert a duplicate and see the error message.
    
    test_url = "https://example.com/test_upsert"
    author = "TestUser"
    
    print(f"1. Testing upsert on 'participants' with on_conflict='url,author'...")
    try:
        data = {"url": test_url, "author": author, "count": 1}
        res = supabase.table("participants").upsert(data, on_conflict="url,author").execute()
        print("   First upsert Success:", res.data)
        
        data["count"] = 2
        res = supabase.table("participants").upsert(data, on_conflict="url,author").execute()
        print("   Second upsert (update) Success:", res.data)
        
    except Exception as e:
        print("   Upsert FAILED:", str(e))
        
        print("\n2. Trying upsert without on_conflict (letting Supabase handle it if PK exists)...")
        try:
            res = supabase.table("participants").upsert(data).execute()
            print("   Upsert (no explicit columns) Success:", res.data)
        except Exception as e2:
            print("   Upsert (no explicit columns) FAILED:", str(e2))

    print("\n3. Checking for specific column 'created_at' in participants...")
    try:
        res = supabase.table("participants").select("*").limit(1).execute()
        if res.data:
            print("   Columns found:", res.data[0].keys())
        else:
            print("   No data to check columns.")
    except Exception as e:
        print("   Select FAILED:", str(e))

if __name__ == "__main__":
    check_structure()
