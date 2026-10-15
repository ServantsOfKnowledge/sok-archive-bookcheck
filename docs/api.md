# Web app API and data model

`webapp.py` is a small standard-library HTTP server (`http.server`) bound to `127.0.0.1`. The page is a single HTML file served from `/`; it talks to the JSON endpoints below. There is no authentication, so do not expose the port beyond localhost.

## Endpoints

| method and path | purpose |
|---|---|
| `GET /` | the web app |
| `GET /static/<name>.png` | logo and favicon |
| `GET /api/runs` | list runs: `id`, `name`, `created_at`, `n` (books), `verified` |
| `GET /api/runs/{id}` | one run with all its rows |
| `POST /api/runs/{id}` | rename. Body: `{"name": "…"}` |
| `DELETE /api/runs/{id}` | delete a run and its rows |
| `POST /api/check?name=…&any=0\|1` | create a run from the request body (the pasted text) and stream results |
| `POST /api/import?name=…` | create a run from a results CSV sent as the request body. Returns `{"run": id}`; `400` if the columns are wrong |
| `POST /api/rows/{id}` | update a row. Body: `{"verdict": "ok"\|"no"\|""}` and/or `{"pick": "<identifier>"}` |

### Streaming check

`POST /api/check` responds with newline-delimited JSON (`application/x-ndjson`):

```text
{"run": 3, "total": 5}
{"id": 21, "input_title": "…", "status": "match", …, "candidates": [...], "verdict": ""}
{"id": 22, …}
```

The first line announces the run id and the number of books; each following line is one finished row. The server keeps checking and saving even if the client disconnects.

### Row object

All CLI output columns, plus:

- `id`: row id
- `verdict`: `""`, `"ok"` or `"no"`
- `candidates`: up to five `{identifier, title, creator, year, mediatype}` objects (best first)

### Example

```bash
curl -s -X POST --data-binary @sample_books.txt "http://127.0.0.1:8765/api/check?name=demo"
curl -s http://127.0.0.1:8765/api/runs
```

## SQLite schema

Stored in `books.db` next to the scripts (git-ignored, WAL mode).

```sql
CREATE TABLE runs(
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL,        -- ISO 8601, local time
  total INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE rows(
  id INTEGER PRIMARY KEY,
  run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  idx INTEGER NOT NULL,            -- position in the input
  data TEXT NOT NULL,              -- JSON row object (without id/verdict)
  verdict TEXT NOT NULL DEFAULT '' -- '', 'ok', 'no'
);
```

Query it directly, for example:

```bash
sqlite3 books.db "SELECT r.name, w.verdict, json_extract(w.data,'\$.input_title'), json_extract(w.data,'\$.ia_url')
                  FROM rows w JOIN runs r ON r.id = w.run_id WHERE w.verdict = 'ok'"
```

## Using the engine from Python

```python
import bookcheck as bc

book = {"title": "Gitanjali", "author": "Rabindranath Tagore", "isbn": ""}
status, match_by, best, score, candidates = bc.check(book, strict_types=True)
row = bc.row_for(book, (status, match_by, best, score, candidates))
```

## Thumbnails

Covers are loaded by the browser straight from `https://archive.org/services/img/<identifier>`. The server never downloads or stores images.
