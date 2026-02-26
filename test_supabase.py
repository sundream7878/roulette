import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")

print(f"URL: {url}")
print(f"KEY: {key[:15]}...")

if not url or not key:
    print("Error: SUPABASE_URL or SUPABASE_KEY missing in .env")
    exit()

try:
    supabase: Client = create_client(url, key)
    print("Supabase client created.")
    
    # Test read
    print("Testing read from 'posts' table...")
    res = supabase.table("posts").select("*").limit(1).execute()
    print(f"Read success: {res.data}")
    
    # Test write
    print("Testing write to 'posts' table...")
    test_data = {"url": "test_url", "title": "Test Sync Connection"}
    res = supabase.table("posts").upsert(test_data).execute()
    print(f"Write success: {res.data}")
    
except Exception as e:
    print(f"\n[Error Details]\n{e}")
    if "PGRST116" in str(e) or "404" in str(e):
        print("\nPossible cause: Table 'posts' does not exist. Did you run the SQL script?")
    elif "401" in str(e) or "Invalid API key" in str(e) or "JWT" in str(e):
        print("\nPossible cause: Invalid API Key. Please use the 'service_role' key, not the 'anon' or 'publishable' key.")
    elif "403" in str(e) or "new row violates row-level security policy" in str(e):
        print("\nPossible cause: Row Level Security (RLS) is blocking the write. Please use the 'service_role' key to bypass RLS.")
