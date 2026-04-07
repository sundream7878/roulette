import os
import time
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional

from supabase import create_client, Client
from postgrest.exceptions import APIError

from event_utils import event_at_to_date_prefix_ymd
from dotenv import load_dotenv
import threading

load_dotenv()

# 운영자 저장은 응답 지연을 줄이되, 저장 실패는 명확히 실패로 반환
_BLOCKING_SAVE_ATTEMPTS = 1
_BLOCKING_SAVE_BASE_DELAY = 0.2
_BLOCKING_SAVE_MAX_DELAY = 0.8


def retry_supabase(func):
    """Supabase 작업 재시도 데코레이터"""

    def wrapper(*args, **kwargs):
        max_retries = 3
        base_delay = 1.0
        for i in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if i < max_retries - 1:
                    time.sleep(base_delay * (2 ** i))
                    continue

                try:
                    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    log_file = os.path.join(base_dir, "monitor_debug.log")
                    with open(log_file, "a", encoding="utf-8") as f:
                        f.write(
                            f"[{datetime.now()}] ERROR: [Supabase Sync Failed] {func.__name__}: {str(e)}\n"
                        )
                except Exception:
                    pass
                print(f"DEBUG: [Supabase Sync Skip] {e}")
                return None

    return wrapper


class CommentDatabase:
    """Supabase 전용 저장소. 로컬 SQLite는 사용하지 않습니다. SUPABASE_URL / SUPABASE_KEY 필수."""

    def __init__(self, db_path: str = None):
        # db_path: 과거 시그니처 호환용, 무시됩니다.
        _ = db_path

        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_KEY")

        if not (self.supabase_url and self.supabase_key):
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_KEY must be set in the environment. "
                "Local SQLite fallback has been removed."
            )

        try:
            self.supabase: Client = create_client(
                self.supabase_url.strip("'\""), self.supabase_key.strip("'\"")
            )
        except Exception as e:
            raise RuntimeError(f"Supabase client initialization failed: {e}") from e

        print(f"DEBUG: [Supabase] Storage: {self.supabase_url}")
        self._post_key_col = "id"
        self._participant_fk_col = "event_id"
        self._commenter_fk_col = "event_id"
        self._post_has_id_col = False
        self._post_has_url_col = False
        self._post_has_is_active_col = False
        self._post_opt_cols: List[str] = []
        self._detect_schema_columns()

    def _column_exists(self, table: str, column: str) -> bool:
        try:
            self.supabase.table(table).select(column).limit(1).execute()
            return True
        except APIError as e:
            msg = str(e).lower()
            if "does not exist" in msg and f"{table}.{column}".lower() in msg:
                return False
            return False
        except Exception:
            return False

    def _detect_schema_columns(self) -> None:
        # posts: id(신규) 또는 url(레거시)
        self._post_has_id_col = self._column_exists("posts", "id")
        self._post_has_url_col = self._column_exists("posts", "url")
        if not self._post_has_id_col and self._post_has_url_col:
            self._post_key_col = "url"
        self._post_has_is_active_col = self._column_exists("posts", "is_active")
        self._post_opt_cols = [
            c
            for c in ["event_at", "title", "updated_at", "prizes", "winners", "is_active", "memo", "allow_duplicates"]
            if self._column_exists("posts", c)
        ]
        # participants/commenters: event_id(신규) 또는 url(레거시)
        if not self._column_exists("participants", "event_id") and self._column_exists("participants", "url"):
            self._participant_fk_col = "url"
        if not self._column_exists("commenters", "event_id") and self._column_exists("commenters", "url"):
            self._commenter_fk_col = "url"
        print(
            "DEBUG: [Supabase schema] "
            f"posts.{self._post_key_col}, "
            f"participants.{self._participant_fk_col}, "
            f"commenters.{self._commenter_fk_col}, "
            f"posts_cols={self._post_opt_cols}"
        )

    def _post_select_cols(self, extra: Optional[List[str]] = None) -> str:
        cols: List[str] = []
        if self._post_has_id_col:
            cols.append("id")
        if self._post_has_url_col:
            cols.append("url")
        if not cols:
            cols.append(self._post_key_col)
        if extra:
            cols.extend(extra)
        return ",".join(cols)

    @staticmethod
    def _is_on_conflict_constraint_error(err: Exception) -> bool:
        msg = str(err).lower()
        return (
            "42p10" in msg
            or (
                "on conflict" in msg
                and ("no unique" in msg or "no unique or exclusion constraint" in msg)
            )
        )

    def _save_post_row_resilient(self, event_id: str, post_data: Dict[str, Any]) -> None:
        """ON CONFLICT 제약이 없어도 posts 저장이 실패하지 않도록 폴백."""
        try:
            self.supabase.table("posts").upsert(post_data, on_conflict=self._post_key_col).execute()
            return
        except Exception as e:
            if not self._is_on_conflict_constraint_error(e):
                raise
            print(
                "DEBUG: [posts save fallback] ON CONFLICT unavailable; "
                f"fallback to select+update/insert ({self._post_key_col})"
            )

        # 42P10 폴백:
        # - 고유 제약이 없어 upsert가 실패하면
        # - 동일 키 존재 여부를 먼저 조회한 뒤 update/insert로 대체한다.
        exists = False
        try:
            q = (
                self.supabase.table("posts")
                .select(self._post_key_col)
                .eq(self._post_key_col, event_id)
                .limit(1)
                .execute()
            )
            exists = bool(q.data or [])
        except Exception:
            exists = False

        if exists:
            self.supabase.table("posts").update(post_data).eq(self._post_key_col, event_id).execute()
        else:
            self.supabase.table("posts").insert(post_data).execute()

    def _row_event_key(self, row: Dict[str, Any]) -> Optional[str]:
        if not isinstance(row, dict):
            return None
        rid = row.get("id")
        rurl = row.get("url")
        rk = row.get(self._post_key_col)
        return rid or rurl or rk

    def clear_data(self, event_id: str):
        threading.Thread(target=self._sync_clear_supabase, args=(event_id,), daemon=True).start()

    @retry_supabase
    def _sync_clear_supabase(self, event_id):
        self.supabase.table("participants").delete().eq(self._participant_fk_col, event_id).execute()
        self.supabase.table("commenters").delete().eq(self._commenter_fk_col, event_id).execute()
        self.supabase.table("posts").delete().eq(self._post_key_col, event_id).execute()

    def save_data(
        self,
        event_id: str,
        participants_dict,
        last_comment_id,
        all_commenters=None,
        title=None,
        prizes=None,
        memo=None,
        winners=None,
        allow_duplicates=None,
        allowed_list=None,
        event_at=None,
    ):
        threading.Thread(
            target=self._sync_save_supabase,
            args=(
                event_id,
                participants_dict,
                last_comment_id,
                all_commenters,
                title,
                prizes,
                memo,
                winners,
                allow_duplicates,
                allowed_list,
                event_at,
            ),
            daemon=True,
        ).start()

    def _sync_save_supabase_core(
        self,
        event_id,
        participants_dict,
        last_comment_id,
        all_commenters,
        title,
        prizes,
        memo,
        winners,
        allow_duplicates,
        allowed_list,
        event_at,
        is_active: Optional[bool] = None,
    ):
        post_data = {self._post_key_col: event_id, "updated_at": datetime.now().isoformat()}
        if self._post_has_id_col:
            post_data["id"] = event_id
        if self._post_has_url_col:
            post_data["url"] = event_id
        if is_active is not None and self._post_has_is_active_col:
            post_data["is_active"] = is_active
        if title is not None:
            post_data["title"] = title
        if prizes is not None:
            post_data["prizes"] = prizes
        if memo is not None:
            post_data["memo"] = memo
        if winners is not None:
            post_data["winners"] = winners
        if allowed_list is not None:
            post_data["allowed_list"] = allowed_list
        if allow_duplicates is not None:
            post_data["allow_duplicates"] = allow_duplicates
        if last_comment_id is not None:
            post_data["last_comment_id"] = last_comment_id
        # event_at 저장 정책
        # 1) event_at 컬럼이 있으면 정상 저장
        # 2) 컬럼이 없으면 updated_at에 대체 저장하여 운영자가 수정한 행사 시간이 유지되게 함
        if event_at is not None:
            if "event_at" in self._post_opt_cols:
                post_data["event_at"] = event_at
            elif "updated_at" in self._post_opt_cols:
                post_data["updated_at"] = event_at

        self._save_post_row_resilient(event_id, post_data)

        if participants_dict:
            p_batch = []
            for author, v in participants_dict.items():
                count = v[0] if isinstance(v, (tuple, list)) else v
                p_batch.append({self._participant_fk_col: event_id, "author": author, "count": count})
            for i in range(0, len(p_batch), 500):
                self.supabase.table("participants").upsert(
                    p_batch[i : i + 500], on_conflict=f"{self._participant_fk_col},author"
                ).execute()

        if all_commenters:
            c_batch = []
            for item in all_commenters:
                name = item["name"] if isinstance(item, dict) else item
                c_batch.append({self._commenter_fk_col: event_id, "author": name})
            for i in range(0, len(c_batch), 1000):
                self.supabase.table("commenters").upsert(
                    c_batch[i : i + 1000], on_conflict=f"{self._commenter_fk_col},author"
                ).execute()

    @retry_supabase
    def _sync_save_supabase(
        self,
        event_id,
        participants_dict,
        last_comment_id,
        all_commenters,
        title,
        prizes,
        memo,
        winners,
        allow_duplicates,
        allowed_list,
        event_at,
        is_active: Optional[bool] = None,
    ):
        self._sync_save_supabase_core(
            event_id,
            participants_dict,
            last_comment_id,
            all_commenters,
            title,
            prizes,
            memo,
            winners,
            allow_duplicates,
            allowed_list,
            event_at,
            is_active,
        )
        return True

    def save_data_blocking(
        self,
        event_id: str,
        participants_dict,
        last_comment_id,
        all_commenters=None,
        title=None,
        prizes=None,
        memo=None,
        winners=None,
        allow_duplicates=None,
        allowed_list=None,
        event_at=None,
        is_active: Optional[bool] = None,
    ) -> Tuple[bool, Optional[str]]:
        """운영자 API 등 응답 전에 반드시 커밋해야 할 때 사용. (성공, 마지막 오류 메시지)"""
        last_err: Optional[str] = None
        for attempt in range(_BLOCKING_SAVE_ATTEMPTS):
            try:
                self._sync_save_supabase_core(
                    event_id,
                    participants_dict,
                    last_comment_id,
                    all_commenters,
                    title,
                    prizes,
                    memo,
                    winners,
                    allow_duplicates,
                    allowed_list,
                    event_at,
                    is_active,
                )
                return True, None
            except Exception as e:
                last_err = str(e)
                if attempt < _BLOCKING_SAVE_ATTEMPTS - 1:
                    delay = min(
                        _BLOCKING_SAVE_BASE_DELAY * (2**attempt),
                        _BLOCKING_SAVE_MAX_DELAY,
                    )
                    time.sleep(delay)
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            log_file = os.path.join(base_dir, "monitor_debug.log")
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(
                    f"[{datetime.now()}] ERROR: [Blocking save failed after "
                    f"{_BLOCKING_SAVE_ATTEMPTS} tries] save_data_blocking: {last_err}\n"
                )
        except Exception:
            pass
        print(f"DEBUG: [save_data_blocking] failed: {last_err}")
        return False, last_err

    def get_data(self, event_id: str) -> Tuple[Dict, str, List, str, str, str, str, bool, str, Optional[str]]:
        """Supabase에서 이벤트 데이터 로드."""
        participants = {}
        all_commenters = []
        last_id, title, prizes, memo, winners, allowed_list_str = None, None, None, None, "", None
        allow_duplicates = False
        event_at_str: Optional[str] = None

        try:
            res = self.supabase.table("posts").select("*").eq(self._post_key_col, event_id).execute()
            if not (res.data or []) and self._post_has_id_col and self._post_has_url_col:
                alt_col = "url" if self._post_key_col == "id" else "id"
                res = self.supabase.table("posts").select("*").eq(alt_col, event_id).execute()
            if res.data:
                print(f"DEBUG: [get_data] Fetching data from Supabase for {event_id}")
                post = res.data[0]
                last_id = post.get("last_comment_id")
                title = post.get("title")
                prizes = post.get("prizes")
                memo = post.get("memo")
                winners = post.get("winners", "")
                allow_duplicates = bool(post.get("allow_duplicates", False))
                allowed_list_str = post.get("allowed_list")
                ea = post.get("event_at")
                if ea is not None:
                    event_at_str = str(ea) if not isinstance(ea, str) else ea
                elif post.get("updated_at") is not None:
                    # event_at 미구성 스키마 대응: 화면 표시용 fallback
                    u = post.get("updated_at")
                    event_at_str = str(u) if not isinstance(u, str) else u

                p_res = self.supabase.table("participants").select("*").eq(self._participant_fk_col, event_id).execute()
                for p in p_res.data or []:
                    participants[p["author"]] = (p["count"], p.get("created_at"))

                c_res = self.supabase.table("commenters").select("*").eq(self._commenter_fk_col, event_id).execute()
                for c in c_res.data or []:
                    all_commenters.append(
                        {"name": c["author"], "created_at": c.get("created_at")}
                    )
            else:
                print(f"DEBUG: [get_data] No post in Supabase for {event_id}")
        except Exception as e:
            print(f"DEBUG: [get_data Supabase Error] {e}")

        return (
            participants,
            last_id,
            all_commenters,
            title,
            prizes,
            memo,
            winners,
            allow_duplicates,
            allowed_list_str,
            event_at_str,
        )

    def set_active_event_id(self, event_id: Optional[str]):
        threading.Thread(
            target=self._sync_active_event_supabase, args=(event_id,), daemon=True
        ).start()

    def set_active_url(self, url: Optional[str]):
        """하위 호환: 활성 이벤트 id 설정."""
        self.set_active_event_id(url)

    def _sync_active_event_supabase_core(self, event_id: Optional[str]):
        self.supabase.table("posts").update({"is_active": False}).neq(self._post_key_col, "void").execute()
        if event_id:
            # 중요:
            # 활성화 단계에서는 "기존 이벤트 행의 is_active 플래그만" 갱신한다.
            # 유니크 제약이 없는 프로젝트에서 여기서 insert/upsert를 쓰면
            # 동일 ID의 최소 필드 행이 중복 생성되어(제목/사은품/메모 비어 있음)
            # 이후 조회 시 값이 사라진 것처럼 보일 수 있다.
            self.supabase.table("posts").update({"is_active": True}).eq(self._post_key_col, event_id).execute()
            print(f"DEBUG: [SupabaseSync] Active event id set to: {event_id}")

    @retry_supabase
    def _sync_active_event_supabase(self, event_id: Optional[str]):
        self._sync_active_event_supabase_core(event_id)
        return True

    def set_active_event_id_blocking(self, event_id: Optional[str]) -> Tuple[bool, Optional[str]]:
        last_err: Optional[str] = None
        for attempt in range(_BLOCKING_SAVE_ATTEMPTS):
            try:
                self._sync_active_event_supabase_core(event_id)
                return True, None
            except Exception as e:
                last_err = str(e)
                if attempt < _BLOCKING_SAVE_ATTEMPTS - 1:
                    delay = min(
                        _BLOCKING_SAVE_BASE_DELAY * (2**attempt),
                        _BLOCKING_SAVE_MAX_DELAY,
                    )
                    time.sleep(delay)
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            log_file = os.path.join(base_dir, "monitor_debug.log")
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(
                    f"[{datetime.now()}] ERROR: [Blocking active sync failed after "
                    f"{_BLOCKING_SAVE_ATTEMPTS} tries] set_active_event_id_blocking: {last_err}\n"
                )
        except Exception:
            pass
        print(f"DEBUG: [set_active_event_id_blocking] failed: {last_err}")
        return False, last_err

    def get_active_event_id(self) -> Optional[str]:
        try:
            res = self.supabase.table("posts").select(self._post_select_cols()).eq("is_active", True).limit(1).execute()
            if res.data:
                k = self._row_event_key(res.data[0])
                if k:
                    return k
        except Exception as e:
            print(f"DEBUG: [get_active_event_id Supabase Error] {e}")
        return None

    def get_active_url(self) -> Optional[str]:
        return self.get_active_event_id()

    def get_all_event_ids(self) -> List[str]:
        try:
            res = self.supabase.table("posts").select(self._post_select_cols()).execute()
            out: List[str] = []
            for item in (res.data or []):
                k = self._row_event_key(item)
                if k:
                    out.append(k)
            return out
        except Exception:
            return []

    def get_all_urls(self) -> List[str]:
        return self.get_all_event_ids()

    def delete_participant(self, event_id: str, author: str):
        threading.Thread(
            target=self._sync_delete_p_supabase, args=(event_id, author), daemon=True
        ).start()

    @retry_supabase
    def _sync_delete_p_supabase(self, event_id, author):
        self.supabase.table("participants").delete().eq(self._participant_fk_col, event_id).eq(
            "author", author
        ).execute()

    def update_timestamp(self, event_id: str):
        ts = datetime.now().isoformat()
        try:
            self.supabase.table("posts").update({"updated_at": ts}).eq(self._post_key_col, event_id).execute()
        except Exception as e:
            print(f"DEBUG: [update_timestamp Supabase] {e}")

    def list_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            sel_cols = self._post_select_cols(self._post_opt_cols)
            q = self.supabase.table("posts").select(sel_cols)
            if "updated_at" in self._post_opt_cols:
                q = q.order("updated_at", desc=True)
            res = q.limit(limit).execute()
            rows = res.data or []
            for r in rows:
                rid = self._row_event_key(r)
                r["id"] = rid
                r["url"] = rid
                # 프론트에서 기대하는 필드는 없어도 키를 맞춰준다.
                for c in ["event_at", "title", "updated_at", "prizes", "winners", "is_active", "memo", "allow_duplicates"]:
                    r.setdefault(c, None)
                # event_at 컬럼이 없는 프로젝트에서는 updated_at으로 대체 표시
                if not r.get("event_at") and r.get("updated_at"):
                    r["event_at"] = r.get("updated_at")

            # 서버에서도 ID(YYYYMMDDNN) 최신순으로 고정 정렬
            def _id_num(row: Dict[str, Any]) -> int:
                v = str((row or {}).get("id") or (row or {}).get("url") or "")
                return int(v) if (len(v) == 10 and v.isdigit()) else 0

            rows.sort(key=_id_num, reverse=True)
            return rows
        except Exception as e:
            print(f"DEBUG: [list_events] Supabase error: {e}")
            return []

    def next_event_id(self, event_at_iso: Optional[str] = None) -> str:
        prefix = event_at_to_date_prefix_ymd(event_at_iso)
        max_serial = 0

        def _bump(uid: str) -> None:
            nonlocal max_serial
            if not uid or len(uid) != 10:
                return
            if not uid.startswith(prefix):
                return
            tail = uid[8:]
            if tail.isdigit():
                max_serial = max(max_serial, int(tail))

        try:
            res = self.supabase.table("posts").select(self._post_select_cols()).like(self._post_key_col, f"{prefix}%").execute()
            for row in res.data or []:
                _bump(self._row_event_key(row) or "")
        except Exception as e:
            print(f"DEBUG: [next_event_id] Supabase: {e}")

        return f"{prefix}{(max_serial + 1):02d}"

    def next_event_code(self) -> str:
        return self.next_event_id(None)

    def create_internal_event(
        self, template_key: str = None, event_at_iso: Optional[str] = None
    ) -> Optional[str]:
        title, prizes, memo, winners = "새 룰렛 이벤트", "", "", ""
        allow_duplicates, allowed_list_str = False, None
        template_event_at = event_at_iso
        if template_key:
            _, _, _, t0, pr, m0, w0, ad0, al0, ea0 = self.get_data(template_key)
            title = (t0 or "이벤트").strip() + " (복사)"
            prizes = pr or ""
            memo = m0 or ""
            winners = ""
            allow_duplicates = bool(ad0) if ad0 is not None else False
            allowed_list_str = al0
            if template_event_at is None:
                template_event_at = ea0
        key = self.next_event_id(template_event_at)
        save_event_at = template_event_at or datetime.now().replace(microsecond=0).isoformat()
        ok_save, _ = self.save_data_blocking(
            key,
            None,
            "",
            title=title,
            prizes=prizes,
            memo=memo,
            winners=winners,
            allow_duplicates=allow_duplicates,
            allowed_list=allowed_list_str,
            event_at=save_event_at,
        )
        if not ok_save:
            return None
        ok_act, _ = self.set_active_event_id_blocking(key)
        if not ok_act:
            return None
        return key
