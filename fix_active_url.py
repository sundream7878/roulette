"""
Fix script:
1. posts 테이블 allowed_list 컬럼 추가 확인 및 active URL 수정
"""
import sys, os
sys.path.insert(0, 'f:/roulette-1')
os.chdir('f:/roulette-1')

from standalone_comment_monitor.db_handler import CommentDatabase

db = CommentDatabase()

if not db.supabase:
    print("ERROR: Supabase not connected")
    exit(1)

print("\n=== Supabase posts 테이블 전체 레코드 확인 ===")
res = db.supabase.table('posts').select('*').execute()
posts = res.data or []
print(f"총 {len(posts)}개 레코드")
for p in posts:
    print(f"  - url: {p.get('url', '')[:80]}")
    print(f"    is_active: {p.get('is_active')}, updated_at: {p.get('updated_at', '')[:19]}")
    print(f"    has allowed_list key: {'allowed_list' in p}, value: {repr(str(p.get('allowed_list',''))[:50])}")
    print()

print("\n=== commenters 테이블 확인 ===")
res2 = db.supabase.table('commenters').select('url, author').execute()
if res2.data:
    from collections import Counter
    url_counts = Counter(r['url'] for r in res2.data)
    for url, cnt in url_counts.most_common(5):
        print(f"  {cnt}명: {url[:70]}")

print("\n=== participants 테이블 확인 ===")
res3 = db.supabase.table('participants').select('url, author, count').execute()
if res3.data:
    from collections import Counter
    url_counts = Counter(r['url'] for r in res3.data)
    for url, cnt in url_counts.most_common(5):
        print(f"  {cnt}명: {url[:70]}")
else:
    print("  (비어있음)")

print("\n=== 잘못된 test_encoding_url active 해제 ===")
try:
    db.supabase.table('posts').update({'is_active': False}).eq('url', 'test_encoding_url').execute()
    print("  test_encoding_url active 해제 완료")
except Exception as e:
    print(f"  오류: {e}")

print("\n=== 실제 이벤트 URL active 설정 ===")
# commenters가 가장 많은 URL을 활성으로 설정
if res2.data:
    from collections import Counter
    url_counts = Counter(r['url'] for r in res2.data)
    if url_counts:
        best_url, count = url_counts.most_common(1)[0]
        print(f"  가장 많은 댓글의 URL ({count}명): {best_url}")
        db.supabase.table('posts').update({'is_active': True}).eq('url', best_url).execute()
        print(f"  is_active=True 설정 완료")
