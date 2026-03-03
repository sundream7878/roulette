"""
Supabase participants 저장 진단 스크립트
"""
import sys
sys.path.insert(0, 'f:/roulette-1')
import os
os.chdir('f:/roulette-1')

from standalone_comment_monitor.db_handler import CommentDatabase

db = CommentDatabase()

# 활성 URL 확인
active_url = db.get_active_url()
print(f"\n[1] 활성 URL: {active_url}")

if not active_url:
    print("ERROR: 활성 URL이 없습니다.")
    exit(1)

# allowed_list 확인
print("\n[2] Supabase posts.allowed_list 확인:")
if db.supabase:
    res = db.supabase.table('posts').select('url, allowed_list, is_active').eq('url', active_url).execute()
    if res.data:
        post = res.data[0]
        allowed_raw = post.get('allowed_list', '')
        print(f"  allowed_list (raw): {repr(allowed_raw[:200] if allowed_raw else 'EMPTY/NULL')}")
    else:
        print("  ERROR: posts 테이블에 해당 URL 없음")

# commenters 확인
print("\n[3] Supabase commenters 확인:")
if db.supabase:
    res = db.supabase.table('commenters').select('author').eq('url', active_url).execute()
    commenters = [r['author'] for r in res.data] if res.data else []
    print(f"  총 댓글 작성자: {len(commenters)}명")
    for c in commenters:
        print(f"    - {c}")

# participants 확인
print("\n[4] Supabase participants 확인:")
if db.supabase:
    res = db.supabase.table('participants').select('author, count').eq('url', active_url).execute()
    participants = res.data or []
    print(f"  총 확정 참여자: {len(participants)}명")
    for p in participants:
        print(f"    - {p['author']}: {p['count']}장")

# 매칭 분석
print("\n[5] commenters vs allowed_list 매칭 분석:")
if db.supabase and commenters and res.data:
    allowed_res = db.supabase.table('posts').select('allowed_list').eq('url', active_url).execute()
    if allowed_res.data:
        allowed_raw = allowed_res.data[0].get('allowed_list', '') or ''
        allowed_names = set()
        for line in allowed_raw.splitlines():
            line = line.strip()
            if not line: continue
            if ',' in line:
                name = line.split(',', 1)[0].strip()
            else:
                name = line
            allowed_names.add(name)
        print(f"  사전 참여 명단 인원: {len(allowed_names)}명")
        print(f"  매칭되는 댓글 작성자:")
        for c in commenters:
            if c in allowed_names:
                print(f"    ✅ {c} → 확정 참여자 대상")
            else:
                print(f"    ❌ {c} → 명단 없음")

print("\n[6] 수동 participants 저장 테스트:")
# commenters 중 allowed_list에 있는 사람을 participants에 직접 저장
if db.supabase and commenters and allowed_names:
    new_participants = {}
    for c in commenters:
        if c in allowed_names:
            new_participants[c] = 1
    if new_participants:
        print(f"  저장할 participants: {new_participants}")
        try:
            p_batch = [{"url": active_url, "author": a, "count": c} for a, c in new_participants.items()]
            result = db.supabase.table("participants").upsert(p_batch).execute()
            print(f"  저장 결과: {result.data}")
        except Exception as e:
            print(f"  저장 실패: {e}")
    else:
        print("  저장할 participants 없음 (댓글 작성자 중 명단에 있는 사람 없음)")
