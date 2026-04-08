import sys
import os
import time
import json
import unicodedata
import random
import datetime

from flask import Flask, render_template, send_from_directory, request, jsonify, Blueprint, redirect, url_for, flash
from flask_cors import CORS
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user
from wtforms import Form, StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired

from flask_socketio import SocketIO

from standalone_comment_monitor.db_handler import CommentDatabase
from event_utils import normalize_event_id, format_event_at_display, get_allowed_list as _get_allowed_list_util
from operator_routes import operator_bp

db = CommentDatabase()
# 과거 monitor_view와 공유하던 메모리 상태 (선택적 동기화)
event_states = {}

HAS_MONITOR = True  # Supabase/DB 이벤트·사전명단 사용
_LAST_ACTIVE_EVENT_KEY = None  # Supabase 일시 장애 시 활성 이벤트 폴백 캐시
_RECENT_CONFIRM_GUARD = {}  # key: "<event>::<winner>" -> ts
_PROCESSED_ROUND_CONFIRM = {}  # key: round_id -> ts


def get_allowed_list(url=None):
    return _get_allowed_list_util(db, url)


def _is_effectively_empty_event_fetch(participants_dict, title, prizes, memo, winners, allowed_list_text):
    """Supabase 일시 실패로 빈 스냅샷이 내려온 경우를 감지."""
    no_participants = not participants_dict
    no_title = not str(title or "").strip()
    no_prizes = not str(prizes or "").strip()
    no_memo = not str(memo or "").strip()
    no_winners = not str(winners or "").strip()
    no_allowed = not str(allowed_list_text or "").strip()
    return no_participants and no_title and no_prizes and no_memo and no_winners and no_allowed


def _should_skip_duplicate_confirm(event_id: str, winner: str, ttl_sec: int = 12) -> bool:
    """짧은 시간 내 동일 이벤트/당첨자 confirm 중복 요청을 무시."""
    now_ts = time.time()
    # 오래된 키 정리
    stale_keys = [k for k, ts in _RECENT_CONFIRM_GUARD.items() if now_ts - ts > max(30, ttl_sec * 2)]
    for k in stale_keys:
        _RECENT_CONFIRM_GUARD.pop(k, None)
    key = f"{event_id}::{winner}"
    prev = _RECENT_CONFIRM_GUARD.get(key)
    if prev and (now_ts - prev) < ttl_sec:
        return True
    _RECENT_CONFIRM_GUARD[key] = now_ts
    return False


def _is_already_processed_round(round_id: str, ttl_sec: int = 180) -> bool:
    if not round_id:
        return False
    now_ts = time.time()
    stale_keys = [k for k, ts in _PROCESSED_ROUND_CONFIRM.items() if now_ts - ts > ttl_sec]
    for k in stale_keys:
        _PROCESSED_ROUND_CONFIRM.pop(k, None)
    if round_id in _PROCESSED_ROUND_CONFIRM:
        return True
    _PROCESSED_ROUND_CONFIRM[round_id] = now_ts
    return False


def _is_hangul_char(ch: str) -> bool:
    if not ch:
        return False
    code = ord(ch)
    return (
        0xAC00 <= code <= 0xD7A3  # Hangul Syllables
        or 0x1100 <= code <= 0x11FF  # Hangul Jamo
        or 0x3130 <= code <= 0x318F  # Hangul Compatibility Jamo
        or 0xA960 <= code <= 0xA97F  # Hangul Jamo Extended-A
        or 0xD7B0 <= code <= 0xD7FF  # Hangul Jamo Extended-B
    )


def _ko_first_name_key(name: str):
    """한글 이름을 영문/기타보다 먼저 정렬하기 위한 키."""
    s = unicodedata.normalize("NFC", str(name or "").strip())
    if not s:
        return (2, "")
    group = 0 if _is_hangul_char(s[0]) else 1
    return (group, s.casefold())


def _normalize_ticket_count(v):
    """participants dict 값: 스칼라 또는 (count, created_at) 등 튜플."""
    if isinstance(v, (tuple, list)):
        raw = v[0] if v else 0
    else:
        raw = v
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 1


def _roulette_pairs_from_participants_dict(participants_dict, winners_str, allow_duplicates):
    """load_participants와 동일 정책으로 룰렛용 [(이름, 횟수), ...]."""
    if not participants_dict:
        return []
    won_names = []
    if winners_str:
        won_names = [w.strip() for w in winners_str.split(',') if w.strip()]
    policy_allow_duplicates = (allow_duplicates != False)
    out = []
    for name, v in participants_dict.items():
        if not policy_allow_duplicates and name in won_names:
            continue
        out.append((name, _normalize_ticket_count(v)))
    out.sort(key=lambda x: _ko_first_name_key(x[0]))
    return out


def _event_at_input_local_value(iso_str):
    """datetime-local 입력용 YYYY-MM-DDTHH:mm (브라우저 기본)."""
    if not iso_str:
        return ""
    s = str(iso_str).replace("Z", "").split("+")[0].strip()
    if " " in s and "T" not in s:
        s = s.replace(" ", "T", 1)
    if len(s) >= 16:
        return s[:16]
    if len(s) >= 10:
        return s[:10] + "T12:00"
    return ""


def get_active_url():
    """현재 활성화된 이벤트 URL을 가져옵니다."""
    global _LAST_ACTIVE_EVENT_KEY
    if not HAS_MONITOR: return None
    cache_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "active_event.txt")
    try:
        # DB에서 활성 URL 가져오기
        uid = db.get_active_event_id()
        if uid:
            key = normalize_event_id(uid)
            _LAST_ACTIVE_EVENT_KEY = key
            try:
                with open(cache_file, "w", encoding="utf-8") as f:
                    f.write(str(key))
            except Exception:
                pass
            return key
    except Exception:
        pass
    # Supabase 일시 오류 시 마지막 성공 이벤트로 폴백 (운영 중 "참여자 없음" 오탐 방지)
    if _LAST_ACTIVE_EVENT_KEY:
        return _LAST_ACTIVE_EVENT_KEY
    try:
        if os.path.exists(cache_file):
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = (f.read() or "").strip()
            if cached:
                _LAST_ACTIVE_EVENT_KEY = normalize_event_id(cached)
                return _LAST_ACTIVE_EVENT_KEY
    except Exception:
        pass
    return None


def _ensure_default_active_event():
    """활성 이벤트가 없으면 가장 최근 히스토리 1건을 자동 활성화 (운영·게스트 동일 데이터)."""
    if not HAS_MONITOR:
        return
    try:
        if db.get_active_event_id():
            return
        evs = db.list_events(limit=1)
        row = evs[0] if evs else None
        ek = (row or {}).get("id") or (row or {}).get("url")
        if ek:
            # 중요: 첫 페이지 렌더 전에 활성 이벤트가 확정되어야
            # load_participants()가 빈 목록으로 떨어지지 않는다.
            ok, err = db.set_active_event_id_blocking(ek)
            if ok:
                print(f"DEBUG: [ensure_active] Latest event activated: {ek}")
            else:
                print(f"DEBUG: [ensure_active] activate failed: {err}")
    except Exception as e:
        print(f"DEBUG: [ensure_active] {e}")


app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['ROULETTE_DB'] = db

@app.after_request
def add_header(response):
    """모든 응답에 캐시 방지 헤더를 추가하여 브라우저/CDN이 과거 데이터를 보여주는 것을 막습니다."""
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/debug')
def debug_view():
    """Render 환경 디버깅을 위한 상태 반환"""
    import os
    info = {
        "supabase_url": os.getenv('SUPABASE_URL', '')[:20] + '...',
        "has_supabase_key": bool(os.getenv('SUPABASE_KEY')),
        "has_monitor": HAS_MONITOR,
        "db_is_supabase": bool(db.supabase) if HAS_MONITOR else False
    }
    if HAS_MONITOR and db.supabase:
        try:
            key_col = getattr(db, "_post_key_col", "id")
            res = db.supabase.table('posts').select(f'{key_col}, title, prizes, is_active').order('updated_at', desc=True).limit(2).execute()
            info['recent_posts'] = res.data
        except Exception as e:
            info['supabase_error'] = str(e)
    return jsonify(info)

app.register_blueprint(operator_bp)

# CORS 설정 추가
CORS(app)

# [수정됨] SocketIO 객체 수정: async_mode를 'threading'으로 변경 (빌드 에러 방지)
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins="*")

# ----- 로그인 매니저 설정 -----
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id):
        self.id = id

@login_manager.user_loader
def load_user(user_id):
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    users_file = os.path.join(BASE_DIR, 'users.txt')
    try:
        with open(users_file, 'r', encoding='utf-8') as f:
            for line in f:
                user_id_stored, password_hash = line.strip().split(':')
                if user_id == user_id_stored:
                    return User(user_id)
    except Exception as e:
        print("[ERROR] load_user:", e)
    return None

# ----- 로그인 폼 (WTForms만 사용) -----
class LoginForm(Form):
    username = StringField('ID', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        form = LoginForm(request.form)
        if form.validate():
            username = form.username.data
            password = form.password.data
            BASE_DIR = os.path.dirname(os.path.abspath(__file__))
            users_file = os.path.join(BASE_DIR, 'users.txt')
            try:
                with open(users_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        user_id, password_hash = line.strip().split(':')
                        if user_id == username and password_hash == password:
                            user = User(user_id)
                            login_user(user)
                            flash('로그인 성공!', 'success')
                            return redirect(url_for('index'))
                flash('잘못된 ID 또는 비밀번호입니다.', 'danger')
            except Exception as e:
                flash('사용자 파일을 찾을 수 없습니다.', 'danger')
        else:
            flash('폼 검증 실패.', 'danger')
        return render_template('login.html', form=form)
    else:
        form = LoginForm()
        return render_template('login.html', form=form)

@app.route('/logout')
def logout():
    if current_user.is_authenticated:
        logout_user()
    return redirect(url_for('index'))

@app.route('/guest')
def guest_view():
    if HAS_MONITOR:
        _ensure_default_active_event()
    active_url = get_active_url() if HAS_MONITOR else None
    p_data = load_participants(active_event_id=active_url)
    p_list = p_data if p_data else []
    
    # colors 리스트 생성
    p_colors = []
    for i in range(len(p_list)):
        h = i * 360 / len(p_list) if p_list else 0
        p_colors.append(f"hsl({h}, 70%, 50%)")
        
    # 가장 최근에 업데이트된 글 정보 가져오기 (가중치/제목/사은품/당첨자/중복허용 보관용)
    title = None
    prizes = None
    memo = None
    winners = None
    event_at_display = ""
    event_at_input_value = ""
    confirmed_names = [unicodedata.normalize('NFC', p[0].strip()) for p in p_list] if p_list else []
    allow_duplicates_dash = False
    
    if HAS_MONITOR:
        try:
            active_url = active_url or get_active_url()
            if active_url:
                _, _, _, title, prizes, memo, winners, allow_dup_raw, _, event_at_raw = db.get_data(active_url)
                allow_duplicates_dash = bool(allow_dup_raw) if allow_dup_raw is not None else False
                event_at_display = format_event_at_display(event_at_raw)
                event_at_input_value = _event_at_input_local_value(event_at_raw)
        except: pass

    # 사전 참여 명단 (화이트리스트) 및 가나다순 정렬
    # - 중복 허용: 현재 참여자 + 기당첨자 모두 체크
    # - 중복 비허용: 현재 참여자만 체크(기당첨자는 체크 해제)
    if HAS_MONITOR:
        won_names = [w.strip() for w in winners.split(',') if w.strip()] if winners else []
        p_names = [p[0] for p in p_list]
        all_confirmed_names = set(p_names)
        if allow_duplicates_dash:
            all_confirmed_names |= set(won_names)

        allowed_dict = get_allowed_list(active_url) if active_url else get_allowed_list()
        allowed_info = []
        for name, tickets in allowed_dict.items():
            name_norm = unicodedata.normalize('NFC', name.strip())
            is_confirmed = name_norm in all_confirmed_names
            allowed_info.append({
                'name': name_norm,
                'tickets': tickets,
                'is_confirmed': is_confirmed
            })
        # 정렬: 확정자 우선, 그 다음 가나다순
        allowed_info.sort(key=lambda x: (not x['is_confirmed'], _ko_first_name_key(x['name'])))
        if not allowed_info and p_list:
            for p in p_list:
                name_norm = unicodedata.normalize("NFC", str(p[0]).strip())
                tickets = int(p[1]) if len(p) > 1 else 1
                is_confirmed = name_norm in all_confirmed_names
                allowed_info.append(
                    {
                        "name": name_norm,
                        "tickets": tickets,
                        "is_confirmed": is_confirmed,
                    }
                )
            allowed_info.sort(
                key=lambda x: (not x["is_confirmed"], _ko_first_name_key(x["name"]))
            )
    else:
        allowed_info = []

    # 전체 체크 상태 목록 (실시간 UI 동기화용)
    all_confirmed_set = set(confirmed_names)
    if HAS_MONITOR and allow_duplicates_dash:
        all_confirmed_set |= set(won_names)
    supabase_rt_url = os.getenv('SUPABASE_URL', '') or ''
    supabase_rt_anon_key = os.getenv('SUPABASE_ANON_KEY', '') or ''

    return render_template('index.html',
                           participants=p_list,
                           confirmed_names=list(all_confirmed_set), # ✅ 표시용
                           colors=p_colors,
                           user=None,
                           is_guest=True,
                           title=title,
                           prizes=prizes,
                           memo=memo,
                           winners=winners,
                           current_url=active_url,
                           event_at_display=event_at_display,
                           event_at_input_value=event_at_input_value,
                           allowed_info=allowed_info,
                           allowed_list_text="",
                           allow_duplicates_dash=allow_duplicates_dash,
                           supabase_rt_url=supabase_rt_url,
                           supabase_rt_anon_key=supabase_rt_anon_key,
                           roulette_closed_message=roulette_event_closed.get(active_url))
    
def _roulette_list_from_allowed_dict(allowed_dict, winners_str, allow_duplicates):
    """사전 명단(dict)에서 룰렛용 (이름, 티켓수, created_at) 리스트를 만듭니다."""
    won_names = []
    if winners_str:
        won_names = [unicodedata.normalize('NFC', w.strip()) for w in winners_str.split(',') if w.strip()]
    policy_allow_duplicates = (allow_duplicates != False)
    participants = []
    for name, tickets in allowed_dict.items():
        name_norm = unicodedata.normalize('NFC', str(name).strip())
        if not policy_allow_duplicates and name_norm in won_names:
            continue
        try:
            t = int(tickets)
        except (TypeError, ValueError):
            t = 1
        participants.append((name_norm, t, None))
    participants.sort(key=lambda x: _ko_first_name_key(x[0]))
    if len(participants) > 100:
        participants = [(f"{i+1}", p[1], p[2]) for i, p in enumerate(participants)]
    return participants


# ----- 참가자 로딩 함수 (가나다순 정렬 추가) -----
def load_participants(filename="participants.txt", active_event_id=None):
    """
    참가자 데이터를 로드합니다. 
    1. 활성화된 이벤트가 있으면 DB에서 가져옵니다 (Render 대응).
    2. 확정 참가자(participants 테이블)가 비어 있어도 사전 명단(allowed_list)이 있으면 그걸 룰렛 풀로 사용합니다.
       (댓글 수집 없이 명단만 올린 경우 원판·추첨이 동작하도록)
    3. DB에 데이터가 없거나 활성화된 이벤트가 없으면 빈 목록을 반환합니다.
    """
    if HAS_MONITOR:
        try:
            active_url = normalize_event_id(active_event_id) if active_event_id else get_active_url()
            if not active_url:
                # 배포/재시작 직후 활성 이벤트가 아직 없을 수 있어 1회 보정
                _ensure_default_active_event()
                active_url = get_active_url()
            if active_url:
                participants_dict, _, _, _, _, _, winners_str, allow_duplicates, _, _ = db.get_data(active_url)
                if participants_dict:
                    # [추가] 중복 당첨 비허용 시 기존 당첨자 명단 제외
                    won_names = []
                    if winners_str:
                        won_names = [w.strip() for w in winners_str.split(',') if w.strip()]
                    
                    policy_allow_duplicates = (allow_duplicates != False)
                    
                    # 룰렛 엔진용 리스트 형식으로 변환: (이름, 횟수, 시간)
                    participants = []
                    for name, v in participants_dict.items():
                        if not policy_allow_duplicates and name in won_names:
                            print(f"DEBUG: [Filter] Skipping previous winner: {name}")
                            continue

                        count = _normalize_ticket_count(v)
                        created_at = v[1] if isinstance(v, (tuple, list)) and len(v) > 1 else None
                        participants.append((name, count, created_at))
                    
                    participants.sort(key=lambda x: _ko_first_name_key(x[0]))
                    
                    # 별명 100개 이상이면 숫자로 대체 (기존 로직 유지)
                    if len(participants) > 100:
                        participants = [(f"{i+1}", p[1], p[2]) for i, p in enumerate(participants)]
                    
                    print(f"DEBUG: Loaded {len(participants)} participants from DB for {active_url}")
                    return participants

                allowed_dict = get_allowed_list(active_url)
                if allowed_dict:
                    participants = _roulette_list_from_allowed_dict(allowed_dict, winners_str, allow_duplicates)
                    print(f"DEBUG: Loaded {len(participants)} participants from allowed_list fallback for {active_url}")
                    return participants
        except Exception as e:
            print(f"DEBUG: Error loading participants from DB: {e}")

    return []

# 전역 변수 제거 (함수 내에서 동적 로드)
# participants = load_participants()
# ...

@app.route('/')
def index():
    if HAS_MONITOR:
        _ensure_default_active_event()
    active_url = get_active_url() if HAS_MONITOR else None
    p_data = load_participants(active_event_id=active_url)
    p_list = p_data if p_data else []
    confirmed_names = [unicodedata.normalize('NFC', p[0].strip()) for p in p_list] if p_list else []
    
    # colors 리스트 생성
    p_colors = []
    for i in range(len(p_list)):
        h = i * 360 / len(p_list) if p_list else 0
        p_colors.append(f"hsl({h}, 70%, 50%)")
        
    # 가장 최근에 업데이트된 글 정보 가져오기
    title = None
    prizes = None
    memo = None
    winners = None
    event_at_display = ""
    event_at_input_value = ""
    allow_duplicates_dash = False
    if HAS_MONITOR:
        try:
            active_url = active_url or get_active_url()
            if active_url:
                _, _, _, title, prizes, memo, winners, adash, _, event_at_raw = db.get_data(active_url)
                allow_duplicates_dash = bool(adash) if adash is not None else False
                event_at_display = format_event_at_display(event_at_raw)
                event_at_input_value = _event_at_input_local_value(event_at_raw)
        except: pass

    # 사전 참여 명단 (화이트리스트) 및 가나다순 정렬
    # - 중복 허용: 현재 참여자 + 기당첨자 모두 체크
    # - 중복 비허용: 현재 참여자만 체크(기당첨자는 체크 해제)
    if HAS_MONITOR:
        won_names = [w.strip() for w in winners.split(',') if w.strip()] if winners else []
        p_names = [p[0] for p in p_list]
        all_confirmed_names = set(p_names)
        if allow_duplicates_dash:
            all_confirmed_names |= set(won_names)

        allowed_dict = get_allowed_list(active_url) if active_url else get_allowed_list()
        allowed_info = []
        for name, tickets in allowed_dict.items():
            name_norm = unicodedata.normalize('NFC', name.strip())
            is_confirmed = name_norm in all_confirmed_names
            allowed_info.append({
                'name': name_norm,
                'tickets': tickets,
                'is_confirmed': is_confirmed
            })
        # 정렬: 확정자 우선, 그 다음 가나다순
        allowed_info.sort(key=lambda x: (not x['is_confirmed'], _ko_first_name_key(x['name'])))
        # posts.allowed_list 가 비어 있어도 participants 테이블에만 명단이 있을 수 있음
        if not allowed_info and p_list:
            for p in p_list:
                name_norm = unicodedata.normalize("NFC", str(p[0]).strip())
                tickets = int(p[1]) if len(p) > 1 else 1
                is_confirmed = name_norm in all_confirmed_names
                allowed_info.append(
                    {
                        "name": name_norm,
                        "tickets": tickets,
                        "is_confirmed": is_confirmed,
                    }
                )
            allowed_info.sort(
                key=lambda x: (not x["is_confirmed"], _ko_first_name_key(x["name"]))
            )
    else:
        allowed_info = []

    # 전체 체크 상태 목록 (실시간 UI 동기화용)
    all_confirmed_set = set(confirmed_names)
    if HAS_MONITOR and allow_duplicates_dash:
        all_confirmed_set |= set(won_names)

    allowed_list_text = ""
    if active_url:
        try:
            _, _, _, _, _, _, _, _, alt, _ = db.get_data(active_url)
            allowed_list_text = alt or ""
        except Exception:
            pass

    if current_user.is_authenticated:
        supabase_rt_url = os.getenv('SUPABASE_URL', '') or ''
        supabase_rt_anon_key = os.getenv('SUPABASE_ANON_KEY', '') or ''
        return render_template('index.html',
                             participants=p_list,
                             confirmed_names=list(all_confirmed_set), # ✅ 표시용
                             colors=p_colors,
                             user=current_user,
                             title=title,
                             prizes=prizes,
                             memo=memo,
                             winners=winners,
                             current_url=active_url,
                             event_at_display=event_at_display,
                             event_at_input_value=event_at_input_value,
                             allowed_info=allowed_info,
                             allowed_list_text=allowed_list_text,
                             allow_duplicates_dash=allow_duplicates_dash,
                             supabase_rt_url=supabase_rt_url,
                             supabase_rt_anon_key=supabase_rt_anon_key,
                             roulette_closed_message=roulette_event_closed.get(active_url))
    else:
        return render_template('welcome.html')

# ----- 회전 게임 로직 -----
games = {}
last_winner_confirm_times = {} # [추가] 당첨자 확정 후 10초 대기를 위한 타임스탬프 저장
# 이벤트 id → 운영자가 "룰렛 종료"로 고정한 안내 문구 (해당 이벤트에서 추가 추첨 비허용)
roulette_event_closed: dict = {}

DEFAULT_ROULETTE_CLOSED_MESSAGE = "오늘 룰렛 이벤트 종료! 감사합니다"

@socketio.on('connect')
def handle_connect():
    print("Client connected:", request.sid)


@app.route("/monitor_page")
def monitor_page_redirect():
    """구 모니터 페이지 URL은 메인으로 유도 (북마크 호환)."""
    return redirect(url_for("index"))


@socketio.on('disconnect')
def handle_disconnect():
    print("Client disconnected:", request.sid)

@socketio.on('reset_game')
def handle_reset_game():
    print("Game reset request received - clearing all game states")
    global games
    # 모든 게임 상태 초기화
    games.clear()
    socketio.emit('game_reset_complete', namespace='/')


@socketio.on('end_roulette_event')
def handle_end_roulette_event(data=None):
    """운영자: 현장에서 룰렛 추첨을 완전히 종료 (원판 안내 + 시작/+1분 차단)."""
    if not current_user.is_authenticated:
        return
    payload = data if isinstance(data, dict) else {}
    active_url = get_active_url()
    if not active_url:
        socketio.emit(
            'error',
            {'message': '활성 이벤트가 없습니다. 히스토리에서 이벤트를 선택해 주세요.'},
            namespace='/',
            to=request.sid,
        )
        return
    msg = (payload.get('message') or '').strip()
    if not msg:
        msg = DEFAULT_ROULETTE_CLOSED_MESSAGE
    roulette_event_closed[active_url] = msg
    global games
    games.clear()
    # game_reset_complete 는 보내지 않음(잠깐 시작 버튼이 풀리는 깜빡임 방지). 클라이언트가 roulette_event_ended 로 UI 정리.
    socketio.emit(
        'roulette_event_ended',
        {'message': msg, 'event_id': active_url},
        namespace='/',
    )
    print(f"DEBUG: [end_roulette_event] closed for {active_url}")


@socketio.on('cancel_roulette_event')
def handle_cancel_roulette_event(data=None):
    """운영자: 현장 종료 안내를 걷어 다시 룰렛 운영 가능 상태로."""
    if not current_user.is_authenticated:
        return
    active_url = get_active_url()
    if not active_url:
        socketio.emit(
            'error',
            {'message': '활성 이벤트가 없습니다. 히스토리에서 이벤트를 선택해 주세요.'},
            namespace='/',
            to=request.sid,
        )
        return
    if active_url not in roulette_event_closed:
        socketio.emit(
            'error',
            {'message': '현재 현장 종료 상태가 아닙니다.'},
            namespace='/',
            to=request.sid,
        )
        return
    del roulette_event_closed[active_url]
    socketio.emit(
        'roulette_event_resumed',
        {'event_id': active_url},
        namespace='/',
    )
    print(f"DEBUG: [cancel_roulette_event] resumed for {active_url}")


@socketio.on('start_rotation')
def handle_start_rotation(data):
    """
    data = { time: "HH:MM:SS" } (UTC 기준)
    """
    print("Received start_rotation with data:", data)
    user_id = current_user.id if current_user.is_authenticated else 'anonymous'
    
    # [추가] 당첨자 확정 후 10초 대기 로직 (서버 사이드 방어)
    active_url = get_active_url()
    if active_url and active_url in roulette_event_closed:
        socketio.emit(
            'error',
            {'message': '이 이벤트는 운영자에 의해 종료되었습니다. 룰렛을 다시 돌릴 수 없습니다.'},
            namespace='/',
            to=request.sid,
        )
        return
    if active_url and active_url in last_winner_confirm_times:
        elapsed = time.time() - last_winner_confirm_times[active_url]
        if elapsed < 10:
            remaining = int(10 - elapsed)
            print(f"DEBUG: Cooldown active for {active_url}. {remaining}s left.")
            socketio.emit('error', {'message': f'당첨자 발표 후 재설정까지 대기 시간이 필요합니다. ({remaining}초 남음)'}, namespace='/', to=request.sid)
            return
    
    # 기존 게임 정보 초기화 또는 신규 생성
    if user_id not in games:
        games[user_id] = {
            'running': False,
            'target_time': None,
            'current_angle': 0.0,
            'final_winner': None,
            'winner_announced': False,
            'confirmed': False 
        }
    
    # [수정] 매 스핀마다 상태를 확실히 초기화 (기존에는 if문 안에 있어 버그 발생)
    game = games[user_id]
    game['winner_announced'] = False
    game['confirmed'] = False
    game['final_winner'] = None
    game['running'] = False

    now = datetime.datetime.utcnow()
    t_str = data['time']
    target_today_str = now.strftime('%Y-%m-%d') + ' ' + t_str
    try:
        game['target_time'] = datetime.datetime.strptime(target_today_str, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        print("DEBUG: Invalid time format:", t_str)
        socketio.emit('error', {'message': '시간 형식이 잘못되었습니다.'}, namespace='/', to=request.sid)
        return

    print("DEBUG: now =", now, "target_time =", game['target_time'])
    if game['target_time'] <= now:
        socketio.emit('error', {'message': '미래 시각을 입력해주세요.'}, namespace='/', to=request.sid)
        return

    # 지속 시간 계산
    duration = (game['target_time'] - now).total_seconds()

    # 총 지속시간도 저장 (추가)
    game['total_duration'] = duration
    
    # 최종 회전 각도 미리 결정 (720~1440도 사이 랜덤)
    # 정확한 계산을 위해 소수점 자리까지 유지
    final_angle = random.uniform(720, 1440)
    
    # 화살표는 12시 방향(0도)에 고정됨
    # 전체 회전 각도 저장
    game['current_angle'] = final_angle
    
    # 화살표가 가리키는 실제 각도 계산 (0도가 12시 방향)
    # 원판이 시계 방향으로 회전하면, 화살표의 상대적 위치는 반시계 방향으로 이동하는 효과
    # 정확한 모듈로 연산 적용 후 정규화
    relative_angle = (360 - (final_angle % 360)) % 360
    
    print(f"DEBUG: 최종 회전 각도: {final_angle:.2f}°, 상대 각도: {relative_angle:.2f}°")
    
    # 현재 참가자 데이터 로드
    p_data = load_participants()
    p_list = p_data if p_data else []
    
    if not p_list:
        print("DEBUG: No participants available for rotation.")
        socketio.emit('error', {'message': '참여자가 없습니다. 댓글을 확인해주세요.'}, namespace='/', to=request.sid)
        return

    # 정확한 당첨자 계산 (화살표가 가리키는 섹터의 참가자)
    winner = calculate_winner_at_angle(relative_angle, p_list)
    game['final_winner'] = winner
    round_id = f"{active_url or 'noevent'}:{int(time.time() * 1000)}:{random.randint(1000, 9999)}"
    game['round_id'] = round_id
    
    # 게임 상태 업데이트
    game['running'] = True

    # 이 부분 추가: 게임 정보를 'global_game' 키에 복사
    games['global_game'] = game.copy()
    
    # 클라이언트에게 모든 정보를 한 번에 전송
    socketio.emit('start_game', {
        'duration': duration,
        'finalAngle': final_angle,
        'winner': winner,
        'round_id': round_id,
        'participants': p_list # 정확한 명단 동기화
    }, namespace='/')
        
    # 모든 클라이언트에게 게임 상태 정보 브로드캐스트
    socketio.emit('game_status', {
        'target_time': game['target_time'].isoformat(),
        'final_winner': winner
    }, namespace='/')
    
    # 비프음 재생
    socketio.emit('play_beep', namespace='/')
    
    # 종료 시간에 팡파레 및 당첨자 알림을 위한 타이머 설정
    def schedule_end_notification():
        socketio.sleep(duration)
        # 종료 시간에 도달했음을 알리는 로그만 남기고,
        # 당첨자 발표는 클라이언트의 애니메이션 완료 후 confirm_winner에서만 처리
        print(f"DEBUG: 서버에서 예정된 종료 시간에 도달. 예상 당첨자: {winner}")
        game['running'] = False
    
    # 백그라운드 작업으로 타이머 실행
    socketio.start_background_task(schedule_end_notification)

@socketio.on('confirm_winner')
def handle_confirm_winner(data=None):
    """
    애니메이션 완료 후 당첨자 확인 이벤트 처리
    클라이언트에서 애니메이션이 완료된 후 호출됨
    """
    if data is None: data = {}
    req_round_id = (data.get('round_id') or '').strip() if isinstance(data, dict) else ''
    emit_round_id = req_round_id
    user_id = current_user.id if current_user.is_authenticated else 'anonymous'
    
    # 먼저 user_id로 게임 정보 확인
    game_obj = None
    if user_id in games and games[user_id]['final_winner']:
        game_obj = games[user_id]
        winner = game_obj['final_winner']
    # global_game에서도 확인 (추가된 부분)
    elif 'global_game' in games and games['global_game'].get('final_winner'):
        game_obj = games['global_game']
        winner = game_obj['final_winner']
    # 다른 진행 중인 게임이 있는지 확인 (추가된 부분)
    else:
        winner = None
        # 모든 게임 중 마지막으로 시작된 게임 찾기
        latest_game = None
        latest_time = None
        
        for gid, g in games.items():
            if isinstance(g, dict) and g.get('target_time') and g.get('final_winner'):
                if latest_time is None or g['target_time'] > latest_time:
                    latest_time = g['target_time']
                    latest_game = g
        
        if latest_game:
            game_obj = latest_game
            winner = latest_game['final_winner']
            print(f"DEBUG: Found latest game for {user_id}, winner: {winner}")
    
    # 당첨자를 찾았으면 발표
    if winner and winner != "N/A":
        # [중요] 중복 처리 방지 (여러 탭이 열려 있어도 한 번만 처리)
        if game_obj and game_obj.get('confirmed'):
            print(f"DEBUG: 이미 확정 처리된 당첨자입니다: {winner}")
            return
            
        if game_obj:
            game_obj['confirmed'] = True
            # global_game 도 같이 업데이트 (동기화)
            if 'global_game' in games:
                games['global_game']['confirmed'] = True
                
        print(f"DEBUG: 확정된 당첨자: {winner}")
        
        print(f"DEBUG: 당첨자 확정: {winner} (현재 active URL에 저장 시도)")
        
        try:
            raw_key = (data.get('event_id') or data.get('url') or "").strip()
            active_url = normalize_event_id(raw_key) if raw_key else get_active_url()
            print(f"DEBUG: Confirming winner for event id: {active_url}")
            if active_url:
                if req_round_id and _is_already_processed_round(req_round_id):
                    print(f"DEBUG: Duplicate round confirm suppressed: {req_round_id}")
                    return
                if _should_skip_duplicate_confirm(active_url, winner):
                    print(f"DEBUG: Duplicate confirm suppressed for {active_url} / {winner}")
                    return
                # 1. 현재 데이터 모두 가져오기 (덮어쓰기 방지)
                dataset = db.get_data(active_url)
                if not dataset:
                    print(f"WARNING: No dataset for {active_url}. Skipping confirmation.")
                    socketio.emit('error', {'message': '이벤트 데이터를 찾을 수 없습니다.'}, namespace='/', to=request.sid)
                    return

                participants, last_id, all_commenters, title, prizes, memo, current_winners_str, allow_duplicates, _, _ = dataset
                participants = dict(participants) if participants else {}

                # 확정 참가자 행이 비어 있어도 사전 명단만 있으면 동일 풀로 복원 (원판·추첨과 일치)
                if not participants:
                    allowed_dict = get_allowed_list(active_url)
                    if allowed_dict:
                        for name, tickets in allowed_dict.items():
                            name_norm = unicodedata.normalize('NFC', str(name).strip())
                            try:
                                t = int(tickets)
                            except (TypeError, ValueError):
                                t = 1
                            participants[name_norm] = (t, None)
                        won_prev = []
                        if current_winners_str:
                            won_prev = [unicodedata.normalize('NFC', w.strip()) for w in current_winners_str.split(',') if w.strip()]
                        if allow_duplicates is False:
                            for wn in won_prev:
                                participants.pop(wn, None)
                        print(f"DEBUG: Hydrated {len(participants)} participants from allowed_list for confirm_winner")

                if not participants:
                    print(f"WARNING: No participants found for {active_url}. Skipping confirmation.")
                    socketio.emit('error', {'message': '이벤트 데이터를 찾을 수 없습니다.'}, namespace='/', to=request.sid)
                    return

                print(f"DEBUG: Policy - Allow Duplicates: {allow_duplicates}, Participants count: {len(participants)}")
                
                current_winners = []
                if current_winners_str:
                    current_winners = current_winners_str.split(',')
                
                # 2. 새 당첨자 추가 (중복 허용 여부와 무관하게 당첨 내역에는 추가)
                current_winners.append(winner)
                new_winners_str = ','.join(current_winners)
                
                # [추가] 중복 당첨 비허용 시 참가자 명단에서 제거
                if not allow_duplicates:
                    if winner in participants:
                        del participants[winner]
                        print(f"DEBUG: Removed winner '{winner}' from participants (No Duplicates Policy)")
                        # [중요] DB에서도 즉시 삭제하여 실시간 동기화 시 다시 나타나지 않게 함
                        db.delete_participant(active_url, winner)
                
                # 3. 저장 (기존 데이터 보존하며 winners 및 participants 업데이트)
                db.save_data(active_url, participants, last_id if last_id else '', 
                             title=title, prizes=prizes, memo=memo, 
                             winners=new_winners_str, allow_duplicates=allow_duplicates)
                    
                print(f"DEBUG: Saved winners to DB: {new_winners_str}")

                # 4. 실시간 설정 브로드캐스트 (당첨자 명단 및 모든 설정 갱신을 위해)
                # event_id/url 은 JSON에서 숫자로 직렬화되면 클라이언트 문자열 키와 !== 로 새 이벤트 오인 → 강제 새로고침 되므로 문자열로 통일
                _ev_key = str(active_url) if active_url is not None else ''
                socketio.emit('update_event_settings', {
                    'event_id': _ev_key,
                    'url': _ev_key,
                    'title': title,
                    'prizes': prizes,
                    'memo': memo,
                    'winners': new_winners_str
                }, namespace='/')
                
                # 4. 브로드캐스트 전 메모리 상태 업데이트 (monitor_view 와 공유)
                st = event_states.setdefault(active_url, {})
                st['winners'] = new_winners_str
                st['participants'] = dict(participants or {})
                st['title'] = title or ''
                st['prizes'] = prizes or ''
                st['memo'] = memo or ''
                st['allow_duplicates'] = bool(allow_duplicates)
                if not allow_duplicates:
                    # 이미 당첨된 사람을 seen_ids 에서도 관리하여 재진입 방지 (선택 사항)
                    # st.setdefault('seen_ids', set()).add(winner)
                    pass

                # 5. 브로드캐스트
                socketio.emit('update_event_settings', {
                    'winners': new_winners_str,
                    'prizes': prizes
                }, namespace='/')
                
                # [추가] 참가자 명단 변경 사항 브로드캐스트 (실시간 UI 갱신용)
                # 중복 비허용 시 제거된 명단을 전송하고, 중복 허용 시에도 당첨자 배지 상태 동기화를 위해 전송
                p_list_for_roulette = [(name, _normalize_ticket_count(v)) for name, v in participants.items()]
                p_list_for_roulette.sort(key=lambda x: _ko_first_name_key(x[0]))
                
                # [중요] 전체 활동 목록(full_commenter_list)을 DB에서 가져와서 배지 정보 추가
                allowed_list = get_allowed_list(active_url)
                full_commenter_data = []
                for c in all_commenters:
                    author = c.get('name') if isinstance(c, dict) else c
                    is_whitelisted = author in allowed_list
                    full_commenter_data.append({
                        'name': author,
                        'is_whitelisted': is_whitelisted,
                        'tickets': allowed_list.get(author, 1) if is_whitelisted else 0
                    })
                
                socketio.emit('update_participants', {
                    'participants': p_list_for_roulette,
                    # 중복 비허용이면 현재 참여자만 체크, 허용이면 기당첨자도 체크
                    'confirmed_all': (
                        list(set(participants.keys()) | set(current_winners))
                        if (allow_duplicates != False) else list(set(participants.keys()))
                    ),
                    'full_commenter_list': full_commenter_data,
                    'total_comments': len(all_commenters),
                    # 클라이언트 키 비교/동기화는 실제 이벤트 키를 사용해야 한다.
                    'event_id': str(active_url) if active_url is not None else ''
                }, namespace='/')

        except Exception as e:
            print(f"DEBUG: Failed to save winner to DB: {e}")
        if (not emit_round_id) and game_obj:
            emit_round_id = str(game_obj.get('round_id') or '')
        # 당첨자 정보 전송
        socketio.emit('update_winner', {'winner': winner, 'round_id': emit_round_id}, namespace='/')
        socketio.emit('play_fanfare', {'round_id': emit_round_id}, namespace='/')

        # [추가] 당첨자 확정 타임스탬프 저장 (10초 대기 로직용)
        try:
            raw_key2 = (data.get('event_id') or data.get('url') or "").strip()
            active_url = normalize_event_id(raw_key2) if raw_key2 else get_active_url()
            if active_url:
                last_winner_confirm_times[active_url] = time.time()
                print(f"DEBUG: Recorded last_winner_confirm_time for {active_url}")
        except: pass
    else:
        # 게임 정보가 없거나 당첨자가 설정되지 않은 경우 오류 메시지 전송
        print("ERROR: 당첨자 정보를 찾을 수 없음")
        socketio.emit('error', {'message': '당첨자 정보를 찾을 수 없습니다.'}, namespace='/', to=request.sid)

@socketio.on('request_game_status')
def handle_request_game_status():
    """
    클라이언트(특히 게스트)가 접속했을 때 현재 게임 상태 정보를 요청
    """
    print("게임 상태 요청 수신")
    user_id = current_user.id if current_user.is_authenticated else 'anonymous'
    
    # 현재 진행 중인 게임이 있는지 확인 (global_game이나 다른 게임)
    active_game = None
    
    if 'global_game' in games and games['global_game'].get('target_time'):
        active_game = games['global_game']
    elif user_id in games and games[user_id].get('target_time'):
        active_game = games[user_id]
    else:
        # 다른 활성 게임 찾기
        for gid, game in games.items():
            if game.get('running') and game.get('target_time'):
                active_game = game
                break
    
    # 현재 활성 이벤트 데이터 가져오기 (게스트 동기화용)
    active_event_data = {}
    if HAS_MONITOR:
        try:
            active_url = get_active_url()
            if active_url:
                participants_dict, last_id, all_commenter_list, title, prizes, memo, winners, allow_duplicates, _, _ = db.get_data(
                    active_url, include_commenters=False
                )
                # Supabase 일시 오류로 빈 데이터가 내려오면 마지막 정상 스냅샷으로 폴백
                cached = event_states.get(active_url) if active_url else None
                if _is_effectively_empty_event_fetch(participants_dict, title, prizes, memo, winners, None) and cached:
                    print(f"DEBUG: [game_status] using cached snapshot for {active_url}")
                    participants_dict = dict(cached.get('participants') or {})
                    title = cached.get('title', title)
                    prizes = cached.get('prizes', prizes)
                    memo = cached.get('memo', memo)
                    winners = cached.get('winners', winners)
                    allow_duplicates = cached.get('allow_duplicates', allow_duplicates)

                p_list_for_roulette = []
                if participants_dict:
                    p_list_for_roulette = _roulette_pairs_from_participants_dict(
                        participants_dict, winners, allow_duplicates
                    )
                else:
                    # 저장 직후 participants 테이블이 비어도 allowed_list로 즉시 복원
                    allowed_dict = get_allowed_list(active_url)
                    if allowed_dict:
                        restored = _roulette_list_from_allowed_dict(allowed_dict, winners, allow_duplicates)
                        p_list_for_roulette = [(name, int(count)) for name, count, _ in restored]
                        p_list_for_roulette.sort(key=lambda x: _ko_first_name_key(x[0]))

                p_names = [name for name, _ in p_list_for_roulette]
                won_names = [w.strip() for w in winners.split(',') if w.strip()] if winners else []
                # 중복 비허용이면 현재 참여자만 체크, 허용이면 기당첨자도 체크
                confirmed_all = (
                    list(set(p_names) | set(won_names))
                    if (allow_duplicates != False) else list(set(p_names))
                )

                # 명단 UI는 항상 "전체 사전 명단"을 우선 사용(중복비허용 시 당첨자를 체크 해제로만 표현)
                participant_display_list = []
                allowed_dict_ui = get_allowed_list(active_url)
                if allowed_dict_ui:
                    for name, tickets in allowed_dict_ui.items():
                        nm = unicodedata.normalize("NFC", str(name).strip())
                        try:
                            t = int(tickets)
                        except (TypeError, ValueError):
                            t = 1
                        participant_display_list.append((nm, t))
                    participant_display_list.sort(
                        key=lambda x: _ko_first_name_key(x[0])
                    )
                elif participants_dict:
                    # 하위 호환: allowed_list 가 없을 때만 participants 로 표시
                    for name, v in participants_dict.items():
                        participant_display_list.append(
                            (name, _normalize_ticket_count(v))
                        )
                    participant_display_list.sort(
                        key=lambda x: _ko_first_name_key(x[0])
                    )
                
                active_event_data = {
                    'title': title,
                    'prizes': prizes,
                    'memo': memo,
                    'winners': winners,
                    'allow_duplicates': bool(allow_duplicates) if allow_duplicates is not None else False,
                    'participants': p_list_for_roulette,
                    'participant_display_list': participant_display_list,
                    'confirmed_all': confirmed_all,
                    'current_url': active_url,
                    'current_event_id': active_url,
                    'roulette_closed_message': roulette_event_closed.get(active_url),
                }
                # 다음 요청에서 폴백할 수 있도록 마지막 정상 스냅샷 갱신
                st = event_states.setdefault(active_url, {})
                st['title'] = title or ''
                st['prizes'] = prizes or ''
                st['memo'] = memo or ''
                st['winners'] = winners or ''
                st['allow_duplicates'] = bool(allow_duplicates)
                st['participants'] = dict(participants_dict or {})
        except Exception as e:
            print(f"DEBUG: Error fetching initial sync data: {e}")

    if active_game:
        now = datetime.datetime.utcnow()
        target_time = active_game['target_time']
        
        # 게임이 아직 진행 중인지 확인
        if target_time > now:
            # 남은 시간 계산
            duration_left = (target_time - now).total_seconds()
            
            # 클라이언트에게 게임 상태, 회전 정보, 남은 시간 및 이벤트 데이터 전송
            socketio.emit(
                'game_status',
                {
                    'target_time': target_time.isoformat(),
                    'final_winner': active_game.get('final_winner'),
                    'is_running': active_game.get('running', False),
                    'finalAngle': active_game.get('current_angle', 0),
                    'duration_left': duration_left,
                    'total_duration': active_game.get('total_duration', 0),
                    'event_data': active_event_data,
                },
                namespace='/',
                to=request.sid,
            )
            
            # 진행 중인 게임이 있으므로 start_game 이벤트도 전송
            socketio.emit('start_game', {
                'duration': duration_left,
                'finalAngle': active_game.get('current_angle', 0),
                'winner': active_game.get('final_winner'),
                'round_id': active_game.get('round_id', '')
            }, namespace='/', to=request.sid)  # 요청한 클라이언트에게만 전송
            
            print(f"진행 중인 게임 정보 전송: 남은 시간 {duration_left:.2f}초")
            return
        else:
            # 게임이 이미 종료됨 - 결과 및 이벤트 데이터 전송
            socketio.emit(
                'game_status',
                {
                    'target_time': target_time.isoformat(),
                    'final_winner': active_game.get('final_winner'),
                    'is_running': False,
                    'event_data': active_event_data,
                },
                namespace='/',
                to=request.sid,
            )
            print("이미 종료된 게임 정보 전송")
            return
    
    # 진행 중인 게임이 없는 경우에도 이벤트 데이터는 보냄 (요청한 클라이언트만)
    socketio.emit(
        'game_status',
        {'event_data': active_event_data},
        namespace='/',
        to=request.sid,
    )
    print("진행 중인 게임 없음 (동기화 데이터 전송)")
        
def calculate_winner_at_angle(angle, participants_list):
    """
    특정 각도에서의 당첨자를 계산하는 함수
    angle: 0도는 12시 방향, 시계방향으로 증가
    """
    if not participants_list:
        return "N/A"
        
    names_local = [p[0] for p in participants_list]
    counts_local = [p[1] for p in participants_list]
    total_count_local = sum(counts_local)
    
    if total_count_local == 0:
        return names_local[0] if names_local else "N/A"

    print(f"DEBUG: 당첨자 계산에 사용되는 각도: {angle:.2f}°")
    
    # 각 섹터 배치를 계산하기 위한 설정
    cumulative_angle = 0.0
    
    # 각 참가자의 세그먼트 정보를 먼저 계산하고 저장
    segments = []
    
    for i, (name, cnt) in enumerate(zip(names_local, counts_local)):
        portion = cnt / total_count_local
        sector_size = portion * 360.0
        sector_start = cumulative_angle
        sector_end = cumulative_angle + sector_size
        
        # 세그먼트 정보 저장
        segments.append({
            'name': name,
            'start': sector_start,
            'end': sector_end,
            'size': sector_size
        })
        
        # 디버깅 정보 출력
        print(f"DEBUG: Sector {i}: {name}, {sector_start:.2f}° ~ {sector_end:.2f}°, size: {sector_size:.2f}°")
        
        cumulative_angle += sector_size
    
    # 입력 각도를 0-360 범위로 정규화
    normalized_angle = angle % 360
    
    # 세그먼트별로 검사 - 정확한 범위 검사
    for segment in segments:
        # 화살표가 현재 세그먼트 내에 있는지 확인 (시작 경계도 포함)
        if segment['start'] <= normalized_angle < segment['end']:
            print(f"DEBUG: 당첨자 결정 - {segment['name']} (각도: {normalized_angle:.2f}°)")
            return segment['name']
    
    # 경계 조건 처리 (360도/0도 근처)
    if normalized_angle >= segments[-1]['start'] or normalized_angle < segments[0]['start']:
        print(f"DEBUG: 경계 조건 처리 - 첫 번째 참가자: {names_local[0]} (각도: {normalized_angle:.2f}°)")
        return names_local[0]
    
    # 여기까지 오면 오류 상황
    print(f"ERROR: 당첨자를 결정할 수 없음 (각도: {normalized_angle:.2f}°)")
    return names_local[0]  # 기본값으로 첫 번째 참가자 반환

# [수정됨] 시간 전송 로직 수정 (threading.Thread 제거하고 socketio 백그라운드 태스크 사용)
def send_current_time():
    """현재 시간을 1초마다 클라이언트로 전송하는 함수"""
    while True:
        now = datetime.datetime.now().strftime('%H:%M:%S')
        # print(f"[DEBUG] send_current_time 실행 중 - 현재 시간 전송: {now}") # 로그 너무 많으면 주석 처리
        socketio.emit('update_current_time', {'current_time': now}, namespace='/')
        socketio.sleep(1)  # [중요] time.sleep 대신 socketio.sleep 사용



if __name__ == '__main__':
    # 서버 시작 시 현재 시간 업데이트 쓰레드 실행
    socketio.start_background_task(send_current_time)
    
    port = int(os.environ.get("PORT", 5000))
    # 로컬 개발 환경에서 Werkzeug 서버 실행을 위해 allow_unsafe_werkzeug=True 추가
    socketio.run(app, host='0.0.0.0', port=port, debug=True, allow_unsafe_werkzeug=True)
