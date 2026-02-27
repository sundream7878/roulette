import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

print("=== Raw Supabase posts 전체 조회 ===")
res = supabase.table('posts').select('*').execute()
print(f"총 posts 수: {len(res.data)}")
for r in res.data:
    print(r)
    print()
