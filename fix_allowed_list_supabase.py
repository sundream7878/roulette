"""
Supabase posts 테이블에 allowed_list 저장 및 participants 재동기화 스크립트
"""
import sys, os
sys.path.insert(0, 'f:/roulette-1')
os.chdir('f:/roulette-1')

from standalone_comment_monitor.db_handler import CommentDatabase

db = CommentDatabase()

if not db.supabase:
    print("ERROR: Supabase not connected")
    exit(1)

# 1. 활성 URL 확인
active_url = db.get_active_url()
print(f"[1] 활성 URL: {active_url}")

if not active_url:
    # 가장 최근 URL 자동 선택
    res = db.supabase.table('posts').select('url').order('updated_at', desc=True).limit(1).execute()
    if res.data:
        active_url = res.data[0]['url']
        print(f"    → 자동 선택: {active_url}")
        db.supabase.table('posts').update({'is_active': True}).eq('url', active_url).execute()

# 2. 로컬 allowed_list.txt 읽기
ALLOWED_LIST_FILE = 'f:/roulette-1/allowed_list.txt'
allowed_raw_lines = []
if os.path.exists(ALLOWED_LIST_FILE):
    with open(ALLOWED_LIST_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                allowed_raw_lines.append(line)
    allowed_content = '\n'.join(allowed_raw_lines)
    print(f"[2] allowed_list.txt: {len(allowed_raw_lines)}명 로드")
else:
    print("[2] ERROR: allowed_list.txt 없음")
    allowed_content = None

# 3. Supabase posts에 allowed_list 저장 시도
if allowed_content and active_url:
    try:
        result = db.supabase.table('posts').update({'allowed_list': allowed_content}).eq('url', active_url).execute()
        print(f"[3] Supabase posts.allowed_list 저장 완료")
    except Exception as e:
        print(f"[3] posts 저장 실패: {e}")
        print("    → Supabase SQL Editor에서 먼저 실행하세요:")
        print("    ALTER TABLE posts ADD COLUMN IF NOT EXISTS allowed_list TEXT;")
        exit(1)

# 4. allowed_list 파싱
allowed_dict = {}
for line in allowed_raw_lines:
    if ',' in line:
        parts = line.split(',', 1)
        name = parts[0].strip()
        try:
            tickets = int(parts[1].strip())
        except:
            tickets = 1
        allowed_dict[name] = tickets
    else:
        allowed_dict[line] = 1

print(f"[4] 사전 참여 명단 파싱: {len(allowed_dict)}명")

# 5. 현재 commenters 조회
if active_url:
    res = db.supabase.table('commenters').select('author').eq('url', active_url).execute()
    commenters = [r['author'] for r in (res.data or [])]
    print(f"[5] 현재 댓글 작성자: {len(commenters)}명")

    # 6. 매칭된 participants 계산
    new_participants = {}
    for commenter in commenters:
        if commenter in allowed_dict:
            new_participants[commenter] = allowed_dict[commenter]
            print(f"    ✅ 확정: {commenter} ({allowed_dict[commenter]}장)")
        else:
            print(f"    ❌ 미매칭: {commenter}")

    # 7. participants 테이블에 저장
    if new_participants:
        p_batch = [{"url": active_url, "author": a, "count": c} for a, c in new_participants.items()]
        try:
            db.supabase.table("participants").upsert(p_batch).execute()
            print(f"\n[7] Supabase participants 저장 완료: {len(new_participants)}명")
        except Exception as e:
            print(f"[7] participants 저장 실패: {e}")
    else:
        print(f"\n[7] 매칭된 참여자 없음 (댓글 작성자가 명단에 없음)")

print("\nDone!")
