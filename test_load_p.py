import sys, os
sys.path.insert(0, 'f:/roulette-1')
os.chdir('f:/roulette-1')

from comment_dart import load_participants, db

# 활성 URL 가져오기
url = db.get_active_url()
print(f"Testing load_participants for active URL: {url}")

try:
    p = load_participants()
    print(f"Success! Found {len(p)} participants.")
    if len(p) > 0:
        print(f"Sample: {p[0]}")
except Exception as e:
    import traceback
    print(f"Failed! Error: {e}")
    traceback.print_exc()
