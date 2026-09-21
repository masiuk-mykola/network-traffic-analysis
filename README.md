# Test task: a web interface for network traffic analysis

`backend/` is a working API. It serves captured network traffic from a fictional company: three
capture points, about a hundred thousand sessions over three days, decoded protocols, carved files,
PCAP. You do not need to touch the backend — it works and it has tests.

Your job is to build the web interface for it.

## Why we ask for this

Two things, and both count.

How you build an interface someone can actually work in: what you put on screen and what you leave
out, how the layout holds up when there are thousands of rows, what the user sees while a search is
running, when something is empty, when it fails. It does not have to be beautiful, but it has to be
thought through.

And how you work against a real API: a long search that runs on the server, paged results, data
that arrives in more than one shape, errors and timeouts. All of that is in the task because that
is how our product works.

## Running the backend

You need Python 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
cd backend
uv sync
uv run capture-api serve
```

The API comes up on `http://localhost:8700`. Also there:

- `http://localhost:8700/docs` — the full endpoint reference; you can fire requests straight from
  the browser;
- `backend/openapi.json` — the same schema as a file, if you want to generate a typed client.

If you would rather not install uv, `docker compose up -d --build` from the repository root gives
you the same API on the same port.

CORS is off on purpose. The browser cannot call this API: your own server has to proxy the requests
(a route handler, a BFF — whatever suits you).

Accounts:

| email                   | password        | role                        |
| ----------------------- | --------------- | --------------------------- |
| `ana@quillmere.example` | `demo-analyst`  | analyst, sees everything    |
| `oli@quillmere.example` | `demo-observer` | read-only, some data hidden |

## Running the frontend

The interface lives in `frontend/` (Next.js, App Router). Everything below is run from the
repository root unless it says otherwise.

Whole stack in Docker — the API and a production build of the app:

```bash
docker compose up -d --build     # API on :8700, UI on http://localhost:3000
```

Same, but with the app running from the source tree and reloading on save:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

Without Docker (Node 24, see `.nvmrc`), with the API already running on :8700:

```bash
cd frontend
cp .env.example .env.local       # CAPTURE_API_URL, read on the server only
npm install
npm run dev                      # refreshes the API types first, then starts on :3000
```

The checks CI runs, from `frontend/`:

```bash
npm run format:check && npm run lint && npm run typecheck && npm run test && npm run build
npm run test:e2e                 # Playwright
```

Two problems in the delivered backend had to be worked around to run it at all. `pyproject.toml`
and `backend/Dockerfile` expect a `backend/README.md` that was missing from the archive, so both
`uv sync` and the image build failed — the file was added back. And the image's `CMD` names
`capture_api` while the console script installed by `pyproject.toml` is `capture-api`, so the
container exec-failed on boot — `docker-compose.yml` overrides the command rather than editing the
backend.

## What to build

Three screens.

**Sign in.** Email and password. The backend token must not reach the browser — keep it on your
side and hand out only a session. A HAR capture of your app should not contain the token.

**Search.** The main screen. The user picks capture points and a time window, builds a condition
from the fields the server publishes (`/v1/meta/fields`), and starts a search. The search is a job
on the server: you create it, follow its progress, and read the results page by page while it is
still running. The result is a table of sessions that is comfortable to scan — there are a lot of
rows.

**Session.** One session in full: the decoded protocol transaction, laid out so it can actually be
read. Write a proper view for one protocol of your choice, and a generic view for the rest that
builds itself from the schema at `/v1/meta/schema/{protocol}`.

Everything else is optional and only if time is left: the live event feed over SSE, WebSocket,
downloading PCAP and files, saved queries. One finished thing beats five started ones.

What you call the project, how you lay out the files, which routing you use — entirely up to you.

Plan on about a day of work. If you did not get to something, say so and say why.

## Stack

We use Next.js, TypeScript, TanStack Query and Table, Tailwind and Radix — that is what we will
find easiest to read. It is a preference, not a requirement: use whatever you are fastest in.

## Something is wrong in that traffic

One of the machines on the network is compromised, and no ready-made rule names it. Once your
interface works, use it to find where it started, and write the answer in your README, with a link
to that spot in your interface and a couple of words on how you found it and what you ruled out
along the way. The traffic contains things that look suspicious and are harmless.

Find it with the interface, not by reading the backend code.

## What to send

A repository with its commit history and a README saying how to run it, what is done, what is not
and why. At least one test you can point at. If you used AI, say where and what you fixed by hand.
That is fine with us, we want the honest picture.

Ask questions. If something in the API looks broken, say so — that is part of the job too.
