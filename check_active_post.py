import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

print("=== 모든 posts 목록 (최신순) ===")
res = supabase.table('posts').select('url, title, prizes, is_active, updated_at').order('updated_at', desc=True).execute()
for r in res.data:
    print(f"Active={r['is_active']} | Title={r['title']} | Prizes={repr(r['prizes'])} | URL={r['url'][:60]}...")
    print()
