import os
from supabase import create_client

url = "https://kbnszmnmvppfbdpdefqw.supabase.co"
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtibnN6bW5tdnBwZmJkcGRlZnF3Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MjA3NTYwOCwiZXhwIjoyMDg3NjUxNjA4fQ.64uvX8k3lUNAtdXpcenSWv2ofuUzDja9_VdJtabkKsw"
supabase = create_client(url, key)

print("Fetching active URL from posts table...")
res = supabase.table("posts").select("url, title, prizes, memo, winners, allow_duplicates").eq("is_active", True).limit(1).execute()

if res.data:
    print("Active Event Found:")
    print(res.data[0])
else:
    print("No active event found in Supabase 'posts' table.")
