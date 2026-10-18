# Static site (GitHub Pages)

`site/` is a self-contained browser version of the web app. It needs no server: the page calls the Internet Archive search API directly, and keeps saved runs in the browser.

## Files

| file | purpose |
|---|---|
| `site/index.html` | UI, IndexedDB storage, run loop |
| `site/bookcheck.js` | browser port of `bookcheck.py`: input parsing, ISBN handling, search, scoring, CSV parsing |
| `site/static/` | logo and favicon |

## How it differs from the Python app

- **Search** uses `https://archive.org/advancedsearch.php` (the same endpoint `ia search` uses). The Archive allows cross-origin requests, which is why this works from a static page. Covers load from `archive.org/services/img/<identifier>` as before.
- **Storage** is IndexedDB (`sok-bookcheck` database, `runs` and `rows` stores), so runs exist only in that browser profile on that device. Download the CSV to back up or move a run, and use **Import CSV** to bring it back.
- **Runs happen in the tab.** Keep it open until the run finishes. Use **Stop** to end early; the rows checked so far are kept.
- **Matching rules are identical**: ISBN-10/13 variants verified against the item's ISBN list, title and author fallback, the same score formula and the 0.85 / 0.60 thresholds (see [matching.md](matching.md)).

## Keeping the two versions in sync

The matching logic exists twice, in Python and JavaScript. When you change one, change the other. `site/bookcheck.js` was checked against Python for identical title similarity ratios, input parsing and ISBN variants.

## Try it locally

```bash
cd site && python3 -m http.server 8770      # open http://localhost:8770
```

## Deployment

`.github/workflows/pages.yml` publishes `site/` to GitHub Pages on every push to `main` that touches `site/`. Pages must be set to **Source: GitHub Actions** in the repository settings (Settings, Pages).
