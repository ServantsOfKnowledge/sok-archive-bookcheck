# SOK Archive Book Check

Bulk-check whether books (by title, author, ISBN) exist on the Internet Archive, using the [`ia` CLI](https://archive.org/developers/internetarchive/cli.html).

Requires Python 3 and the `ia` CLI (`brew install internetarchive`). No other dependencies.

## CLI
```
python3 bookcheck.py sample_books.txt -o results.csv
```
Input lines can be `Title | Author | ISBN`, free text (`Moby Dick by Herman Melville 0142437247`), or a CSV with a header.

## Web app
```
python3 webapp.py        # http://127.0.0.1:8765
```
Shows IA cover thumbnails, lets you verify matches manually (✓/✗), and saves every run to a local SQLite file (`books.db`).
