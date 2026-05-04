# lc-backend

Django service that stores Landing-Constructor page exports (HTML + events
JSON) and serves them to the funnel. SQLite for metadata, local filesystem
for blobs by default, S3 optional.

## Layout

    lc-backend/
      manage.py
      requirements.txt
      .env.example          → copy to .env
      lc_backend/           Django project (settings, urls)
      pages/                LcPage model + storage helper + views
        models.py
        storage.py          thin wrapper over default_storage
        auth.py             bearer-token decorator
        views.py            HTTP endpoints
        urls.py
      storage/              created on first write; gitignored
      db.sqlite3            metadata; gitignored

## Run locally (Windows / PowerShell)

```powershell
cd C:\Users\admin\Desktop\jobEscape\hackathon\lc-backend
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver 8000
```

Service is now at `http://localhost:8000/`. Health check returns
`{"ok": true, "service": "lc-backend"}`.

To create a Django admin user (optional, for inspecting saved pages at
`/admin`):

```powershell
.\.venv\Scripts\python.exe manage.py createsuperuser
```

## Configuration

All settings come from `.env` (see `.env.example`). None are required for
local dev. The ones that matter:

| Var | Default | Purpose |
|---|---|---|
| `LC_BACKEND_WRITE_TOKEN` | *(unset)* | Bearer token required on POST/PUT/DELETE. **Unset = open** — set before deploying. |
| `DJANGO_SECRET_KEY` | insecure dev key | Standard Django secret. |
| `DJANGO_DEBUG` | `true` | Set `false` in prod. |
| `DJANGO_ALLOWED_HOSTS` | `*` | Comma-separated. |
| `AWS_BUCKET` | *(unset)* | If set, blobs go to S3 instead of `./storage/`. |
| `AWS_REGION` | `us-east-1` | |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | *(unset)* | Required only if `AWS_BUCKET` is set. |
| `LC_S3_PREFIX` | `lc-pages` | Key prefix inside the bucket. |

The funnel already has `AWS_BUCKET` / creds in its `.env`. Reusing them with
the default `LC_S3_PREFIX=lc-pages` keeps these blobs isolated from the
funnel's existing `templates/` / `quiz_prod/` keys.

## API

All write endpoints require `Authorization: Bearer <LC_BACKEND_WRITE_TOKEN>`
(or `X-API-Key: <token>`) when the token is configured.

### `POST /api/lc-pages/` — create

```json
{
  "title": "Pricing v3",
  "html": "<header>...</header>",
  "events": [{ "selector": "[data-lc-events='abc']", "bindings": [...] }],
  "slug": "pricing-v3"
}
```

- `title` — required
- `html` — required, the full HTML body output of `buildActiveHtml(state.doc)`
- `events` — optional `EventConfig[]` array. Either parsed JSON or a JSON string.
  If omitted defaults to `[]`. (The editor inlines the events config into the
  HTML via `<script>window.__lcEventsConfig=…</script>`. You can either keep
  it inline and pass `events: []`, or split it out before POSTing.)
- `slug` — optional, lowercase letters/digits/hyphens. Auto-generated from the
  UUID when omitted. Conflicts return 400.

Response `201`:

```json
{
  "id": "8f3a…",
  "slug": "pricing-v3",
  "title": "Pricing v3",
  "html_url":   "http://localhost:8000/api/lc-pages/pricing-v3/html",
  "events_url": "http://localhost:8000/api/lc-pages/pricing-v3/events",
  "size_bytes": 18421,
  "created_at": "2026-05-04T12:00:00+00:00",
  "updated_at": "2026-05-04T12:00:00+00:00"
}
```

### `GET /api/lc-pages/` — list

```json
{ "items": [ /* same shape as create response */ ] }
```

### `GET /api/lc-pages/<id_or_slug>/` — metadata

Same shape as create response. Accepts either the UUID or the slug.

### `PUT /api/lc-pages/<id_or_slug>/` — overwrite

Same body as POST (no `slug`). HTML and events are rewritten in place; the
`updated_at` timestamp is bumped. No history is kept (versioning is
intentionally out of scope for the hackathon).

### `DELETE /api/lc-pages/<id_or_slug>/`

Removes both blobs and the row.

### `GET /api/lc-pages/<id_or_slug>/html` — raw HTML

Returns `text/html`. **This is the URL the funnel calls.**

### `GET /api/lc-pages/<id_or_slug>/events` — raw events JSON

Returns `application/json`.

## Editor → backend (sketch)

In `landing-constructor-app/app/editor/components/TopBar.tsx`, add a "Save"
button alongside Export. The current `buildActiveHtml(state.doc)` is exactly
what the backend stores:

```ts
const res = await fetch(`${BACKEND_URL}/api/lc-pages/`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": `Bearer ${process.env.NEXT_PUBLIC_LC_BACKEND_TOKEN}`,
  },
  body: JSON.stringify({
    title,
    html: buildActiveHtml(state.doc),
    // events are already inlined as <script>window.__lcEventsConfig=…</script>
    // — leave events: [] and let the renderer parse the inline config, or
    // split via annotateAndCollect(state.doc.children) and pass `configs`.
    events: [],
  }),
});
```

## Funnel → backend (sketch)

Add a route like `funnel/src/app/lc/[slug]/page.tsx`:

```tsx
export default async function LcPage({ params }: { params: { slug: string } }) {
  const meta = await fetch(`${process.env.LC_BACKEND_URL}/api/lc-pages/${params.slug}/`)
    .then(r => r.json());
  const [html, events] = await Promise.all([
    fetch(meta.html_url).then(r => r.text()),
    fetch(meta.events_url).then(r => r.json()),
  ]);
  return <LcRenderer html={html} events={events} />;
}
```

This mirrors the existing `mdx_url` pattern in
`funnel/src/widgets/quiz-builder/ui/quiz-builder.tsx` —
`await handleGetHtml(firstNode.quiz_page.mdx_url)`.

## Hosting

Quick recommendation for the hackathon: **Railway** or **Render**. Both
deploy a Django app from a GitHub repo in ~5 minutes and give you a public
URL. SQLite + local-filesystem blobs work out of the box on a single
instance; switch to Postgres + S3 only when you need multi-instance.

### Vercel — short answer: no, not without rework

Vercel runs Python as **serverless functions**, not as a long-running WSGI
process. Two real problems:

1. **SQLite + filesystem blobs are ephemeral.** Each invocation gets a fresh
   `/tmp` and the bundled `db.sqlite3` is read-only. Writes appear to work
   then vanish on the next cold start.
2. **Django is built around a long-running process.** You can wrap it with a
   WSGI-to-serverless shim (`vercel.json` with `@vercel/python`), but cold
   starts are slow and the Django ORM was not designed for per-request
   reconnect-and-die.

If you really want Vercel, the only sane path is: **Vercel Postgres** for
metadata + **S3 for blobs** + the Django app stripped to a stateless
serverless handler. That's noticeably more work than just deploying to
Railway. Skip Vercel for this service.

### Railway (recommended)

1. Push `lc-backend/` to GitHub.
2. New project → Deploy from repo → pick `lc-backend`.
3. Set env vars (`LC_BACKEND_WRITE_TOKEN`, `DJANGO_SECRET_KEY`,
   `DJANGO_DEBUG=false`, `DJANGO_ALLOWED_HOSTS=*.up.railway.app`).
4. Build command: `pip install -r requirements.txt && python manage.py migrate`
5. Start command: `gunicorn lc_backend.wsgi --bind 0.0.0.0:$PORT`
6. (Optional) attach a Postgres add-on and switch `DATABASES` over. SQLite is
   fine on Railway as long as you have a single instance and a persistent
   volume.

### Render

Identical shape — Web Service → Python → same build/start commands. The
free tier sleeps after 15 min idle (cold-start delay on first request);
the $7/mo plan removes that.

### Fly.io

`fly launch` from the project root, attach a 1 GB volume mounted at
`/app/storage` for blobs and the SQLite file. Generous free allowance.

### PythonAnywhere

Easiest manual setup: upload the folder, point a web app at
`lc_backend/wsgi.py`, set env vars in the web tab. Free tier handles low
hackathon traffic fine.

### Heroku

Works (Procfile: `web: gunicorn lc_backend.wsgi`) but no free tier — eco
dyno is $5/mo. Use S3 since Heroku's filesystem is ephemeral.

## What's intentionally not in here

- **Versioning.** Each save overwrites. Add a `versions/` S3 prefix and a
  `version` column when needed.
- **Granular auth.** A single shared token guards all writes. No per-user
  ACLs. If you need them, swap `auth.py` for `django.contrib.auth` + DRF
  `TokenAuthentication`.
- **Rate limiting.** Add `django-ratelimit` if hackathon submissions stay up
  past the demo.
