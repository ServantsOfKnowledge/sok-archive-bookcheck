# Usage guide

## Input

One book per line. Blank lines are ignored. Three formats are understood, and you can mix the first two in one file.

### 1. Separated fields

`Title | Author | ISBN` with `|` or a tab as the separator. Author and ISBN are optional.

```text
Pride and Prejudice | Jane Austen | 9780141439518
Gitanjali | Rabindranath Tagore
Gitanjali | 9788171672707          <- title and ISBN only
```

### 2. Free text

An ISBN anywhere in the line is detected and removed. The rest is split into title and author on ` by ` or ` - `.

```text
Moby Dick by Herman Melville 0142437247
Dune - Frank Herbert
```

### 3. CSV with a header

The first line must contain a comma and the word `title` or `isbn`. Recognised columns (case-insensitive):

| field | accepted column names |
|---|---|
| title | `title`, `book`, `name` |
| author | `author`, `authors`, `creator` |
| isbn | `isbn`, `isbn13`, `isbn10` |

ISBNs may contain hyphens or spaces; they are cleaned automatically.

## Output columns

| column | meaning |
|---|---|
| `input_title`, `input_author`, `input_isbn` | what you supplied (ISBN cleaned) |
| `status` | `match`, `possible`, `weak`, `not_found`, `error` |
| `match_by` | `isbn`, `title/author`, or `manual` (web app swap) |
| `score` | confidence, 0–1 (1.0 for an exact ISBN hit) |
| `num_candidates` | how many Archive results were considered |
| `ia_identifier`, `ia_url` | the best match's Archive identifier and page |
| `ia_title`, `ia_creator`, `ia_year`, `ia_mediatype` | its metadata |
| `other_candidates` | up to three runner-up identifiers |
| `verdict` | web app only: `ok`, `no`, or blank (not yet reviewed) |

The CLI writes UTF-8 with a BOM so Excel opens non-ASCII names correctly.

## Web app workflow

- **Run name**: defaults to a timestamp, or the uploaded file's name. Change it before clicking **Check books**.
- **Saved runs** dropdown: reopens any previous run with its verdicts. **Rename** and **Delete** act on the open run.
- **Cover column**: the Archive's own thumbnail for the best match. Click it to open the item. Greyed-out covers mean the item has no image.
- **Smaller covers under a match**: runner-up candidates. Click one to use it instead (status becomes `possible`, `match_by` becomes `manual`).
- **✓ / ✗**: mark a match correct or wrong. Click again to clear.
- **Filter**: show all, needs review, verified, rejected, or not found.
- Results are saved as each book is checked. Closing the tab mid-run is safe: the server finishes the run and it appears in the saved runs list.

## Tips

- Supplying an ISBN is the most reliable route. Where you have one, include it.
- For titles with subtitles, try the short title first; the Archive's own titles are often shorter than catalogue titles.
- Review `possible` and `weak` rows by hand. Fast manual review is what the covers are for.
- Large lists: the tool makes roughly one request per book plus a short pause, so a few hundred books take a few minutes.
- Use `--any-type` (or the **any media type** box) if you also want audio, video or other items, not only texts.
