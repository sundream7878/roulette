import os
import sqlite3
from supabase import create_client

# Credentials
url = "https://kbnszmnmvppfbdpdefqw.supabase.co"
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtibnN6bW5tdnBwZmJkcGRlZnF3Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MjA3NTYwOCwiZXhwIjoyMDg3NjUxNjA4fQ.64uvX8k3lUNAtdXpcenSWv2ofuUzDja9_VdJtabkKsw"
supabase = create_client(url, key)

target_url = "https://cafe.naver.com/ca-fe/web/cafes/27870803/articles/67661"

print(f"Force syncing active status for {target_url}...")

try:
    # 1. Clear all active
    supabase.table("posts").update({"is_active": False}).neq("url", "void").execute()
    
    # 2. Set target active
    res = supabase.table("posts").upsert({"url": target_url, "is_active": True}, on_conflict="url").execute()
    print("Supabase update successful.")
    
    # 3. Verify
    verify = supabase.table("posts").select("url, title, prizes, is_active").eq("is_active", True).execute()
    print("Currently active in Supabase:")
    print(verify.data)
except Exception as e:
    print(f"Error: {e}")
