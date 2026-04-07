# -*- coding: utf-8 -*-
"""로그인한 운영자 전용 API (이벤트·명단·사은품 — Supabase/DB)."""
from datetime import datetime
from typing import Optional, Tuple

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required

from event_utils import (
    parse_allowed_list_text,
    allowed_dict_to_lines,
    normalize_event_id,
    parse_participants_csv_bytes,
)

operator_bp = Blueprint("operator", __name__, url_prefix="/api/operator")


def _db():
    return current_app.config["ROULETTE_DB"]


def _operator_storage_error_response(detail: Optional[str]):
    """Supabase 저장 실패 시 사용자용 문구 + 기술 힌트(detail)."""
    d = (detail or "").lower()
    if (
        "getaddrinfo" in d
        or "11001" in d
        or "name or service not known" in d
        or "temporary failure in name resolution" in d
    ):
        msg = (
            "PC가 Supabase 주소를 찾지 못했습니다(DNS/네트워크). "
            "VPN·방화벽을 끄거나 다른 인터넷(핫스팟)으로 바꾼 뒤 다시 시도해 주세요. "
            "계속되면 Windows 네트워크 설정에서 DNS를 8.8.8.8 로 지정해 보세요."
        )
    elif "401" in d or "jwt" in d or "permission denied" in d or "row-level security" in d:
        msg = (
            "Supabase에 쓰기 권한이 없습니다. 서버 .env 의 SUPABASE_KEY 가 "
            "service_role 키인지, RLS 정책이 쓰기를 막고 있지 않은지 확인해 주세요."
        )
    else:
        msg = "저장에 실패했습니다. 인터넷 연결을 확인한 뒤 다시 시도해 주세요."
    payload = {"error": msg}
    if detail:
        payload["detail"] = detail[:400]
    return jsonify(payload), 503


def _register_new_from_operator_form(
    data: dict, keep_title: bool = True
) -> Tuple[Optional[str], Optional[str]]:
    """폼 본문으로 새 ID 발급·저장·활성화 (당첨자 비움). 반환: (event_key, error_message)."""
    parse_allowed_list_text(data.get("allowed_list_text") or "")
    event_at = (data.get("event_at") or "").strip()
    if not event_at:
        event_at = datetime.now().replace(microsecond=0).isoformat()
    key = _db().next_event_id(event_at)
    raw_title = (data.get("title") or "").strip()
    title_to_save = raw_title if keep_title and raw_title else "새 룰렛 이벤트"
    ok, err_detail = _db().save_data_blocking(
        key,
        None,
        "",
        title=title_to_save,
        prizes=data.get("prizes") or "",
        memo=data.get("memo") or "",
        winners="",
        allow_duplicates=bool(data.get("allow_duplicates", False)),
        allowed_list=data.get("allowed_list_text"),
        event_at=event_at,
    )
    if not ok:
        return None, err_detail or "save failed"
    ok_act, err_act = _db().set_active_event_id_blocking(key)
    if not ok_act:
        return None, err_act or "activate failed"
    return key, None


@operator_bp.get("/events")
@login_required
def api_list_events():
    limit = min(int(request.args.get("limit", 40)), 100)
    rows = _db().list_events(limit=limit)
    return jsonify({"events": rows})


@operator_bp.get("/active")
@login_required
def api_active():
    key = _db().get_active_event_id()
    if not key:
        return jsonify({"active": None})
    key = normalize_event_id(key)
    p, _, _, title, prizes, memo, winners, allow_duplicates, allowed_list, event_at = _db().get_data(key)
    return jsonify({
        "active": {
            "event_key": key,
            "title": title or "",
            "prizes": prizes or "",
            "memo": memo or "",
            "winners": winners or "",
            "allow_duplicates": bool(allow_duplicates),
            "allowed_list_text": allowed_list or "",
            "participant_count": len(p) if p else 0,
            "event_at": event_at or "",
        }
    })


@operator_bp.post("/save")
@login_required
def api_save():
    data = request.get_json(silent=True) or {}
    raw = (data.get("event_key") or "").strip()
    key = raw or _db().get_active_event_id()
    if not key:
        # 선택/활성 ID 없음: 「저장」만 눌러도 폼으로 첫 이벤트 자동 생성
        new_key, err_detail = _register_new_from_operator_form(data, keep_title=True)
        if err_detail:
            return _operator_storage_error_response(err_detail)
        return jsonify({"ok": True, "event_key": new_key, "created": True})
    key = normalize_event_id(key.strip())

    _, last_id, _, t0, pr, m0, w0, ad0, al0, ea0 = _db().get_data(key)
    last_id = last_id or ""

    title = data["title"] if "title" in data else t0
    prizes = data["prizes"] if "prizes" in data else pr
    memo = data["memo"] if "memo" in data else m0
    winners = data["winners"] if "winners" in data else (w0 or "")
    allow_duplicates = bool(data["allow_duplicates"]) if "allow_duplicates" in data else bool(ad0)
    allowed_list = data["allowed_list_text"] if "allowed_list_text" in data else al0
    if "event_at" in data:
        raw_ea = data.get("event_at")
        event_at = raw_ea if raw_ea else ea0
    else:
        event_at = ea0

    if allowed_list is not None:
        parse_allowed_list_text(allowed_list or "")

    ok, err_detail = _db().save_data_blocking(
        key,
        None,
        last_id,
        title=title,
        prizes=prizes,
        memo=memo,
        winners=winners,
        allow_duplicates=allow_duplicates,
        allowed_list=allowed_list,
        event_at=event_at,
    )
    if not ok:
        return _operator_storage_error_response(err_detail)
    # 저장 시점에 해당 이벤트를 활성화하여 실제 운영 화면 반영 기준을 일원화
    ok_act, err_act = _db().set_active_event_id_blocking(key)
    if not ok_act:
        return _operator_storage_error_response(err_act)
    return jsonify({"ok": True, "event_key": key, "created": False})


@operator_bp.post("/new")
@login_required
def api_new():
    """(API) 템플릿 복사 빈 이벤트 — UI에서는 주로 register_new 사용."""
    data = request.get_json(silent=True) or {}
    template = data.get("template_key")
    if template and str(template).strip():
        template = normalize_event_id(str(template).strip())
    else:
        template = None
    key = _db().create_internal_event(template_key=template)
    if not key:
        return jsonify(
            {"error": "이벤트 생성에 실패했습니다. 잠시 후 다시 시도해 주세요."}
        ), 503
    return jsonify({"ok": True, "event_key": key})


@operator_bp.post("/register_new")
@login_required
def api_register_new():
    """새 이벤트 작성 준비: DB에 쓰지 않고 다음 ID만 발급. 실제 레코드 생성·활성화는 「저장」(/save)에서만."""
    data = request.get_json(silent=True) or {}
    raw_event_at = (data.get("event_at") or "").strip()
    event_at = raw_event_at or datetime.now().replace(microsecond=0).isoformat()
    key = _db().next_event_id(event_at)
    return jsonify(
        {
            "ok": True,
            "event_key": key,
            "prepared": True,
            "title": "",
            "prizes": "",
            "memo": "",
            "winners": "",
            "allow_duplicates": False,
            "allowed_list_text": "",
            "event_at": event_at,
        }
    )


@operator_bp.post("/reset_winners")
@login_required
def api_reset_winners():
    """선택 이벤트 내용을 복제하되 당첨자만 초기화하여 새 ID로 생성/활성화."""
    data = request.get_json(silent=True) or {}
    raw = (data.get("event_key") or "").strip()
    source_key = normalize_event_id(raw) if raw else _db().get_active_event_id()
    if not source_key:
        return jsonify({"error": "초기화할 event_key 가 없습니다."}), 400

    _, _, _, title, prizes, memo, _, allow_duplicates, allowed_list, event_at = _db().get_data(source_key)
    if allowed_list is not None:
        parse_allowed_list_text(allowed_list or "")

    new_key = _db().next_event_id(event_at)
    ok_save, err_save = _db().save_data_blocking(
        new_key,
        None,
        "",
        title=title or "",
        prizes=prizes or "",
        memo=memo or "",
        winners="",  # 핵심: 당첨자만 초기화
        allow_duplicates=bool(allow_duplicates),
        allowed_list=allowed_list or "",
        event_at=event_at,
    )
    if not ok_save:
        return _operator_storage_error_response(err_save)

    ok_act, err_act = _db().set_active_event_id_blocking(new_key)
    if not ok_act:
        return _operator_storage_error_response(err_act)

    return jsonify(
        {
            "ok": True,
            "source_event_key": source_key,
            "event_key": new_key,
            "title": title or "",
            "prizes": prizes or "",
            "memo": memo or "",
            "winners": "",
            "allow_duplicates": bool(allow_duplicates),
            "allowed_list_text": allowed_list or "",
            "event_at": event_at or "",
            "reset_winners": True,
        }
    )


@operator_bp.post("/delete")
@login_required
def api_delete():
    """선택 이벤트를 DB에서 완전 삭제. 활성 이벤트를 지우면 최신 이벤트를 자동 활성화."""
    data = request.get_json(silent=True) or {}
    raw = (data.get("event_key") or "").strip()
    if not raw:
        return jsonify({"error": "event_key 필요"}), 400
    key = normalize_event_id(raw)

    active_key = _db().get_active_event_id()
    active_key = normalize_event_id(active_key) if active_key else None

    ok_del, err_del = _db().clear_data_blocking(key)
    if not ok_del:
        return _operator_storage_error_response(err_del)

    next_active_key = None
    if active_key == key:
        rows = _db().list_events(limit=1)
        if rows:
            row = rows[0] or {}
            next_active_key = row.get("id") or row.get("url")
            if next_active_key:
                ok_act, err_act = _db().set_active_event_id_blocking(next_active_key)
                if not ok_act:
                    return _operator_storage_error_response(err_act)

    return jsonify(
        {
            "ok": True,
            "deleted_event_key": key,
            "next_active_event_key": next_active_key,
        }
    )


@operator_bp.post("/select")
@login_required
def api_select():
    """히스토리에서 선택 시: 해당 이벤트를 활성화하고 폼용 스냅샷 반환."""
    data = request.get_json(silent=True) or {}
    key = data.get("event_key")
    if not key or not str(key).strip():
        return jsonify({"error": "event_key 필요"}), 400
    key = normalize_event_id(str(key).strip())
    ok, err_detail = _db().set_active_event_id_blocking(key)
    if not ok:
        return _operator_storage_error_response(err_detail)
    participants, _, _, title, prizes, memo, winners, allow_duplicates, allowed_list, event_at = _db().get_data(key)
    return jsonify({
        "ok": True,
        "event_key": key,
        "title": title or "",
        "prizes": prizes or "",
        "memo": memo or "",
        "winners": winners or "",
        "allow_duplicates": bool(allow_duplicates),
        "allowed_list_text": allowed_list or "",
        "event_at": event_at or "",
        "participant_count": len(participants or {}),
    })


@operator_bp.post("/activate")
@login_required
def api_activate():
    data = request.get_json(silent=True) or {}
    key = data.get("event_key")
    if not key:
        return jsonify({"error": "event_key 필요"}), 400
    key = normalize_event_id(key.strip())
    ok, err_detail = _db().set_active_event_id_blocking(key)
    if not ok:
        return _operator_storage_error_response(err_detail)
    return jsonify({"ok": True, "event_key": key})


@operator_bp.post("/upload_csv")
@login_required
def api_upload_csv():
    if "file" not in request.files:
        return jsonify({"error": "file 필드에 CSV를 올려주세요."}), 400
    f = request.files["file"]
    raw = f.read()
    merged = parse_participants_csv_bytes(raw)
    if not merged:
        return jsonify({"error": "CSV에서 유효한 행을 찾지 못했습니다."}), 400
    text = allowed_dict_to_lines(merged)
    return jsonify({"ok": True, "allowed_list_text": text, "count": len(merged)})


@operator_bp.post("/snapshot")
@login_required
def api_snapshot():
    """과거 이벤트 내용을 폼에 채우기 위한 읽기 전용 스냅샷."""
    data = request.get_json(silent=True) or {}
    key = data.get("event_key")
    if not key:
        return jsonify({"error": "event_key 필요"}), 400
    key = normalize_event_id(key.strip())
    _, _, _, title, prizes, memo, winners, allow_duplicates, allowed_list, event_at = _db().get_data(key)
    return jsonify({
        "event_key": key,
        "title": title or "",
        "prizes": prizes or "",
        "memo": memo or "",
        "winners": winners or "",
        "allow_duplicates": bool(allow_duplicates),
        "allowed_list_text": allowed_list or "",
        "event_at": event_at or "",
    })
