"""
Supabase posts 정리 스크립트:
1. 테스트 데이터(test_*) 삭제
2. 올바른 활성 URL 설정
"""
import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# 1. 테스트 URL 삭제
TEST_URLS = ['test_sync_url', 'test_sync_url_2', 'test_sync_url_3', 'test_encoding_url', 'test_sync_url_4']
for url in TEST_URLS:
    supabase.table('posts').delete().eq('url', url).execute()
    supabase.table('participants').delete().eq('url', url).execute()
    supabase.table('commenters').delete().eq('url', url).execute()
    print(f"테스트 데이터 삭제: {url}")

# 2. 현재 어떤 posts가 있는지 확인
print("\n=== 남은 posts ===")
res = supabase.table('posts').select('url, title, prizes, is_active, updated_at').order('updated_at', desc=True).execute()
for i, r in enumerate(res.data):
    print(f"[{i}] Active={r['is_active']} | {r['updated_at'][:10]} | title={r['title']} | url={r['url'][:70]}")
