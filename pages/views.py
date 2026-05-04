"""HTTP views for /api/lc-pages.

Endpoints:
    GET    /api/lc-pages/                    list saved pages
    POST   /api/lc-pages/                    create — body: { title, html, events?, editor_state?, slug? }
    GET    /api/lc-pages/<id_or_slug>/       metadata (html_url + events_url + editor_state_url)
    PUT    /api/lc-pages/<id_or_slug>/       overwrite html + events + editor_state
    DELETE /api/lc-pages/<id_or_slug>/       delete row + blobs
    GET    /api/lc-pages/<id_or_slug>/html   raw text/html (used by funnel)
    GET    /api/lc-pages/<id_or_slug>/events raw application/json events
    GET    /api/lc-pages/<id_or_slug>/state  raw editor doc tree (used by editor's Load modal)
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .auth import require_write_token
from .models import LcPage
from .storage import (
    blob_exists,
    delete_blob,
    events_key,
    html_key,
    read_blob,
    state_key,
    write_blob,
)


SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,118}[a-z0-9]$|^[a-z0-9]$")


def _serialize(page: LcPage, request: HttpRequest) -> dict[str, Any]:
    has_state = blob_exists(state_key(str(page.id)))
    return {
        "id": str(page.id),
        "slug": page.slug,
        "title": page.title,
        "html_url": request.build_absolute_uri(
            reverse("lc-page-html", args=[page.slug])
        ),
        "events_url": request.build_absolute_uri(
            reverse("lc-page-events", args=[page.slug])
        ),
        # Always present in the URL shape; the GET endpoint 404s for pages
        # saved before editor_state existed. The editor's Load modal uses
        # has_editor_state to decide whether the page is openable.
        "editor_state_url": request.build_absolute_uri(
            reverse("lc-page-state", args=[page.slug])
        ),
        "has_editor_state": has_state,
        "size_bytes": page.size_bytes,
        "created_at": page.created_at.isoformat(),
        "updated_at": page.updated_at.isoformat(),
    }


def _parse_body(request: HttpRequest) -> dict[str, Any] | HttpResponse:
    if not request.body:
        return JsonResponse({"error": "empty body"}, status=400)
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        return JsonResponse({"error": f"invalid json: {err}"}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({"error": "body must be a JSON object"}, status=400)
    return data


def _events_to_string(events: Any) -> str:
    """Accept either a parsed array (preferred) or a stringified JSON. Stored
    on disk as canonical JSON text."""
    if events is None:
        return "[]"
    if isinstance(events, str):
        try:
            parsed = json.loads(events)
        except json.JSONDecodeError:
            parsed = []
        return json.dumps(parsed, ensure_ascii=False)
    return json.dumps(events, ensure_ascii=False)


def _state_to_string(state: Any) -> str | None:
    """Coerce editor_state to canonical JSON text. Returns None when the
    client didn't send one (PUT preserves existing) or sent an unusable
    value (string-only senders are tolerated for parity with events)."""
    if state is None:
        return None
    if isinstance(state, str):
        try:
            parsed = json.loads(state)
        except json.JSONDecodeError:
            return None
        return json.dumps(parsed, ensure_ascii=False)
    if isinstance(state, (dict, list)):
        return json.dumps(state, ensure_ascii=False)
    return None


def _resolve(id_or_slug: str) -> LcPage:
    try:
        as_uuid = uuid.UUID(id_or_slug)
    except (ValueError, AttributeError):
        return get_object_or_404(LcPage, slug=id_or_slug)
    return get_object_or_404(LcPage, id=as_uuid)


def _slug_for(new_id: uuid.UUID, requested: str | None) -> str:
    if requested:
        candidate = requested.strip().lower()
        if not SLUG_RE.match(candidate):
            raise ValueError(
                "slug must be lowercase letters, digits, and hyphens (1-120 chars)"
            )
        if LcPage.objects.filter(slug=candidate).exists():
            raise ValueError(f"slug '{candidate}' already in use")
        return candidate
    return str(new_id)[:8]


@csrf_exempt
@require_http_methods(["GET", "POST"])
def collection(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        pages = LcPage.objects.all()
        return JsonResponse(
            {"items": [_serialize(p, request) for p in pages]},
        )
    return _create(request)


@require_write_token
def _create(request: HttpRequest) -> HttpResponse:
    data = _parse_body(request)
    if isinstance(data, HttpResponse):
        return data

    title = (data.get("title") or "").strip()
    html = data.get("html")
    if not title:
        return JsonResponse({"error": "title is required"}, status=400)
    if not isinstance(html, str) or not html:
        return JsonResponse({"error": "html is required (string)"}, status=400)

    new_id = uuid.uuid4()
    try:
        slug = _slug_for(new_id, data.get("slug"))
    except ValueError as err:
        return JsonResponse({"error": str(err)}, status=400)

    events_text = _events_to_string(data.get("events"))
    h_key = html_key(str(new_id))
    e_key = events_key(str(new_id))
    html_size = write_blob(h_key, html)
    events_size = write_blob(e_key, events_text)

    state_size = 0
    state_text = _state_to_string(data.get("editor_state"))
    if state_text is not None:
        state_size = write_blob(state_key(str(new_id)), state_text)

    page = LcPage.objects.create(
        id=new_id,
        slug=slug,
        title=title[:200],
        html_path=h_key,
        events_path=e_key,
        size_bytes=html_size + events_size + state_size,
    )
    return JsonResponse(_serialize(page, request), status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
def detail(request: HttpRequest, id_or_slug: str) -> HttpResponse:
    page = _resolve(id_or_slug)
    if request.method == "GET":
        return JsonResponse(_serialize(page, request))
    if request.method == "PUT":
        return _update(request, page)
    return _delete(request, page)


@require_write_token
def _update(request: HttpRequest, page: LcPage) -> HttpResponse:
    data = _parse_body(request)
    if isinstance(data, HttpResponse):
        return data
    html = data.get("html")
    if not isinstance(html, str) or not html:
        return JsonResponse({"error": "html is required (string)"}, status=400)
    title = (data.get("title") or page.title).strip()

    events_text = _events_to_string(data.get("events"))
    html_size = write_blob(page.html_path, html)
    events_size = write_blob(page.events_path, events_text)

    # editor_state is optional on PUT — clients that don't send it (e.g. the
    # funnel-side render path or curl smoke tests) leave any existing
    # state.json untouched so the page stays openable in the editor.
    state_size = 0
    s_key = state_key(str(page.id))
    if "editor_state" in data:
        state_text = _state_to_string(data.get("editor_state"))
        if state_text is None:
            delete_blob(s_key)
        else:
            state_size = write_blob(s_key, state_text)
    elif blob_exists(s_key):
        # preserve existing state size in the rollup
        state_size = len(read_blob(s_key))

    page.title = title[:200]
    page.size_bytes = html_size + events_size + state_size
    page.save(update_fields=["title", "size_bytes", "updated_at"])
    return JsonResponse(_serialize(page, request))


@require_write_token
def _delete(_request: HttpRequest, page: LcPage) -> HttpResponse:
    delete_blob(page.html_path)
    delete_blob(page.events_path)
    delete_blob(state_key(str(page.id)))
    page.delete()
    return JsonResponse({"deleted": True})


@require_http_methods(["GET"])
def raw_html(_request: HttpRequest, id_or_slug: str) -> HttpResponse:
    page = _resolve(id_or_slug)
    body = read_blob(page.html_path)
    return HttpResponse(body, content_type="text/html; charset=utf-8")


@require_http_methods(["GET"])
def raw_events(_request: HttpRequest, id_or_slug: str) -> HttpResponse:
    page = _resolve(id_or_slug)
    body = read_blob(page.events_path)
    return HttpResponse(body, content_type="application/json; charset=utf-8")


@require_http_methods(["GET"])
def raw_state(_request: HttpRequest, id_or_slug: str) -> HttpResponse:
    page = _resolve(id_or_slug)
    key = state_key(str(page.id))
    if not blob_exists(key):
        return JsonResponse(
            {"error": "no editor_state for this page"}, status=404
        )
    body = read_blob(key)
    return HttpResponse(body, content_type="application/json; charset=utf-8")
