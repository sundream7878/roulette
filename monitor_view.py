import os
import time
from flask import Blueprint, render_template, request, jsonify
from standalone_comment_monitor.scraper import NaverCommentMonitor
from standalone_comment_monitor.db_handler import CommentDatabase
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
    """현재 관리 중인 URL을 파일에 저장합니다."""
    # 정규화하여 저장
    from standalone_comment_monitor.parsers import parse_post_ids_from_url
    clubid, articleid = parse_post_ids_from_url(url)
    if clubid and articleid:
        url = f"https://cafe.naver.com/ca-fe/web/cafes/{clubid}/articles/{articleid}"
    
    try:
        # DB에 활성 상태 저장 (Render 환경 대응)
        db.set_active_url(url)
        
        with open(ACTIVE_URL_FILE, 'w', encoding='utf-8') as f:
            f.write(url.strip())
        print(f"DEBUG: Active URL set to: {url}")
    except Exception as e:
        print(f"ERROR: Failed to set active URL: {e}")

def normalize_url(url):
    """URL을 표준 형식으로 정규화합니다."""
    from standalone_comment_monitor.parsers import parse_post_ids_from_url
    clubid, articleid = parse_post_ids_from_url(url)
    if clubid and articleid:
        return f"https://cafe.naver.com/ca-fe/web/cafes/{clubid}/articles/{articleid}"
    return url.strip()

def get_allowed_list():
    """명단을 {이름: 티켓수} 사전 형식으로 파싱합니다."""
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
                        tickets = 1 # 파싱 실패시 기본 1장
                    allowed[name] = tickets
                else:
                    # 티켓수 없이 이름만 있는 경우 기본 1장
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
    'participant_count': -1,
    'title': None,
    'prizes': None,
    'active_url': None,
}
_supabase_polling_started = False

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
        post_res = db.supabase.table('posts').select('url, title, prizes, winners, updated_at').eq('is_active', True).limit(1).execute()
        if not post_res.data:
            return
        post = post_res.data[0]
        url = post['url']
        title = post.get('title')
        prizes = post.get('prizes')
        winners = post.get('winners')
        updated_at = post.get('updated_at')

        # 이벤트 설정 브로드캐스트
        socketio.emit('update_event_settings', {
            'url': url, 'title': title, 'prizes': prizes, 'winners': winners,
        })

        # 참가자 브로드캐스트
        p_res = db.supabase.table('participants').select('author, count').eq('url', url).execute()
        participants = p_res.data or []
        if participants:
            p_list = sorted([(r['author'], r['count']) for r in participants], key=lambda x: x[0])
            socketio.emit('update_participants', {
                'participants': p_list, 'total_comments': len(p_list), 'event_id': 'realtime'
            })

        # 상태 갱신
        _last_supabase_state.update({
            'updated_at': updated_at, 'title': title, 'prizes': prizes,
            'participant_count': len(participants), 'active_url': url
        })
    except Exception as e:
        print(f"DEBUG: [Realtime Broadcast Error] {e}")

def _supabase_poll_loop():
    """2초마다 Supabase를 확인하고 변경이 있으면 즉시 브로드캐스트"""
    import time as _time
    global _last_supabase_state
    _time.sleep(3)  # 서버 초기화 대기

    # ── 첫 번째 루프: 현재 DB 상태를 조용히 읽어서 기준값으로 설정 ──
    # 이렇게 해야 서버 재시작 직후 "변경 없음인데 emit"하는 오작동을 막을 수 있음
    try:
        if db.supabase:
            post_res = db.supabase.table('posts').select('url, title, prizes, winners, updated_at').eq('is_active', True).limit(1).execute()
            if post_res.data:
                post = post_res.data[0]
                url = post['url']
                p_res = db.supabase.table('participants').select('author').eq('url', url).execute()
                _last_supabase_state.update({
                    'updated_at': post.get('updated_at'),
                    'title': post.get('title'),
                    'prizes': post.get('prizes'),
                    'active_url': url,
                    'participant_count': len(p_res.data) if p_res.data else 0,
                })
                print(f"DEBUG: [Realtime] Initial state loaded: {len(p_res.data or [])} participants, title={post.get('title')}")
    except Exception as e:
        print(f"DEBUG: [Realtime] Init error: {e}")

    while True:
        try:
            from comment_dart import socketio
            if not db.supabase:
                _time.sleep(5)
                continue

            # 활성 포스트 조회
            post_res = db.supabase.table('posts').select('url, title, prizes, winners, updated_at').eq('is_active', True).limit(1).execute()
            if not post_res.data:
                _time.sleep(2)
                continue

            post = post_res.data[0]
            url = post['url']
            updated_at = post.get('updated_at')
            title = post.get('title')
            prizes = post.get('prizes')
            winners = post.get('winners')

            # 이전 상태와 비교해서 실제 변경이 있을 때만 브로드캐스트
            settings_changed = (
                updated_at != _last_supabase_state['updated_at'] or
                title != _last_supabase_state['title'] or
                prizes != _last_supabase_state['prizes'] or
                url != _last_supabase_state['active_url']
            )

            if settings_changed:
                print(f"DEBUG: [Realtime] Settings changed! Broadcasting...")
                socketio.emit('update_event_settings', {
                    'url': url, 'title': title, 'prizes': prizes, 'winners': winners,
                })
                _last_supabase_state['title'] = title
                _last_supabase_state['prizes'] = prizes
                _last_supabase_state['active_url'] = url
                _last_supabase_state['updated_at'] = updated_at

            # 참가자 수 변경은 별도로 체크 (updated_at 변경 없이도 추가될 수 있음)
            p_res = db.supabase.table('participants').select('author, count').eq('url', url).execute()
            participants = p_res.data or []
            if len(participants) != _last_supabase_state['participant_count']:
                p_list = sorted([(r['author'], r['count']) for r in participants], key=lambda x: x[0])
                print(f"DEBUG: [Realtime] Participants changed ({len(p_list)}명) → broadcasting")
                socketio.emit('update_participants', {
                    'participants': p_list, 'total_comments': len(p_list), 'event_id': 'realtime'
                })
                _last_supabase_state['participant_count'] = len(participants)

        except Exception as e:
            print(f"DEBUG: [Realtime Poll Error] {e}")
        _time.sleep(2)

# ─────────────────────────────────────────────────────────────────────────────


def sync_participants_with_whitelist(url, existing_participants, all_commenters):
    """
    이미 수집된 '모든 작성자' 중에서 '사전 명단(화이트리스트)'에 있는 사람을 
    참여자 명단으로 동적으로 업데이트합니다.
    """
    allowed_list = get_allowed_list()
    updated = False
    
    for name in all_commenters:
        if name in allowed_list and name not in existing_participants:
            existing_participants[name] = allowed_list[name]
            updated = True
            print(f"DEBUG: [Sync] Promoted '{name}' to participant (found in whitelist)")
            
    if updated:
        # DB 업데이트 및 파일 동기화
        db.save_data(url, existing_participants, '', list(all_commenters))
        sync_files(existing_participants, None)
        
    return existing_participants, updated


@monitor_bp.route('/monitor_page')
def monitor_page():
    return render_template('monitor.html')

@monitor_bp.route('/api/update_event_settings', methods=['POST'])
def update_event_settings():
    data = request.json
    url = normalize_url(data.get('url', ''))
    title = data.get('title')
    prizes = data.get('prizes')
    allow_duplicates = data.get('allow_duplicates')
    
    if not url:
        return jsonify({'error': 'URL이 필요합니다.'}), 400
        
    try:
        # DB 저장 (입력된 값만 업데이트됨)
        # participants_dict를 None으로 주어 기존 명단이 삭제되지 않도록 함
        db.save_data(url, None, '', title=title, prizes=prizes, allow_duplicates=allow_duplicates)
        
        # [추가] 설정 저장 시 해당 이벤트를 활성화 (룰렛 화면에 즉시 반영되도록)
        set_active_url(url)
        
        # 메모리 상태 업데이트
        for eid, state in event_states.items():
            if state.get('url') == url:
                if title is not None: state['title'] = title
                if prizes is not None: state['prizes'] = prizes
                if allow_duplicates is not None: state['allow_duplicates'] = (allow_duplicates == True)
        
        # 소켓 브로드캐스트
        from comment_dart import socketio
        socketio.emit('update_event_settings', {
            'url': url,
            'title': title,
            'prizes': prizes,
            'allow_duplicates': allow_duplicates
        })
        
        return jsonify({'message': '이벤트 설정이 성공적으로 업데이트되었습니다.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@monitor_bp.route('/api/fetch_comments', methods=['POST'])
def fetch_comments_route():
    data = request.json
    url = normalize_url(data.get('url', ''))
    incremental = data.get('incremental', False)
    event_id = data.get('event_id', 'default_event') # 이벤트 격리용 키
    
    if not url:
        return jsonify({'error': 'URL이 필요합니다.'}), 400
        
    try:
        # URL 정규화 및 ID 추출 (normalize_url에서 이미 처리됨)
        # from standalone_comment_monitor.parsers import parse_post_ids_from_url
        # clubid, articleid = parse_post_ids_from_url(url)
        
        canonical_url = url # Already normalized by normalize_url
        # if clubid and articleid:
        #     canonical_url = f"https://cafe.naver.com/ca-fe/web/cafes/{clubid}/articles/{articleid}"
        
        print(f"DEBUG: [API Request] Event: {event_id}, URL: {canonical_url}, incremental: {incremental}")
        
        url = canonical_url 

        # 1. 이벤트 데이터 초기화 또는 로드
        # [수정] URL이 변경된 경우에도 새로 시작해야 함 (동일 event_id로 다른 URL 수집 시 데이터 섞임 방지)
        is_url_changed = False
        if event_id in event_states and event_states[event_id].get('url') != url:
            print(f"DEBUG: URL changed for event {event_id}. Forcing fresh state.")
            is_url_changed = True

        if not incremental or event_id not in event_states or is_url_changed:
            print(f"DEBUG: Initializing fresh state for event: {event_id}")
            # DB에서 해당 URL의 데이터를 가져와 초기값으로 사용하거나, 완전 초기화
            if not incremental or is_url_changed:
                # 완전 새로 시작하는 경우 (새 이벤트 버튼 또는 URL 변경)
                last_comment_id = None
                existing_participants = {}
                db.clear_data(url) # DB 초기화 (기본 정책 유지 시)
                
                # 메인 룰렛용 임시 파일도 초기화
                if os.path.exists(PARTICIPANTS_FILE):
                    with open(PARTICIPANTS_FILE, 'w', encoding='utf-8') as f: f.write('')
                if os.path.exists(LAST_COMMENT_FILE):
                    with open(LAST_COMMENT_FILE, 'w', encoding='utf-8') as f: f.write('')
            else:
                # 점진적 수집이지만 메모리에 없을 때 (페이지 새로고침 등)
                existing_participants, all_c_list, last_comment_id, title, prizes, winners, allow_duplicates = db.get_data(url)
            
            event_states[event_id] = {
                'participants': existing_participants,
                'last_id': last_comment_id,
                'url': url,
                'seen_ids': set(), # 본 댓글 ID 추적용 (이중 잠금)
                'all_commenters': set(all_c_list) if 'all_c_list' in locals() else set(),
                'title': title if 'title' in locals() else None,
                'prizes': prizes if 'prizes' in locals() else None,
                'winners': winners if 'winners' in locals() else None,
                'allow_duplicates': allow_duplicates if 'allow_duplicates' in locals() else True
            }
            # 초기 로드시 현재 알고 있는 ID들 채워넣기 (이미 DB 등에 기록된 상태 반영)
            # 단, 초기화(incremental=False) 시에는 비워두어야 함

        
        current_state = event_states[event_id]
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
        allowed_list = get_allowed_list()
        new_participants_found = 0
        all_commenters = current_state.setdefault('all_commenters', set())
        
        if comments:
            seen_ids = current_state.setdefault('seen_ids', set())
            for comment in comments:
                cid = comment.get('comment_id')
                if cid in seen_ids: continue
                seen_ids.add(cid)
                
                writer = comment.get('author_nickname') or comment.get('author_id')
                if not writer or writer == 'None': continue
                
                # 모든 작성자 추적
                all_commenters.add(writer)
                
                # 화이트리스트 체크 (참여자 명단)
                if writer in allowed_list:
                    # 명단에 있는 사람만 참여자로 인정하되, 배정된 티켓수를 할당
                    if writer not in existing_participants:
                        existing_participants[writer] = allowed_list[writer]
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
        existing_participants, _ = sync_participants_with_whitelist(url, existing_participants, all_commenters)
        
        # [추가] 활성 URL 설정 및 타임스탬프 갱신
        set_active_url(url)
        db.update_timestamp(url)
        
        # DB 저장 및 파일 동기화 (최종 결과만)
        db.save_data(url, existing_participants, current_state['last_id'], list(all_commenters))
        
        try:
            with open(PARTICIPANTS_FILE, 'w', encoding='utf-8') as f:
                for name, count in existing_participants.items():
                    f.write(f"{name} {count}\n")
            if current_state.get('last_id'):
                with open(LAST_COMMENT_FILE, 'w', encoding='utf-8') as f:
                    f.write(str(current_state['last_id']))
                    
            # [추가] 실시간 룰렛 업데이트용 SocketIO 브로드캐스트

            try:
                from comment_dart import socketio
                total_comments = sum(existing_participants.values()) # 여기서 정의
                
                # 룰렛 페이지가 기대하는 형식 [(이름, 횟수), ...]
                p_list_for_roulette = [(name, int(count)) for name, count in existing_participants.items()]
                # 가나다순 정렬
                p_list_for_roulette.sort(key=lambda x: x[0])
                
                # 모니터 페이지를 위한 전체 명단 (상태 포함)
                full_commenters_data = []
                # 정렬해서 보냄
                sorted_all = sorted(list(all_commenters))
                for name in sorted_all:
                    is_whitelisted = name in allowed_list
                    tickets = allowed_list.get(name, 0)
                    full_commenters_data.append({
                        'name': name,
                        'is_whitelisted': is_whitelisted,
                        'tickets': tickets
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

        except Exception as fe:
            print(f"DEBUG: Sync Error: {fe}")
        
        # 결과 포맷팅 (티켓수 숨김 - 요청 반영)
        participant_list = [f"{name} (확정)" for name in existing_participants.keys()]
        total_participants = len(existing_participants)
        
        response_id = int(time.time())
        message = f'{new_participants_found}명의 새 확정 참가자 추가 (총: {total_participants}명)' if incremental else f'{total_participants}명의 확정 참가자가 수집되었습니다.'
        
        # [추가] 실시간 백그라운드 모니터링 시작 (이미 시작되지 않았다면)
        if incremental and url not in active_monitoring_urls:
            start_background_monitoring(url)

        return jsonify({
            'event_id': event_id,
            'message': message,
            'participants': participant_list, # 확정 명단 (String 표시용)
            'participants_raw': p_list_for_roulette, # Raw data for UI table
            'full_commenter_list': full_commenters_data if 'full_commenters_data' in locals() else [],
            'total_comments': total_comments_count,
            'new_comments': new_comments_count,
            'event_title': current_state.get('title'),
            'event_prizes': current_state.get('prizes'),
            'is_incremental': incremental,
            'response_id': response_id,
            'stats': {
                'unique_participants': len(existing_participants),
                'total_comment_count': total_comments_count,
                'new_comment_count': new_comments_count,
                'collection_method': 'incremental' if incremental else 'full',
                'event_id': event_id
            }
        })
        
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
        
        while url in active_monitoring_urls:
            try:
                # 해당 URL을 사용하는 모든 이벤트들의 상태 확인 및 업데이트
                target_events = [eid for eid, state in event_states.items() if state.get('url') == url]
                
                if not target_events:
                    print(f"DEBUG: [Background] No active events for {url}. Stopping.")
                    active_monitoring_urls.pop(url, None)
                    break
                
                for eid in target_events:
                    state = event_states[eid]
                    last_id = state.get('last_id')
                    
                    new_comments = scraper_inner.get_new_comments(url, last_comment_id=last_id)
                    
                    if new_comments:
                        print(f"DEBUG: [Background] Found {len(new_comments)} new comments for event {eid}")
                        seen_ids = state.setdefault('seen_ids', set())
                        
                        allowed_list = get_allowed_list()
                        added_count = 0
                        for c in new_comments:
                            cid = c.get('comment_id')
                            if cid not in seen_ids:
                                seen_ids.add(cid)
                                writer = c.get('author_nickname') or c.get('author_id')
                                if writer and writer != 'None':
                                    # 모든 작성자 추적
                                    all_commenters = state.setdefault('all_commenters', set())
                                    all_commenters.add(writer)
                                    
                                    # 화이트리스트 체크
                                    if writer in allowed_list:
                                        if writer not in state['participants']:
                                            state['participants'][writer] = allowed_list[writer]
                                            added_count += 1
                        
                        any_new_commenter = False
                        if added_count > 0:
                            # 마지막 ID 업데이트
                            for last_c in reversed(new_comments):
                                cid = last_c.get('comment_id', '')
                                if cid and not cid.startswith('selenium_'):
                                    state['last_id'] = cid
                                    break
                            
                            # DB 동기화
                            db.save_data(url, state['participants'], state['last_id'], list(all_commenters))
                            any_new_commenter = True

                        # 새 댓글 작성자가 추가됐는지 확인 (화이트리스트 여부 관계없이)
                        new_commenter_count = len(state.get('all_commenters', set()))
                        if new_commenter_count != state.get('_last_broadcast_commenter_count', -1):
                            any_new_commenter = True
                            state['_last_broadcast_commenter_count'] = new_commenter_count

                        if any_new_commenter:
                            # UI 업데이트 소켓 전송
                            # 룰렛용 명단 [(이름, 티켓수), ...]
                            p_list_for_roulette = [(name, int(count)) for name, count in state['participants'].items()]
                            p_list_for_roulette.sort(key=lambda x: x[0])

                            # 전체 명단 데이터 준비
                            full_commenters_data = []
                            all_commenters = state.setdefault('all_commenters', set())
                            allowed_list = get_allowed_list()
                            
                            for name in sorted(list(all_commenters)):
                                full_commenters_data.append({
                                    'name': name,
                                    'is_whitelisted': name in allowed_list,
                                    'tickets': allowed_list.get(name, 0)
                                })

                            socketio.emit('update_participants', {
                                'participants': p_list_for_roulette,
                                'full_commenter_list': full_commenters_data,
                                'total_comments': len(all_commenters),
                                'event_id': eid,
                                'new_count': added_count
                            })
                            
                            # 룰렛용 파일 동기화
                            if added_count > 0:
                                sync_files(state['participants'], state['last_id'])

            except Exception as le:
                print(f"DEBUG: [Background Loop Error] {le}")
                
            socketio.sleep(0.2) # 0.2초 간격으로 초고속 모니터링

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
        participants_dict, all_commenter_list, last_id, title, prizes, winners, allow_duplicates = db.get_data(url)
        
        if not participants_dict and not all_commenter_list:
            return jsonify({'message': '저장된 데이터가 없습니다.', 'participants': [], 'url': url})

        # [추가] 명단 동기화 (화이트리스트 업데이트 반영)
        participants_dict, _ = sync_participants_with_whitelist(url, participants_dict, all_commenter_list)
        
        # [추가] 활성 URL 설정 및 타임스탬프 갱신
        set_active_url(url)
        db.update_timestamp(url)
        
        # 로드된 데이터로 메모리 상태 복구/생성
        event_id = str(int(time.time()))
        event_states[event_id] = {
            'participants': participants_dict,
            'all_commenters': set(all_commenter_list),
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
        allowed_list = get_allowed_list()
        full_commenters_data = []
        for name in sorted(all_commenter_list):
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
            p_list_for_roulette = [(name, int(count)) for name, count in participants_dict.items()]
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
            'event_title': title,
            'event_prizes': prizes,
            'event_winners': winners,
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
        # 1. DB 데이터 삭제
        db.clear_data(url)
        
        # 2. 메모리 상태(event_states)에서 해당 URL을 가진 모든 이벤트 제거
        keys_to_delete = []
        for eid, state in event_states.items():
            if state.get('url') == url:
                keys_to_delete.append(eid)
        
        for eid in keys_to_delete:
            del event_states[eid]
            print(f"DEBUG: [Memory] Cleared state for event {eid} (URL: {url})")

        # 3. 만약 현재 PARTICIPANTS_FILE에 이 URL의 데이터가 있다면 초기화
        # (비교 로직이 복잡하므로 그냥 간단히 초기화하거나 유지 - 여기서는 간단히 무시)
        
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

@monitor_bp.route('/api/get_allowed_list', methods=['GET'])
def api_get_allowed_list():
    try:
        if not os.path.exists(ALLOWED_LIST_FILE):
            return jsonify({'content': ''})
        with open(ALLOWED_LIST_FILE, 'r', encoding='utf-8') as f:
            return jsonify({'content': f.read()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@monitor_bp.route('/api/save_allowed_list', methods=['POST'])
def api_save_allowed_list():
    data = request.json
    content = data.get('content', '')
    try:
        with open(ALLOWED_LIST_FILE, 'w', encoding='utf-8') as f:
            f.write(content)
        return jsonify({'message': '명단이 저장되었습니다.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
