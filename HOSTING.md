# Hosting tutorial — all three projects

Three pieces, three hosts:

| Project | Path | Host | Why |
|---|---|---|---|
| `lc-backend` (Django) | `hackathon/lc-backend/` | **PythonAnywhere** | Free Django-friendly tier, persistent filesystem, no Docker/Procfile fuss |
| `landing-constructor-app` (Next.js editor) | `hackathon/landing-constructor-app/` | **Vercel** | Native Next.js host |
| `funnel` (Next.js consumer) | `funnel/` | **Vercel** | Already targets Vercel (`@vercel/analytics`, `@vercel/functions` are deps) |

The order to deploy matters. The editor and the funnel both need the
backend's URL, so deploy the backend first, then the others.

---

## 1. Backend → PythonAnywhere

PythonAnywhere's free "Beginner" tier hosts one Django app, gives you a
persistent filesystem (so SQLite + `./storage/` blobs survive restarts),
and runs Python 3.10. You'll get a URL like `https://<username>.pythonanywhere.com`.

### 1.1 Push to GitHub

PythonAnywhere can clone from GitHub. From your local machine:

```powershell
cd C:\Users\admin\Desktop\jobEscape\hackathon\lc-backend
git init
git add .
git commit -m "lc-backend initial"
# create an empty repo on github.com/<you>/lc-backend, then:
git branch -M main
git remote add origin https://github.com/<you>/lc-backend.git
git push -u origin main
```

`.venv/`, `db.sqlite3`, `.env`, and `storage/` are already in `.gitignore`.

### 1.2 Sign up + clone on PythonAnywhere

1. Sign up at [pythonanywhere.com](https://www.pythonanywhere.com/) (free
   Beginner plan).
2. Open the **Bash console** from the dashboard.
3. Clone:

   ```bash
   git clone https://github.com/<you>/lc-backend.git ~/lc-backend
   cd ~/lc-backend
   ```

### 1.3 Create venv + install deps

PythonAnywhere ships with `mkvirtualenv`. The free tier offers Python up to
3.10 — pick whichever is newest available (check `which python3.10`):

```bash
mkvirtualenv lc-backend --python=python3.10
# from now on the venv autoactivates when you `cd ~/lc-backend`
pip install -r requirements.txt
```

If `mkvirtualenv` isn't on PATH, the equivalent is `python3.10 -m venv ~/.virtualenvs/lc-backend && source ~/.virtualenvs/lc-backend/bin/activate`.

### 1.4 Configure `.env`

```bash
cp .env.example .env
nano .env
```

Set at minimum:

```
LC_BACKEND_WRITE_TOKEN=<a-long-random-string>
DJANGO_SECRET_KEY=<another-long-random-string>
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=<your-username>.pythonanywhere.com
```

Generate the secrets locally with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.

S3 vars stay empty — PythonAnywhere's filesystem is persistent, so blobs
go straight under `~/lc-backend/storage/`. Switching to S3 later is one
env-var change with no code edits.

### 1.5 Run migrations

```bash
python manage.py migrate
python manage.py createsuperuser   # optional, for /admin
```

### 1.6 Add the web app

1. Go to the **Web** tab on the PythonAnywhere dashboard.
2. **Add a new web app** → **Manual configuration** → **Python 3.10**.
3. The default working directory is `/home/<username>/`.

In the web app config you'll see four fields to set:

- **Source code**: `/home/<username>/lc-backend`
- **Working directory**: `/home/<username>/lc-backend`
- **Virtualenv**: `/home/<username>/.virtualenvs/lc-backend`
- **WSGI configuration file**: click the link, edit the file PythonAnywhere
  generated for you (typically `/var/www/<username>_pythonanywhere_com_wsgi.py`).
  Replace its body with:

  ```python
  import os
  import sys
  from pathlib import Path

  from dotenv import load_dotenv

  PROJECT_ROOT = Path("/home/<username>/lc-backend")
  if str(PROJECT_ROOT) not in sys.path:
      sys.path.insert(0, str(PROJECT_ROOT))

  load_dotenv(PROJECT_ROOT / ".env")
  os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lc_backend.settings")

  from django.core.wsgi import get_wsgi_application
  application = get_wsgi_application()
  ```

  Replace `<username>` with your real username. The `load_dotenv` line is
  what makes the `.env` you wrote in step 1.4 visible to the Django process
  — without it, gunicorn-style environment variables wouldn't reach Django.

### 1.7 Static files (admin assets)

In the web app's **Static files** section, add:

| URL | Directory |
|---|---|
| `/static/` | `/home/<username>/lc-backend/staticfiles` |

Then collect them once:

```bash
cd ~/lc-backend
python manage.py collectstatic --noinput
```

(Only needed if you'll use `/admin`. The `/api/lc-pages/...` endpoints
work without static files.)

### 1.8 Reload + smoke test

Click the green **Reload** button in the Web tab. Then from your local
machine:

```powershell
curl https://<username>.pythonanywhere.com/
# {"ok": true, "service": "lc-backend"}

# create a page (replace <token>):
curl -X POST https://<username>.pythonanywhere.com/api/lc-pages/ `
  -H "Authorization: Bearer <token>" `
  -H "Content-Type: application/json" `
  -d '{\"title\":\"hello\",\"html\":\"<h1>Hello</h1>\",\"events\":[]}'
```

You should get back a JSON object with `html_url` and `events_url`. Hit
the `html_url` in a browser — your `<h1>Hello</h1>` should render.

### 1.9 Updating the deploy

```bash
cd ~/lc-backend
git pull
pip install -r requirements.txt   # only if requirements.txt changed
python manage.py migrate          # only if migrations changed
```

Then click **Reload** in the Web tab.

---

## 2. Editor → Vercel

The editor is a vanilla Next.js 16 app. Vercel imports it directly.

### 2.1 Push to GitHub

```powershell
cd C:\Users\admin\Desktop\jobEscape\hackathon\landing-constructor-app
git init   # if not already a repo
# … same flow as backend …
```

### 2.2 Import on Vercel

1. [vercel.com/new](https://vercel.com/new) → import the GitHub repo.
2. Framework: Next.js (auto-detected).
3. Root directory: leave at the repo root (or set to
   `landing-constructor-app/` if you committed the wider hackathon repo).
4. Build command: `next build` (default).
5. Output directory: `.next` (default).

### 2.3 Environment variables

Set these in **Project → Settings → Environment Variables**:

| Var | Value | Notes |
|---|---|---|
| `NEXT_PUBLIC_LC_BACKEND_URL` | `https://<username>.pythonanywhere.com` | The editor calls this from the **browser** (the Save button), so it must be `NEXT_PUBLIC_…`. |
| `NEXT_PUBLIC_LC_BACKEND_TOKEN` | the `LC_BACKEND_WRITE_TOKEN` from step 1.4 | Hackathon-grade — exposing a write token in the client is fine for an internal tool, but rotate it before showing the URL to anyone. |

> **Note**: the editor's "Save" button isn't wired up yet — only the
> backend and the funnel-side fetch. Wiring the editor is one fetch call
> in `app/editor/components/TopBar.tsx` (sketch in `lc-backend/README.md`).

### 2.4 Deploy

Push to `main`. Vercel builds and gives you `<project>.vercel.app`.

---

## 3. Funnel → Vercel

The funnel is also Next.js (14.2). Same Vercel flow, with **server-side**
env vars (the funnel calls the backend from server components only).

### 3.1 Push / import

Identical to the editor: push the funnel repo to GitHub, import on Vercel.

### 3.2 Environment variables

Set in Project Settings:

| Var | Value | Notes |
|---|---|---|
| `LC_BACKEND_URL` | `https://<username>.pythonanywhere.com` | **Server-side only** — no `NEXT_PUBLIC_` prefix. The funnel fetches LC pages in `app/lc/[slug]/page.tsx`, which runs on the server. |

The funnel already declares `LC_BACKEND_URL` in `src/shared/types/env.d.ts`,
so TypeScript will know about it.

You'll also need the funnel's existing env vars (Stripe, AWS, Amplitude,
GrowthBook, etc.). Copy them from the funnel's existing `.env` — those are
unrelated to lc-backend.

### 3.3 Deploy + smoke test

After the deploy succeeds, hit `https://<funnel>.vercel.app/lc/<slug>` —
the funnel server-fetches the page from PythonAnywhere and renders it via
`<LcRenderer>`. Replace `<slug>` with the slug returned by your POST in
step 1.8.

---

## End-to-end flow check

Once all three are up:

1. In the editor (Vercel), build a page.
2. Click Save (once wired) — the editor POSTs to
   `https://<username>.pythonanywhere.com/api/lc-pages/` with the bearer
   token. The backend writes a row to SQLite and the html / events.json
   blobs to `~/lc-backend/storage/lc-pages/<id>/`.
3. The editor receives `{ id, slug, html_url, events_url }`.
4. Open `https://<funnel>.vercel.app/lc/<slug>` — the funnel's
   `app/lc/[slug]/page.tsx` runs `getLcPage(slug)` server-side:
   - GETs `…/api/lc-pages/<slug>/html` (text)
   - GETs `…/api/lc-pages/<slug>/events` (json)
   - Strips `<script>` tags so the inline `__lcEventsConfig` doesn't
     double-bind
   - Renders `<LcRenderer html={…} events={…} />` in the funnel's
     analytics + Builder context.

---

## Hardening checklist (after the demo)

- Set `DJANGO_DEBUG=false` and a real `DJANGO_SECRET_KEY` (already in step
  1.4 — verify it stuck).
- Constrain `DJANGO_ALLOWED_HOSTS` to the PythonAnywhere domain (already
  done) and keep `LC_BACKEND_WRITE_TOKEN` set so writes are gated.
- In `lc_backend/settings.py`, replace `CORS_ALLOW_ALL_ORIGINS = True`
  with a `CORS_ALLOWED_ORIGINS` list containing your editor + funnel
  Vercel URLs. (Hackathon-mode is wide open.)
- Switch SQLite → Postgres if multiple instances or heavy writes ever
  matter. PythonAnywhere offers MySQL on the free tier; PostgreSQL is
  paid-only there. For Postgres, Railway / Render / Supabase all have
  free tiers.
- Rotate the bearer token to a fresh value once the demo is over and
  you've shared the URL.

---

## Troubleshooting

**"Something went wrong :-(" on PythonAnywhere first hit**
Check **Web tab → Error log**. Most common cause is a typo in the WSGI
file's `PROJECT_ROOT` path or a missing `pip install -r requirements.txt`.

**`/admin` shows unstyled HTML**
You skipped step 1.7 (`collectstatic` + static-files mapping). Either run
those steps or just don't use `/admin`.

**Funnel returns 404 on `/lc/<slug>`**
Verify the slug exists: `curl https://<username>.pythonanywhere.com/api/lc-pages/<slug>/`.
If that 404s, the page wasn't saved or the slug is wrong. If it returns
JSON but the funnel still 404s, check the funnel's deployment logs —
`LC_BACKEND_URL` is probably unset.

**CORS error in the editor's browser console**
Backend's `CORS_ALLOW_ALL_ORIGINS = True` should make this impossible.
If you see one, the backend isn't actually running with that setting —
verify `pip show django-cors-headers` and that `corsheaders` is in
`INSTALLED_APPS` (already wired in `lc_backend/settings.py`).

**Editor write returns 401**
The `Authorization: Bearer …` header doesn't match `LC_BACKEND_WRITE_TOKEN`.
Confirm the env var values exactly match between Vercel and PythonAnywhere
(no trailing whitespace, no quotes around the value).
