<p align="center"><img src="static/sok-logo.png" alt="ServantsOfKnowledge" width="120"></p>

# SOK Archive Book Check

Paste a list of books — titles, authors, ISBNs — and find out which of them already exist on the [Internet Archive](https://archive.org). Get the answer as a CSV, or review the matches visually in a local web app with cover thumbnails.

Built by [ServantsOfKnowledge](https://research.servantsofknowledge.in) to speed up catalogue checks before scanning or sourcing books.

## Features

- **Bulk input**: one book per line, in whatever shape you have it (pipe-separated, free text, or a CSV with a header).
- **ISBN-first matching**: ISBN-10 and ISBN-13 are both tried, and a hit only counts if the ISBN is really in the item's metadata.
- **Fuzzy title and author fallback** with a 0–1 confidence score.
- **CSV output**: one row per input line, with match status, Archive link and runner-up candidates.
- **Web app** with IA cover thumbnails, ✓/✗ manual verification, click-to-swap alternate matches, and filters.
- **Saved runs**: every web run is stored in a local SQLite file, so you can reopen, rename or delete it later.
- **No dependencies** beyond Python 3 and the `ia` command-line tool.

## Requirements

- Python 3.9 or newer (developed on 3.14)
- The Internet Archive CLI, `ia`:
  ```bash
  brew install internetarchive     # macOS
  # or
  pip install internetarchive
  ```
  Searching needs no account, so `ia configure` is not required.

## Quick start

```bash
git clone https://github.com/ServantsOfKnowledge/sok-archive-bookcheck.git
cd sok-archive-bookcheck
```

### Web app

```bash
python3 webapp.py            # then open http://127.0.0.1:8765
python3 webapp.py 9000       # use another port
```

1. Paste your list (or click **Load file**) and give the run a name.
2. Click **Check books**. Rows appear as they are checked.
3. Compare your input against the Archive cover and metadata. Press ✓ or ✗, or click a smaller cover under the match to use that one instead.
4. Click **Download CSV** to export, including your verdicts.

The server listens on `127.0.0.1` only. It is meant to run on your own machine, because it shells out to your installed `ia` CLI.

### Command line

```bash
python3 bookcheck.py sample_books.txt -o results.csv
pbpaste | python3 bookcheck.py > results.csv       # straight from the clipboard
```

Options: `--any-type` (don't restrict to `mediatype:texts`) and `--delay SECONDS` (pause between queries, default 0.3).

## Input formats

Any mix of these in one file:

```text
Pride and Prejudice | Jane Austen | 9780141439518
The Autobiography of a Yogi | Paramahansa Yogananda
Gitanjali by Rabindranath Tagore
Moby Dick by Herman Melville 0142437247
```

or a CSV with a header row containing `title`, `author` and `isbn` columns. Details in [docs/usage.md](docs/usage.md).

## Reading the results

| status | meaning |
|---|---|
| `match` | exact ISBN hit, or title/author score ≥ 0.85 |
| `possible` | score 0.60–0.85, or a candidate you picked by hand — check it |
| `weak` | something was found, but the score is below 0.60 |
| `not_found` | nothing on the Archive matched |
| `error` | the `ia` search failed after retries |

A `match` means the item **exists** on the Archive. It does not mean the book is borrowable or free to download; the `ia` search does not report availability.

## Documentation

- [Usage guide](docs/usage.md): input formats, output columns, web app workflow, tips
- [How matching works](docs/matching.md): search strategy, scoring, known limits
- [Web app API and data model](docs/api.md): HTTP endpoints and the SQLite schema

## Project layout

```text
bookcheck.py      matching engine and CLI (standard library only)
webapp.py         local web UI, JSON API and SQLite storage (imports bookcheck)
sample_books.txt  example input
static/           logo and favicon
docs/             documentation
books.db          created on first web run; local history (git-ignored)
```

## Troubleshooting

- **`ia: command not found`**: install it as above and make sure it is on your `PATH`.
- **`Address already in use`**: another process holds the port. Start on another one: `python3 webapp.py 9000`.
- **Old app shows up in Chrome on that port**: unregister the stale service worker at `chrome://serviceworker-internals`, or open `http://127.0.0.1:PORT` in an Incognito window.
- **Lots of `error` rows**: the Archive may be rate-limiting you. Raise `--delay` and re-run.

## License

[MIT](LICENSE) © ServantsOfKnowledge
