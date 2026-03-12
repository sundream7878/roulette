import os
import time
from flask import Blueprint, render_template, request, jsonify
from standalone_comment_monitor.scraper import NaverCommentMonitor
from standalone_comment_monitor.db_handler import CommentDatabase
from datetime import datetime
try:
    from standalone_comment_monitor.selenium_scraper import SeleniumCommentScraper
except ImportError:
    SeleniumCommentScraper = None

monitor_bp = Blueprint('monitor', __name__)

# 파일 경로
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARTICIPANTS_FILE = os.path.join(BASE_DIR, 'participants.txt')
LAST_COMMENT_FILE = os.path.join(BASE_DIR, 'last_comment_id.txt')
ALLOWED_LIST_FILE = os.path.join(BASE_DIR, 'allowed_list.txt')
ACTIVE_URL_FILE = os.path.join(BASE_DIR, 'active_event.txt')

def set_active_url(url):
    """현재 관리 중인 URL을 활성 상태로 설정합니다. (중복 호출 방지)"""
    if not url:
        try:
            db.set_active_url(None)
            print("DEBUG: Active URL cleared")
        except Exception as e:
            print(f"ERROR: Failed to clear active URL: {e}")
        return

    # 정규화하여 저장
    from standalone_comment_monitor.parsers import parse_post_ids_from_url
    clubid, articleid = parse_post_ids_from_url(url)
    if clubid and articleid:
        url = f"https://cafe.naver.com/ca-fe/web/cafes/{clubid}/articles/{articleid}"
    
    try:
        # 현재 활성 URL과 동일하면 스킵 (Supabase Realtime 무한 루프 방지)
        current_active = db.get_active_url()
        if current_active == url:
            return

        # DB에 활성 상태 저장 (Supabase)
        db.set_active_url(url)
        print(f"DEBUG: Active URL set to: {url}")
    except Exception as e:
        print(f"ERROR: Failed to set active URL: {e}")

def normalize_url(url):
    """네이버 카페 URL을 표준 형식으로 변환"""
    if not url: return url
    url = url.strip() # 공백 및 개행 제거
    from standalone_comment_monitor.parsers import parse_post_ids_from_url
    clubid, articleid = parse_post_ids_from_url(url)
    if clubid and articleid:
        return f"https://cafe.naver.com/ca-fe/web/cafes/{clubid}/articles/{articleid}"
    return url.strip()

def get_allowed_list(url=None):
    """명단을 {이름: 티켓수} 사전 형식으로 파싱합니다."""
    # 1. URL이 있으면 DB(Supabase)에서 가져오기 우선
    if url:
        try:
            _, _, _, _, _, _, _, _, allowed_list_content = db.get_data(url)
            if allowed_list_content:
                allowed = {}
                for line in allowed_list_content.splitlines():
                    line = line.strip()
                    if not line: continue
                    if ',' in line:
                        parts = line.split(',', 1)
                        name = parts[0].strip()
                        try:
                            tickets = int(parts[1].strip())
                        except:
                            tickets = 1
                        allowed[name] = tickets
                    else:
                        allowed[line] = 1
                return allowed
        except Exception as e:
            print(f"DEBUG: Error getting allowed list from DB for {url}: {e}")

    # 2. URL이 없거나 DB에 없으면 기존 파일 fallback (로컬 관리용)
    if not os.path.exists(ALLOWED_LIST_FILE):
        return {}
    allowed = {}
    try:
        with open(ALLOWED_LIST_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line: continue
                if ',' in line:
                    parts = line.split(',', 1)
                    name = parts[0].strip()
                    try:
                        tickets = int(parts[1].strip())
                    except:
                        tickets = 1
                    allowed[name] = tickets
                else:
                    allowed[line] = 1
        return allowed
    except:
        return {}

# DB 초기화
db = CommentDatabase()

# 이벤트별 메모리 상태 저장소 (Event Isolation)
# 구조: { event_id: { 'participants': {name: count}, 'last_id': str, 'url': str, 'seen_ids': set() } }
event_states = {}

# 백그라운드 모니터링 관리용
active_monitoring_urls = {} # { url: boolean }
monitoring_lock = False # 간단한 락 대용

# ─── [실시간 Supabase 변경 감지 - 2초 빠른 폴링] ──────────────────────────────
_last_supabase_state = {
    'updated_at': None,
    'participant_count': -1,   # commenters 테이블 수
    'confirmed_count': -1,     # participants 테이블 수 (확정 명단)
    'title': None,
    'prizes': None,
    'memo': None,
    'winners': None,
    'allowed_list': None,
    'active_url': None,
}
_supabase_polling_started = False
_auto_monitoring_started = False

def _safe_supabase_call(func, max_retries=3):
    """Supabase 호출 안정성 확보 (Resource temporarily unavailable 대응)"""
    import time as _time
    import random as _random
    base_delay = 1.0
    for i in range(max_retries):
        try:
            return func()
        except Exception as e:
            error_str = str(e)
            if "[Errno 11]" in error_str and i < max_retries - 1:
                delay = base_delay * (2 ** i) + _random.uniform(0, 1)
                print(f"DEBUG: [Supabase SafeCall] Resource busy, retrying in {delay:.2f}s... ({i+1}/{max_retries})")
                _time.sleep(delay)
                continue
            raise e

def _auto_start_monitoring():
    """서버 시작 시 활성화된 URL이 있으면 자동으로 백그라운드 모니터링 시작"""
    global _auto_monitoring_started
    if _auto_monitoring_started:
        return
    _auto_monitoring_started = True

    import threading
    def _auto_start_thread():
        import time as _time
        _time.sleep(5)  # 서버 완전 초기화 대기
        try:
            # 1. 활성 URL 확인 (Supabase에서만 확인)
            active_url = db.get_active_url()

            if not active_url:
                print("DEBUG: [AutoStart] No active URL found, skipping auto-monitoring")
                return

            print(f"DEBUG: [AutoStart] Found active URL: {active_url}")

            # 2. event_states 초기화 (DB에서 데이터 복원)
            # URL을 정규화하여 키 일관성 확보
            active_url = normalize_url(active_url)
            
            # 이미 상태가 있으면(프론트엔드 요청 등) 덮어쓰지 않음
            if active_url in event_states:
                print(f"DEBUG: [AutoStart] State for {active_url} already exists, skipping initialization")
                start_background_monitoring(active_url)
                return

            try:
                existing_participants, last_comment_id, all_c_list, title, prizes, memo, winners, allow_duplicates, _ = db.get_data(active_url)
            except Exception:
                existing_participants, all_c_list, last_comment_id = {}, [], None
                title, prizes, memo, winners, allow_duplicates = None, None, None, None, True

            event_states[active_url] = {
                'participants': existing_participants,
                'last_id': last_comment_id,
                'url': active_url,
                'seen_ids': set(),
                'all_commenters': list(all_c_list) if all_c_list else [], # list of {name, created_at}
                'title': title,
                'prizes': prizes,
                'memo': memo,
                'winners': winners,
                'allow_duplicates': allow_duplicates,
            }
            print(f"DEBUG: [AutoStart] event_states initialized for {active_url}")

            # 3. 백그라운드 모니터링 시작
            start_background_monitoring(active_url)
            print(f"DEBUG: [AutoStart] Background monitoring started for {active_url}")

        except Exception as e:
            print(f"DEBUG: [AutoStart] Error: {e}")

    t = threading.Thread(target=_auto_start_thread, daemon=True)
    t.start()


def _start_supabase_polling():
    """Supabase 변경 감지 스레드 시작 (최초 1회)"""
    global _supabase_polling_started
    if _supabase_polling_started:
        return
    if not db.supabase:
        print("DEBUG: [Realtime] Supabase not connected, skipping polling")
        return
    _supabase_polling_started = True
    import threading
    t = threading.Thread(target=_supabase_poll_loop, daemon=True)
    t.start()
    print("DEBUG: [Realtime] Supabase fast-polling started (2s interval)")

def _broadcast_current_state():
    """현재 Supabase 상태를 즉시 모든 클라이언트에게 브로드캐스트"""
    try:
        from comment_dart import socketio
        if not db.supabase:
            return
            
        def fetch_post():
            return db.supabase.table('posts').select('url, title, prizes, memo, winners, allowed_list, updated_at').eq('is_active', True).limit(1).execute()
        post_res = _safe_supabase_call(fetch_post)
        
        if not post_res.data:
            return
        post = post_res.data[0]
        url = post['url']
        title = post.get('title')
        prizes = post.get('prizes')
        memo = post.get('memo')
        winners = post.get('winners')
        allowed_list_str = post.get('allowed_list')
        updated_at = post.get('updated_at')

        # [추가] 브로드캐스트 전 로컬 DB 동기화 (Render stale 데이터 방지)
        post['is_active'] = True
        db.sync_post_data_local(url, post)

        socketio.emit('update_event_settings', {
            'url': url, 'title': title, 'prizes': prizes, 'memo': memo, 'winners': winners, 'allowed_list': allowed_list_str
        })

        # 참가자 및 전체 댓글 데이터 브로드케스트
        def fetch_participants():
            return db.supabase.table('participants').select('author, count, created_at').eq('url', url).execute()
        p_res = _safe_supabase_call(fetch_participants)
        participants = p_res.data or []
        
        # 전체 댓글 작성자 목록 가져오기
        def fetch_commenters():
            return db.supabase.table('commenters').select('author, created_at').eq('url', url).execute()
        c_res = _safe_supabase_call(fetch_commenters)
        all_commenters_list = [{'name': r['author'], 'created_at': r.get('created_at')} for r in c_res.data] if c_res.data else []
        
        allowed_list = get_allowed_list(url)
        full_commenters_data = []
        for name_data in all_commenters_list:
            full_commenters_data.append({
                'name': name_data['name'] if isinstance(name_data, dict) else name_data,
                'is_whitelisted': (name_data['name'] if isinstance(name_data, dict) else name_data) in allowed_list,
                'tickets': allowed_list.get(name_data['name'] if isinstance(name_data, dict) else name_data, 0),
                'created_at': name_data.get('created_at') if isinstance(name_data, dict) else None
            })

        p_list = []
        p_data_for_sync = []
        for r in participants:
            a = r['author']
            v = r['count']
            created_at = r.get('created_at')
            p_list.append((a, v, created_at))
            p_data_for_sync.append({'author': a, 'count': v, 'created_at': created_at})
            
        # [추가] 브로드캐스트 전 로컬 DB 동기화 (Render stale 데이터 방지)
        db.sync_participants_local(url, p_data_for_sync)
        db.sync_commenters_local(url, all_commenters_list)
        
        # [중요] 화살표 불일치 방지: 항상 가나다순 정렬
        p_list.sort(key=lambda x: x[0])
            
        # 모든 확정자 (현재 참여자 + 기당첨자)
        won_names = [w.strip() for w in winners.split(',') if w.strip()] if winners else []
        confirmed_all = list(set([p[0] for p in p_list]) | set(won_names))

        socketio.emit('update_participants', {
            'participants': p_list,
            'confirmed_all': confirmed_all,
            'full_commenter_list': full_commenters_data,
            'total_comments': len(all_commenters_list),
            'event_id': 'realtime'
        })

        # 상태 갱신
        _last_supabase_state.update({
            'updated_at': updated_at, 'title': title, 'prizes': prizes,
            'participant_count': len(all_commenters_list), 'active_url': url
        })
    except Exception as e:
        print(f"DEBUG: [Realtime Broadcast Error] {e}")

def _supabase_poll_loop():
    """2초마다 Supabase를 확인하고 변경이 있으면 즉시 브로드캐스트"""
    import time as _time
    global _last_supabase_state
    _time.sleep(3)  # 서버 초기화 대기

    # ── 첫 번째 루프: 현재 DB 상태를 조용히 읽어서 기준값으로 설정 ──
    try:
        if db.supabase:
            def fetch_initial_post():
                return db.supabase.table('posts').select('url, title, prizes, memo, winners, allowed_list, updated_at').eq('is_active', True).limit(1).execute()
            post_res = _safe_supabase_call(fetch_initial_post)
            
            if post_res.data:
                post = post_res.data[0]
                url = post['url']
                # 전체 작성자 수를 기준으로 변경 감지
                def fetch_commenters_count():
                    return db.supabase.table('commenters').select('author', count='exact').eq('url', url).execute()
                c_res = _safe_supabase_call(fetch_commenters_count)
                total_count = c_res.count if hasattr(c_res, 'count') else (len(c_res.data) if c_res.data else 0)
                # 확정 참가자 수도 초기값으로
                def fetch_participants_count():
                    return db.supabase.table('participants').select('author', count='exact').eq('url', url).execute()
                p_res = _safe_supabase_call(fetch_participants_count)
                confirmed_count = p_res.count if hasattr(p_res, 'count') else (len(p_res.data) if p_res.data else 0)
                
                _last_supabase_state.update({
                    'updated_at': post.get('updated_at'),
                    'title': post.get('title'),
                    'prizes': post.get('prizes'),
                    'memo': post.get('memo'),
                    'winners': post.get('winners'),
                    'allowed_list': post.get('allowed_list'),
                    'active_url': url,
                    'participant_count': total_count,
                    'confirmed_count': confirmed_count,
                })
                print(f"DEBUG: [Realtime] Initial state: {total_count} commenters, {confirmed_count} confirmed, title={post.get('title')}")
                
                # [추가] 초기 상태 즉시 브로드캐스트 (새로 접속한 클라이언트 대응)
                _broadcast_current_state()
    except Exception as e:
        print(f"DEBUG: [Realtime] Init error: {e}")

    while True:
        try:
            from comment_dart import socketio
            if not db.supabase:
                _time.sleep(5)
                continue

            # 활성 포스트 조회
            def fetch_poll_post():
                return db.supabase.table('posts').select('url, title, prizes, memo, winners, allowed_list, updated_at').eq('is_active', True).limit(1).execute()
            post_res = _safe_supabase_call(fetch_poll_post)
            
            if not post_res.data:
                _time.sleep(2)
                continue

            post = post_res.data[0]
            url = post['url']
            if not url:
                _time.sleep(2)
                continue
                
            updated_at = post.get('updated_at')
            title = post.get('title')
            prizes = post.get('prizes')
            memo = post.get('memo')
            winners = post.get('winners')
            allowed_list_str = post.get('allowed_list')

            # 1. 설정 변경 체크
            settings_changed = (
                updated_at != _last_supabase_state['updated_at'] or
                title != _last_supabase_state['title'] or
                prizes != _last_supabase_state['prizes'] or
                memo != _last_supabase_state.get('memo') or
                winners != _last_supabase_state.get('winners') or
                allowed_list_str != _last_supabase_state.get('allowed_list') or
                url != _last_supabase_state['active_url']
            )

            if settings_changed:
                print(f"DEBUG: [Realtime] Settings changed! Broadcasting...")
                
                if url != _last_supabase_state['active_url']:
                    print(f"DEBUG: [Realtime] Active URL changed to {url}. Syncing local state...")
                    # [수정] 단순 URL 변경 대신 전체 데이터 동기화
                    post['is_active'] = True
                    db.sync_post_data_local(url, post)
                else:
                    # 동일 URL이지만 설정이 바뀐 경우
                    print(f"DEBUG: [Realtime] Settings updated for {url}. Syncing local state...")
                    post['is_active'] = True
                    db.sync_post_data_local(url, post)

                socketio.emit('update_event_settings', {
                    'url': url, 'title': title, 'prizes': prizes, 'memo': memo, 'winners': winners, 'allowed_list': allowed_list_str
                })
                _last_supabase_state.update({
                    'title': title, 'prizes': prizes, 'memo': memo, 'winners': winners, 'allowed_list': allowed_list_str,
                    'active_url': url, 'updated_at': updated_at
                })

            # 2. commenters 수 변경 체크
            def fetch_poll_commenters():
                return db.supabase.table('commenters').select('author, created_at').eq('url', url).execute()
            c_res = _safe_supabase_call(fetch_poll_commenters)
            all_commenters_list = [{'name': r['author'], 'created_at': r.get('created_at')} for r in c_res.data] if c_res.data else []
            current_total_count = len(all_commenters_list)

            # 3. 확정 참가자(participants) 수 변경 체크 - 이벤트 명단 변동 시에도 감지
            def fetch_poll_participants():
                return db.supabase.table('participants').select('author, count, created_at').eq('url', url).execute()
            p_res = _safe_supabase_call(fetch_poll_participants)
            participants = p_res.data or []
            current_confirmed_count = len(participants)

            # 변경 감지: 댓글 수 OR 확정 참가자 수 OR 설정 변경 시 emit
            commenters_changed = current_total_count != _last_supabase_state['participant_count']
            confirmed_changed = current_confirmed_count != _last_supabase_state['confirmed_count']

            # [추가] 변경 감지 시 로컬 DB 동기화 (Render stale 데이터 방지)
            if commenters_changed:
                db.sync_commenters_local(url, all_commenters_list)
            if confirmed_changed:
                db.sync_participants_local(url, participants)

            if commenters_changed or confirmed_changed or settings_changed:
                change_reason = []
                if commenters_changed: change_reason.append(f"commenters {_last_supabase_state['participant_count']}→{current_total_count}")
                if confirmed_changed: change_reason.append(f"confirmed {_last_supabase_state['confirmed_count']}→{current_confirmed_count}")
                if settings_changed: change_reason.append("settings")
                print(f"DEBUG: [Realtime] Change detected ({', '.join(change_reason)}) → broadcasting")
                
                allowed_list = get_allowed_list(url)
                full_commenters_data = []
                for item in all_commenters_list:
                    name = item['name'] if isinstance(item, dict) else item
                    full_commenters_data.append({
                        'name': name,
                        'is_whitelisted': name in allowed_list,
                        'tickets': allowed_list.get(name, 0),
                        'created_at': item.get('created_at') if isinstance(item, dict) else None
                    })

                p_list = []
                for r in participants:
                    a = r['author']
                    v = r['count']
                    created_at = r.get('created_at')
                    p_list.append((a, v, created_at))
                
                # [중요] 항상 가나다순 정렬하여 화살표 동기화
                p_list.sort(key=lambda x: str(x[0]))
                
                # [추가] 전체 확정자 명단 (참여자 + 기당첨자) 계산하여 UI 상태 보존
                won_names = [w.strip() for w in winners.split(',') if w.strip()] if winners else []
                confirmed_all = list(set(r['author'] for r in participants) | set(won_names))

                socketio.emit('update_participants', {
                    'participants': p_list,
                    'confirmed_all': confirmed_all,
                    'full_commenter_list': full_commenters_data,
                    'total_comments': current_total_count,
                    'event_id': 'realtime'
                })
                _last_supabase_state['participant_count'] = current_total_count
                _last_supabase_state['confirmed_count'] = current_confirmed_count

        except Exception as e:
            error_str = str(e)
            if "[Errno 11]" in error_str:
                print(f"DEBUG: [Realtime Poll] Resource busy ([Errno 11]). Slowing down... {e}")
                _time.sleep(5) # 오류 발생 시 더 길게 대기
            else:
                print(f"DEBUG: [Realtime Poll Error] {e}")
                _time.sleep(2)
        else:
            _time.sleep(2) # 정상 작동 시 기본 2초 대기

# ─────────────────────────────────────────────────────────────────────────────


def sync_participants_with_whitelist(url, existing_participants, all_commenters):
    """
    이미 수집된 '모든 작성자' 중에서 '사전 명단(화이트리스트)'에 있는 사람을 
    참여자 명단으로 동적으로 업데이트합니다.
    """
    allowed_list = get_allowed_list(url)
    updated = False
    
    for item in all_commenters:
        name = item['name'] if isinstance(item, dict) else item
        if name in allowed_list and name not in existing_participants:
            existing_participants[name] = (allowed_list[name], item.get('created_at') if isinstance(item, dict) else None)
            updated = True
            print(f"DEBUG: [Sync] Promoted '{name}' to participant (found in whitelist)")
            
    if updated:
        # [수정] 백그라운드나 모니터링 중 중복 저장을 피해 성능 개선
        print(f"DEBUG: [Sync] Whitelist sync updated participants, will be saved in main loop")
        
    return existing_participants, updated


@monitor_bp.route('/monitor_page')
def monitor_page():
    try:
        current_url = db.get_active_url() or ''
    except:
        current_url = ''
    return render_template('monitor.html', current_url=current_url)

@monitor_bp.route('/api/update_event_settings', methods=['POST'])
def update_event_settings():
    data = request.json
    url = normalize_url(data.get('url', ''))
    title = data.get('title')
    prizes = data.get('prizes')
    memo = data.get('memo')
    allow_duplicates = data.get('allow_duplicates')
    
    if not url:
        return jsonify({'error': 'URL이 필요합니다.'}), 400
        
    try:
        # DB 저장 (입력된 값만 업데이트됨)
        # 덮어쓰기 방지를 위해 기존 상태에서 last_id와 winners를 가져옴
        current_last_id = ''
        current_winners = None
        current_allowed_list = None
        
        if url in event_states:
            current_last_id = event_states[url].get('last_id', '')
            current_winners = event_states[url].get('winners')
            current_allowed_list = event_states[url].get('allowed_list_str')
        else:
            # [수정] 메모리에 상태가 없는 경우 DB에서 직접 조회하여 데이터 유실 방지
            try:
                # get_data returns: participants, last_id, all_commenters, title, prizes, memo, winners, allow_duplicates, allowed_list_str
                _, last_id, _, _, _, _, winners, _, allowed_list = db.get_data(url)
                current_last_id = last_id or ''
                current_winners = winners
                current_allowed_list = allowed_list
                print(f"DEBUG: [Settings] Hydrated state from DB for {url} (winners: {len(winners) if winners else 0} chars)")
            except Exception as e:
                print(f"DEBUG: [Settings] Failed to fetch existing data from DB: {e}")

        # [수정] 실제 변경 여부 확인하여 무분별한 새로고침 차단
        is_changed = False
        if url in event_states:
            state = event_states[url]
            if title is not None and title != state.get('title'): is_changed = True
            if prizes is not None and prizes != state.get('prizes'): is_changed = True
            if memo is not None and memo != state.get('memo'): is_changed = True
            if allow_duplicates is not None and (allow_duplicates == True) != state.get('allow_duplicates'): is_changed = True
        else:
            is_changed = True # 상태가 없으면 첫 설정이므로 저장

        if is_changed:
            db.save_data(url, None, current_last_id, title=title, prizes=prizes, memo=memo, 
                         winners=current_winners, allow_duplicates=allow_duplicates, allowed_list=current_allowed_list)
            # db.save_data 내부에서 업데이트를 수행하므로 별도의 db.update_timestamp(url) 호출은 필요 없음
            # (save_data -> _save_to_local -> datetime.now()로 정해짐)
            print(f"DEBUG: [Settings] Changes detected for {url}, database updated.")
        else:
            print(f"DEBUG: [Settings] No changes detected for {url}, skipping database update.")
        
        # [추가] 설정 저장 시 해당 이벤트를 활성화 (룰렛 화면에 즉시 반영도록)
        set_active_url(url)
        
        # 메모리 상태 업데이트 (URL을 키로 사용)
        if url in event_states:
            state = event_states[url]
            if title is not None: state['title'] = title
            if prizes is not None: state['prizes'] = prizes
            if memo is not None: state['memo'] = memo
            if allow_duplicates is not None: state['allow_duplicates'] = (allow_duplicates == True)
        else:
            # 상태가 없으면 새로 생성 (최소 정보만)
            event_states[url] = {
                'url': url,
                'title': title,
                'prizes': prizes,
                'memo': memo,
                'allow_duplicates': (allow_duplicates == True),
                'participants': {},
                'last_id': None,
                'seen_ids': set(),
                'all_commenters': []
            }
        
        # 소켓 브로드캐스트
        from comment_dart import socketio
        safe_winners = current_winners if current_winners else ""
        socketio.emit('update_event_settings', {
            'url': url,
            'title': title,
            'prizes': prizes,
            'memo': memo,
            'winners': safe_winners,
            'allow_duplicates': allow_duplicates
        })
        
        return jsonify({'message': '이벤트 설정이 성공적으로 업데이트되었습니다.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@monitor_bp.route('/api/fetch_comments', methods=['POST'])
def fetch_comments_route():
    data = request.json
    # URL 정규화
    url = normalize_url(data.get('url', ''))
    incremental = data.get('incremental', False)
    # [수정] URL 자체를 키로 사용하여 중복 방지
    event_id = url 
    
    if not url:
        return jsonify({'error': 'URL이 필요합니다.'}), 400
        
    try:
        print(f"DEBUG: [API Request] URL: {url}, incremental: {incremental}")
        
        # 1. 이벤트 데이터 초기화 또는 로드 (URL 기반)
        if url not in event_states or not incremental:
            print(f"DEBUG: Initializing state for URL: {url}")
            if not incremental:
                # [수정] 동일 URL인 경우 기존 데이터(참여자, 댓글 등) 유지하면서 수집 시작
                # 명시적인 삭제 요청이 없을 경우 clear_data 호출 안 함
                existing_participants, last_comment_id, all_c_list, title, prizes, memo, winners, allow_duplicates, _allowed_list_str = db.get_data(url)
                all_commenters = list(all_c_list) if all_c_list else []
                print(f"DEBUG: [Fetch] Loaded existing data: {len(existing_participants)} participants, {len(all_commenters)} commenters")
                
                # [중요] 기존 설정(제목, 상품, 메모 등)이 없는 경우에만 초기값 설정
                if not (title or prizes or memo):
                    title, prizes, memo, winners, allow_duplicates = None, None, None, '', True
                
                # [제거] 불필요한 clear_data 호출 차단 (데이터 소실 원인)
                # db.clear_data(url) 
            else:
                # 점진적 수집이지만 메모리에 없을 때 (페이지 새로고침 등)
                existing_participants, last_comment_id, all_c_list, title, prizes, memo, winners, allow_duplicates, _ = db.get_data(url)
                all_commenters = list(all_c_list) if all_c_list else []
            
            event_states[url] = {
                'participants': existing_participants,
                'last_id': last_comment_id,
                'url': url,
                'seen_ids': set(), # 본 댓글 ID 추적용 (이중 잠금)
                'all_commenters': all_commenters,
                'title': title,
                'prizes': prizes,
                'memo': memo,
                'winners': winners,
                'allow_duplicates': allow_duplicates,
                'allowed_list_str': _ # allowed_list_str is the last arg of get_data
            }

        current_state = event_states[url]
        last_comment_id = current_state['last_id']
        existing_participants = current_state['participants']
            
        # 댓글 수집 (Selenium은 전체 수집일 때만 기본으로 사용, 점진적 수집은 API 우선)
        # incremental=True 인 자동 모니터링 시에는 Selenium 부하를 피하기 위해 False
        use_selenium_fallback = not incremental 
        monitor = NaverCommentMonitor(use_selenium=use_selenium_fallback)
        print(f"DEBUG: Event {event_id} - Fetching comments starting after ID: {last_comment_id} (Selenium: {use_selenium_fallback})")
        comments = monitor.get_new_comments(url, last_comment_id=last_comment_id)
        
        print(f"DEBUG: Event {event_id} - Found {len(comments) if comments else 0} new filtered comments")

        
        # 2. 새로운 댓글 분석 및 화이트리스트 필터링
        allowed_list = get_allowed_list(url)
        new_participants_found = 0
        all_commenters = current_state.setdefault('all_commenters', [])
        
        if comments:
            seen_ids = current_state.setdefault('seen_ids', set())
            for comment in comments:
                cid = comment.get('comment_id')
                if cid in seen_ids: continue
                seen_ids.add(cid)
                
                writer = comment.get('author_nickname') or comment.get('author_id')
                if not writer or writer == 'None': continue
                
                # 모든 작성자 추적
                all_names = [item['name'] if isinstance(item, dict) else item for item in all_commenters]
                if writer not in all_names:
                    all_commenters.append({'name': writer, 'created_at': comment.get('created_at')})
                
                # 화이트리스트 체크 (참여자 명단)
                if writer in allowed_list:
                    # 명단에 있는 사람만 참여자로 인정하되, 배정된 티켓수를 할당
                    if writer not in existing_participants:
                        existing_participants[writer] = (allowed_list[writer], comment.get('created_at'))
                        new_participants_found += 1
        
        # 전체 댓글 수 계산 (응답용)
        total_comments_count = len(all_commenters)
        new_comments_count = len(comments) if comments else 0
        
        # 마지막 ID 업데이트 (Selenium 더미 ID 방지)
        if comments:
            for last_c in reversed(comments):
                cid = last_c.get('comment_id', '')
                if cid and not cid.startswith('selenium_'):
                    current_state['last_id'] = cid
                    break

        
        print(f"DEBUG: Event {event_id} - Extracted {len(existing_participants)} participants")
        
        # [추가] 명단 동기화 (화이트리스트 업데이트 반영)
        existing_participants, whitelist_updated = sync_participants_with_whitelist(url, existing_participants, all_commenters)
        
        # [최적화] 실시간 새로고침 무한 루프 방지: 새 댓글이 있거나, 화이트리스트 동기화로 명단이 변했거나, 전체 수집(Full Scan)일 때만 DB 동기화
        if comments or whitelist_updated or not incremental:
            # 활성 URL 설정 (URL이 바뀐 경우에만 DB 반영됨)
            set_active_url(url)
            
            # 타임스탬프 갱신 및 DB 저장 (이 작업이 Supabase Realtime 새로고침을 트리거함)
            db.update_timestamp(url)
            # [중요] 모든 설정을 함께 저장하여 Supabase 동기화 보장 (Render 환경 stale 데이터 방지)
            db.save_data(url, existing_participants, current_state['last_id'], list(all_commenters),
                         title=current_state.get('title'), prizes=current_state.get('prizes'),
                         memo=current_state.get('memo'), winners=current_state.get('winners'),
                         allow_duplicates=current_state.get('allow_duplicates'))
            print(f"DEBUG: [Fetch] DB Sync completed (New comments: {bool(comments)}, Whitelist updated: {whitelist_updated})")
        else:
            # 새 댓글이 없는 점진적 수집(Polling)인 경우, 활성 URL만 메모리에 설정
            set_active_url(url)
            # db.update_timestamp(url) # 스킵
            # db.save_data(...)      # 스킵
            # print(f"DEBUG: [Fetch] Skiped DB Sync (No new comments)")
            pass
        
        # [추가] 실시간 룰렛 업데이트용 SocketIO 브로드캐스트
        try:
            from comment_dart import socketio
            total_comments = sum(v[0] if isinstance(v, (tuple, list)) else v for v in existing_participants.values())
            
            # 룰렛 페이지가 기대하는 형식 [(이름, 횟수, 시간), ...]
            p_list_for_roulette = []
            for name, v in existing_participants.items():
                count = v[0] if isinstance(v, (tuple, list)) else v
                created_at = v[1] if isinstance(v, (tuple, list)) else None
                p_list_for_roulette.append((name, count, created_at))
            
            # [중요] 화살표 불일치 방지: 고정 정렬 순서 보장
            p_list_for_roulette.sort(key=lambda x: str(x[0]))
            
            # 모니터 페이지를 위한 전체 명단 (상태 포함)
            full_commenters_data = []
            for item in all_commenters:
                name = item['name'] if isinstance(item, dict) else item
                created_at = item.get('created_at') if isinstance(item, dict) else None
                full_commenters_data.append({
                    'name': name,
                    'is_whitelisted': name in allowed_list,
                    'tickets': allowed_list.get(name, 0),
                    'created_at': created_at
                })

            socketio.emit('update_participants', {
                'participants': p_list_for_roulette,
                'full_commenter_list': full_commenters_data,
                'total_comments': total_comments_count,
                'event_id': event_id
            })
            print(f"DEBUG: [SocketIO] Broadcasted update for event: {event_id}")
        except Exception as se:
            print(f"DEBUG: SocketIO Broadcast Error: {se}")

        # 3. 결과 포맷팅 및 응답 데이터 준비
        participant_list = [f"{name} (확정)" for name in existing_participants.keys()]
        total_participants = len(existing_participants)
        response_id = int(time.time())
        message = f'{new_participants_found}명의 새 확정 참가자 추가 (총: {total_participants}명)' if incremental else f'{total_participants}명의 확정 참가자가 수집되었습니다.'
        
        # [추가] 실시간 백그라운드 모니터링 시작
        if incremental and url not in active_monitoring_urls:
            start_background_monitoring(url)

        return jsonify({
            'event_id': event_id,
            'message': message,
            'participants': participant_list,
            'participants_raw': p_list_for_roulette,
            'full_commenter_list': full_commenters_data,
            'total_comments': total_comments_count,
            'new_comments': new_comments_count,
            'event_title': current_state.get('title'),
            'event_prizes': current_state.get('prizes'),
            'is_incremental': incremental,
            'response_id': response_id,
            'stats': {
                'unique_participants': total_participants,
                'total_comment_count': total_comments_count,
                'new_comment_count': new_comments_count,
                'collection_method': 'incremental' if incremental else 'full',
                'event_id': event_id
            }
        })
        
    except Exception as fe:
        print(f"DEBUG: Sync Error: {fe}")
        import traceback
        print(traceback.format_exc())
        return jsonify({'error': str(fe)}), 500
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"DEBUG: Error occurred:\n{error_details}")
        return jsonify({'error': str(e), 'details': error_details}), 500

def start_background_monitoring(url):
    """특정 URL에 대한 백그라운드 모니터링 루틴 시작"""
    if url in active_monitoring_urls:
        return
        
    active_monitoring_urls[url] = True
    print(f"DEBUG: [Background] Starting monitoring for {url}")
    
    from comment_dart import socketio
    
    def monitor_loop():
        scraper_inner = NaverCommentMonitor(use_selenium=False) # 백그라운드는 API 위주로 빠르게
        log_file = os.path.join(BASE_DIR, "monitor_debug.log")
        
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.now()}] Background monitoring started for {url}\n")

        while url in active_monitoring_urls:
            try:
                # 해당 URL의 상태 직접 참조 (URL이 키)
                state = event_states.get(url)
                if not state:
                    with open(log_file, "a", encoding="utf-8") as f:
                        f.write(f"[{datetime.now()}] No state for {url}. Stopping.\n")
                    active_monitoring_urls.pop(url, None)
                    break
                
                last_id = state.get('last_id')
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(f"[{datetime.now()}] [{url[-10:]}] Polling Naver (last_id: {last_id})...\n")
                
                # 단일 상태에 대해 수집 수행
                try:
                    new_comments = scraper_inner.get_new_comments(url, last_comment_id=last_id)
                except Exception as ge:
                    with open(log_file, "a", encoding="utf-8") as f:
                        f.write(f"[{datetime.now()}] [{url[-10:]}] Scraper error: {ge}\n")
                    continue
                
                if new_comments:
                    processed_count = len(new_comments)
                    with open(log_file, "a", encoding="utf-8") as f:
                        f.write(f"[{datetime.now()}] [{url[-10:]}] Found {processed_count} new comments.\n")
                    
                    seen_ids = state.setdefault('seen_ids', set())
                    allowed_list = get_allowed_list()
                    added_count = 0
                    
                    for c in new_comments:
                        cid = c.get('comment_id')
                        if cid not in seen_ids:
                            seen_ids.add(cid)
                            writer = c.get('author_nickname') or c.get('author_id')
                            if writer and writer != 'None':
                                all_commenters = state.setdefault('all_commenters', [])
                                if writer not in [item['name'] if isinstance(item, dict) else item for item in all_commenters]:
                                    all_commenters.append({'name': writer, 'created_at': c.get('created_at')})
                                if writer in allowed_list:
                                    # [중요] 중복 당첨 비허용 시, 이미 당첨된 사람은 명단에서 제외
                                    allow_duplicates = state.get('allow_duplicates', True)
                                    winners_str = state.get('winners', '')
                                    winners_list = [w.strip() for w in winners_str.split(',')] if winners_str else []
                                    
                                    if not allow_duplicates and writer in winners_list:
                                        # 이미 당첨된 사람임 -> 스킵
                                        continue
                                        
                                    if writer not in state['participants']:
                                        state['participants'][writer] = (allowed_list[writer], c.get('created_at'))
                                        added_count += 1
                    
                    # 마지막 ID 업데이트
                    for last_c in reversed(new_comments):
                        cid = last_c.get('comment_id', '')
                        if cid and not cid.startswith('selenium_'):
                            state['last_id'] = cid
                            break
                    
                    # DB 동기화 (비동기) - 기존 설정 유지
                    db.save_data(url, state['participants'], state['last_id'], list(state.get('all_commenters', [])),
                                 title=state.get('title'), prizes=state.get('prizes'),
                                 memo=state.get('memo'), winners=state.get('winners'),
                                 allow_duplicates=state.get('allow_duplicates'),
                                 allowed_list=state.get('allowed_list_str'))

                    # 무조건 업데이트 전송 (UI 갱신을 위해)
                    p_list_for_roulette = []
                    for name, v in state['participants'].items():
                        count = v[0] if isinstance(v, (tuple, list)) else v
                        created_at = v[1] if isinstance(v, (tuple, list)) else None
                        p_list_for_roulette.append((name, count, created_at))
                    # p_list_for_roulette.sort(key=lambda x: x[0])

                    full_commenters_data = []
                    all_commenters_list = state.get('all_commenters', [])
                    
                    for item in all_commenters_list:
                        name = item['name'] if isinstance(item, dict) else item
                        full_commenters_data.append({
                            'name': name,
                            'is_whitelisted': name in allowed_list,
                            'tickets': allowed_list.get(name, 0),
                            'created_at': item.get('created_at') if isinstance(item, dict) else None
                        })

                    socketio.emit('update_participants', {
                        'participants': p_list_for_roulette,
                        'full_commenter_list': full_commenters_data,
                        'total_comments': len(all_commenters_list),
                        'event_id': url,
                        'new_count': added_count
                    })
                    
                    with open(log_file, "a", encoding="utf-8") as f:
                        f.write(f"[{datetime.now()}] [{url[-10:]}] Emitted update. Total commenters: {len(all_commenters_list)}\n")
                    
                    if added_count > 0:
                        # [제거] NameError: sync_files (사용하지 않는 레거시 함수)
                        pass 
                else:
                    # 댓글이 없는 경우에도 주기적으로 생존 신고 (디버깅용)
                    if int(time.time()) % 30 == 0:
                        with open(log_file, "a", encoding="utf-8") as f:
                            f.write(f"[{datetime.now()}] [{url[-10:]}] Loop alive, no new comments.\n")

            except Exception as le:
                print(f"DEBUG: [Background Loop Error] {le}")
                
            socketio.sleep(5.0) # 5초 간격으로 안정적인 모니터링

    socketio.start_background_task(monitor_loop)

def sync_files(participants_dict, last_id):
    """메인 룰렛 연동용 파일 동기화"""
    try:
        with open(PARTICIPANTS_FILE, 'w', encoding='utf-8') as f:
            for name, count in participants_dict.items():
                f.write(f"{name} {count}\n")
        if last_id:
            with open(LAST_COMMENT_FILE, 'w', encoding='utf-8') as f:
                f.write(str(last_id))
    except: pass


@monitor_bp.route('/api/login_naver', methods=['POST'])
def login_naver():
    if not SeleniumCommentScraper:
        return jsonify({'error': 'Selenium이 설치되어 있지 않습니다.'}), 500
    
    try:
        scraper = SeleniumCommentScraper()
        success = scraper.login_to_naver()
        if success:
            return jsonify({'message': '네이버 로그인이 성공적으로 완료되었습니다.'})
        else:
            return jsonify({'error': '로그인이 완료되지 않았거나 타임아웃되었습니다.'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@monitor_bp.route('/api/load_comments', methods=['POST'])
def load_comments():
    data = request.json
    url = normalize_url(data.get('url', ''))
    
    if not url:
        return jsonify({'error': 'URL이 필요합니다.'}), 400
        
    try:
        url = normalize_url(url)
        print(f"DEBUG: [Load Request] URL: {url}")
        participants_dict, last_id, all_commenter_list, title, prizes, memo, winners, allow_duplicates, _ = db.get_data(url)
        
        if not participants_dict and not all_commenter_list:
            return jsonify({'message': '저장된 데이터가 없습니다.', 'participants': [], 'url': url})

        # [추가] 명단 동기화 (화이트리스트 업데이트 반영)
        participants_dict, whitelist_updated = sync_participants_with_whitelist(url, participants_dict, all_commenter_list)
        
        if whitelist_updated:
            print(f"DEBUG: [Load] Whitelist promotion detected, force saving to Supabase for {url}")
            db.save_data(url, participants_dict, last_id, list(all_commenter_list),
                         title=title, prizes=prizes, memo=memo, winners=winners, 
                         allow_duplicates=allow_duplicates)
        
        # [수정] 활성 URL 설정 (새로고침 루프 방지를 위해 타임스탬프 갱신 제거)
        set_active_url(url)
        # db.update_timestamp(url) # [제거] 로드 시마다 타임스탬프를 갱신하면 무한 새로고침 유발
        
        # 로드된 데이터로 메모리 상태 복구/생성 (URL을 키로 사용)
        event_id = url
        event_states[url] = {
            'participants': participants_dict,
            'all_commenters': all_commenter_list,
            'last_id': last_id,
            'url': url,
            'seen_ids': set(),
            'title': title,
            'prizes': prizes,
            'winners': winners,
            'allow_duplicates': allow_duplicates
        }
            
        # 결과 포맷팅 (티켓수 숨김)
        participant_list = [f"{name} (확정)" for name in participants_dict.keys()]
        total_participants = len(participants_dict)
        total_comments_count = len(all_commenter_list)
        
        # 전체 명단 데이터 준비
        allowed_list = get_allowed_list(url)
        full_commenters_data = []
        
        # [수정] all_commenter_list는 딕셔너리 리스트이므로 이름 기준으로 정렬
        sorted_commenters = sorted(all_commenter_list, key=lambda x: x['name'] if isinstance(x, dict) else x)
        
        for item in sorted_commenters:
            name = item['name'] if isinstance(item, dict) else item
            full_commenters_data.append({
                'name': name,
                'is_whitelisted': name in allowed_list,
                'tickets': allowed_list.get(name, 0)
            })
        
        response_id = int(time.time())
        print(f"DEBUG: [Load Response] ID: {response_id}, Total: {total_participants}")
        
        # [추가] participants.txt 파일 동기화 (룰렛 메인 화면 반영용)
        try:
            with open(PARTICIPANTS_FILE, 'w', encoding='utf-8') as f:
                for name, count in participants_dict.items():
                    f.write(f"{name} {count}\n")
            if last_id:
                with open(LAST_COMMENT_FILE, 'w', encoding='utf-8') as f:
                    f.write(last_id)
            print(f"DEBUG: [Load Sync] Synchronized participants and last ID for roulette engine")
        except Exception as se:
            print(f"DEBUG: [Load Sync Error] {se}")

        # [추가] 실시간 룰렛 업데이트용 SocketIO 브로드캐스트
        try:
            from comment_dart import socketio
            p_list_for_roulette = []
            for name, v in participants_dict.items():
                count = v[0] if isinstance(v, (tuple, list)) else v
                created_at = v[1] if isinstance(v, (tuple, list)) else None
                p_list_for_roulette.append((name, int(count), created_at))
            
            p_list_for_roulette.sort(key=lambda x: x[0])
            socketio.emit('update_participants', {
                'participants': p_list_for_roulette,
                'full_commenter_list': full_commenters_data,
                'total_comments': total_comments_count,
                'event_id': event_id
            })
            print(f"DEBUG: [SocketIO] Broadcasted loaded data update")
        except Exception as se:
            print(f"DEBUG: SocketIO Broadcast Error: {se}")

        return jsonify({
            'message': f'데이터를 성공적으로 불러왔습니다. (확정: {total_participants}명, 전체: {total_comments_count}명)',
            'participants': participant_list,
            'participants_raw': p_list_for_roulette,
            'full_commenter_list': full_commenters_data,
            'total_comments': total_comments_count,
            'event_id': event_id,
            'event_title': title or "",
            'event_prizes': prizes or "",
            'event_memo': memo or "",
            'event_winners': winners or "",
            'allow_duplicates': event_states[event_id].get('allow_duplicates', True), # Use event_states for current state
            'response_id': response_id
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@monitor_bp.route('/api/delete_event', methods=['POST'])
def delete_event():
    data = request.json
    url = normalize_url(data.get('url', ''))
    
    if not url:
        return jsonify({'error': 'URL이 필요합니다.'}), 400
        
    try:
        # 1. DB 데이터 삭제 (완전 삭제)
        db.clear_data(url)
        
        # 2. 메모리 상태(event_states)에서 해당 URL을 가진 모든 이벤트 제거
        keys_to_delete = []
        for eid, state in event_states.items():
            if state.get('url') == url:
                keys_to_delete.append(eid)
        
        for eid in keys_to_delete:
            del event_states[eid]
            print(f"DEBUG: [Memory] Cleared state for event {eid} (URL: {url})")

        # 3. 만약 현재 활성 URL이면 상태 파일 및 임시 파일 초기화
        current_active = None
        if os.path.exists(ACTIVE_URL_FILE):
            with open(ACTIVE_URL_FILE, 'r', encoding='utf-8') as f:
                current_active = normalize_url(f.read().strip())
        
        if current_active == url:
            set_active_url(None)
            # 임시 파일들 정리
            for fpath in [PARTICIPANTS_FILE, LAST_COMMENT_FILE]:
                if os.path.exists(fpath):
                    with open(fpath, 'w', encoding='utf-8') as f:
                        f.write("")
            print(f"DEBUG: [Files] Cleared active files for URL: {url}")
            
            # 클라이언트에게 즉시 알림 (화면 초기화 유도)
            try:
                from comment_dart import socketio
                socketio.emit('update_event_settings', {
                    'title': '', 'prizes': '', 'memo': '', 'winners': '', 'participants': []
                })
            except Exception as se:
                print(f"DEBUG: Socket emit error during delete: {se}")
        
        return jsonify({'message': f'이벤트({url}) 데이터가 성공적으로 삭제되었습니다.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@monitor_bp.route('/api/get_stored_urls', methods=['GET'])
def get_stored_urls():
    try:
        urls = db.get_all_urls()
        return jsonify({'urls': urls})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@monitor_bp.route('/api/get_allowed_list', methods=['GET', 'POST'])
def api_get_allowed_list():
    # POST요청인 경우 body에서 URL을 가져오고, GET요청인 경우 query parameter에서 가져옴
    if request.method == 'POST':
        data = request.json or {}
    else:
        data = request.args
    
    url = normalize_url(data.get('url', ''))
    
    try:
        if url:
            # DB에서 먼저 조회
            _, _, _, _, _, _, _, _, allowed_list_content = db.get_data(url)
            if allowed_list_content is not None:
                return jsonify({'content': allowed_list_content})
        
        if not os.path.exists(ALLOWED_LIST_FILE):
            return jsonify({'content': ''})
        with open(ALLOWED_LIST_FILE, 'r', encoding='utf-8') as f:
            return jsonify({'content': f.read()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@monitor_bp.route('/api/naver_login', methods=['POST'])
def naver_login():
    """Selenium을 사용하여 네이버 수동 로그인을 실행하고 쿠키를 갱신합니다."""
    if not SeleniumCommentScraper:
        return jsonify({'error': 'Selenium을 사용할 수 없는 환경입니다.'}), 500
        
    try:
        scraper = SeleniumCommentScraper()
        success = scraper.login_to_naver()
        if success:
            return jsonify({'message': '네이버 로그인이 완료되었습니다. 이제 댓글 수집이 가능합니다.'})
        else:
            return jsonify({'error': '로그인이 완료되지 않았거나 취소되었습니다.'}), 400
    except Exception as e:
        return jsonify({'error': f'로그인 중 오류 발생: {str(e)}'}), 500

@monitor_bp.route('/api/save_allowed_list', methods=['POST'])
def api_save_allowed_list():
    data = request.json
    content = data.get('content', '')
    url = normalize_url(data.get('url', ''))
    try:
        if url:
            # 1. DB에 저장을 먼저 수행 (get_allowed_list가 DB를 보므로)
            db.save_data(url, None, None, allowed_list=content)
            
            # 2. [추가] 즉시 명단 업데이트 및 동기화 (수동 수집 버튼 안 눌러도 반영되도록)
            if url in event_states:
                state = event_states[url]
                existing_p = state.get('participants', {})
                all_c = state.get('all_commenters', [])
                
                # 명단 동기화 실행
                updated_p, updated = sync_participants_with_whitelist(url, existing_p, all_c)
                
                if updated:
                    print(f"DEBUG: [WhitelistSave] Participants promoted, force saving to Supabase")
                    db.save_data(url, updated_p, state.get('last_id'), list(all_c),
                                 title=state.get('title'), prizes=state.get('prizes'),
                                 memo=state.get('memo'), winners=state.get('winners'),
                                 allow_duplicates=state.get('allow_duplicates'))
                    
                    # 소켓 브로드캐스트 (실시간 UI 반영)
                    from comment_dart import socketio
                    socketio.emit('update_participants', {
                        'participants': [(n, c[0], c[1]) for n, c in updated_p.items()],
                        'total_comments': len(all_c),
                        'event_id': url
                    })
            
            return jsonify({'message': '명단이 DB에 저장되었습니다.'})
        
        with open(ALLOWED_LIST_FILE, 'w', encoding='utf-8') as f:
            f.write(content)
        return jsonify({'message': '명단이 파일에 저장되었습니다.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
