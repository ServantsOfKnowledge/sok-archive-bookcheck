# How matching works

The engine lives in `bookcheck.py` and shells out to `ia search` for every query.

## 1. ISBN lookup

If an ISBN is supplied:

1. It is cleaned (digits and `X` only).
2. Its ISBN-10 and ISBN-13 forms are both computed, since an Archive item may list either.
3. One query is sent: `(isbn:A OR isbn:B) AND mediatype:texts`.
4. Each result's `isbn` metadata list is checked locally. Only items that really contain one of the variants count.

Step 4 matters: a plain ISBN search can return unrelated items, so results are verified rather than trusted. An exact hit gives `status=match`, `match_by=isbn`, `score=1.0`.

## 2. Title and author search

If there is no ISBN, or the ISBN found nothing:

1. A leading "The", "A" or "An" is dropped from the title, because Archive titles often omit it.
2. Query: `title:("…") AND creator:(token AND token …)`, with Lucene special characters escaped. Author tokens are the words of the name (one-letter initials are skipped), in any order.
3. If that returns nothing, it retries with the title only. The author then only affects the score.
4. Up to 15 results are scored and ranked.

### Score

```text
title_similarity = difflib ratio of normalised titles (lowercase, punctuation removed)

with author:     score = 0.7 * title_similarity + 0.3 * author_token_overlap
without author:  score = title_similarity
```

`author_token_overlap` is the fraction of your author's name tokens found in the item's `creator` field.

| score | status |
|---|---|
| ≥ 0.85 | `match` |
| 0.60–0.85 | `possible` |
| < 0.60 | `weak` |
| no results | `not_found` |

## Scope

Searches are limited to `mediatype:texts`. Pass `--any-type` on the CLI, or tick **any media type** in the web app, to remove the restriction.

## Reliability

- A failed `ia search` is retried up to 3 times with a growing pause. If it still fails, the row gets `status=error` and the run continues.
- A short pause (0.3 s CLI, 0.2 s web) follows each book to be polite to archive.org.

## Known limits

- **Existence, not availability.** The search does not say whether an item is borrowable, lendable or openly downloadable.
- **Editions.** A title match may be a different edition or translation of the same work. That is what manual review and the covers are for.
- **Transliteration.** Names spelled differently from the Archive's record (e.g. Indic names romanised in another way) can miss; try a shorter or alternative spelling.
- **Duplicate items.** The Archive often has several scans of one book; the best-scoring one is reported and runners-up are listed.
- **Free text parsing is heuristic.** If a title itself contains " by " or " - ", use the pipe-separated format.
