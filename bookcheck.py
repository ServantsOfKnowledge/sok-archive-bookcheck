#!/usr/bin/env python3
"""Bulk-check whether books exist on the Internet Archive, using the `ia` CLI.

Input  (file or stdin), one book per line, any of:
    * CSV with a header containing title / author / isbn columns
    * "Title | Author | ISBN"  (pipe or tab separated, author/ISBN optional)
    * free text: "Pride and Prejudice by Jane Austen 9780141439518"

Output: CSV, one row per input line (see COLUMNS).

    python3 bookcheck.py books.txt -o results.csv
    pbpaste | python3 bookcheck.py > results.csv
"""
import argparse
import csv
import io
import json
import re
import subprocess
import sys
import time
from difflib import SequenceMatcher

FIELDS = ["identifier", "title", "creator", "date", "isbn", "mediatype", "language"]
COLUMNS = [
    "input_title", "input_author", "input_isbn",
    "status", "match_by", "score", "num_candidates",
    "ia_identifier", "ia_url", "ia_title", "ia_creator", "ia_year", "ia_mediatype",
    "other_candidates",
]
ISBN_RE = re.compile(r"\b(?:97[89][- ]?)?\d(?:[- ]?\d){8}[- ]?[\dXx]\b")
LUCENE_SPECIAL = re.compile(r'([+\-&|!(){}\[\]^"~*?:\\/])')


def norm(s):
    return re.sub(r"[^a-z0-9 ]", "", re.sub(r"\s+", " ", (s or "").lower())).strip()


def clean_isbn(s):
    return re.sub(r"[^0-9Xx]", "", s or "").upper()


def isbn10_to_13(i):
    if len(i) != 10:
        return None
    core = "978" + i[:9]
    chk = (10 - sum(int(c) * (1 if n % 2 == 0 else 3) for n, c in enumerate(core)) % 10) % 10
    return core + str(chk)


def isbn13_to_10(i):
    if len(i) != 13 or not i.startswith("978"):
        return None
    core = i[3:12]
    chk = (11 - sum(int(c) * (10 - n) for n, c in enumerate(core)) % 11) % 11
    return core + ("X" if chk == 10 else str(chk))


def isbn_variants(raw):
    i = clean_isbn(raw)
    out = {i}
    for v in (isbn10_to_13(i), isbn13_to_10(i)):
        if v:
            out.add(v)
    return {v for v in out if v}


def as_list(v):
    return v if isinstance(v, list) else ([] if v in (None, "") else [v])


# ---------------------------------------------------------------- input parsing
def parse_free(line):
    isbn = ""
    m = ISBN_RE.search(line)
    if m:
        isbn = clean_isbn(m.group())
        line = (line[:m.start()] + " " + line[m.end():]).strip(" ,;-()[]")
    author = ""
    parts = re.split(r"\s+by\s+", line, maxsplit=1, flags=re.I)
    if len(parts) == 2:
        line, author = parts
    elif " - " in line:
        line, author = line.split(" - ", 1)
    return {"title": line.strip(), "author": author.strip(), "isbn": isbn}


def parse_input(text):
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return []
    first = lines[0].lower()
    if "," in first and ("title" in first or "isbn" in first):  # CSV with header
        rows = []
        for r in csv.DictReader(io.StringIO("\n".join(lines))):
            r = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}
            rows.append({
                "title": r.get("title") or r.get("book") or r.get("name", ""),
                "author": r.get("author") or r.get("authors") or r.get("creator", ""),
                "isbn": clean_isbn(r.get("isbn") or r.get("isbn13") or r.get("isbn10", "")),
            })
        return rows
    rows = []
    for l in lines:
        sep = "|" if "|" in l else ("\t" if "\t" in l else None)
        if sep:
            p = [x.strip() for x in l.split(sep)] + ["", ""]
            title, author, isbn = p[0], p[1], p[2]
            if ISBN_RE.fullmatch(author) and not isbn:  # "Title | ISBN"
                author, isbn = "", author
            rows.append({"title": title, "author": author, "isbn": clean_isbn(isbn)})
        else:
            rows.append(parse_free(l))
    return rows


# ---------------------------------------------------------------- ia search
def ia_search(query, rows=15, retries=3):
    cmd = ["ia", "search", query, "-p", f"rows:{rows}", "-p", "page:1"]
    for f in FIELDS:
        cmd += ["-f", f]
    for attempt in range(retries):
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode == 0:
            out = []
            for line in p.stdout.splitlines():
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
            return out
        time.sleep(2 * (attempt + 1))
    print(f"  ! ia search failed: {p.stderr.strip()[:200]}", file=sys.stderr)
    return None


def q(s):
    return LUCENE_SPECIAL.sub(r"\\\1", s)


def score(book, item):
    t = SequenceMatcher(None, norm(book["title"]), norm(item.get("title", ""))).ratio() if book["title"] else 0
    if not book["author"]:
        return round(t, 2)
    creators = " ".join(as_list(item.get("creator")))
    a_tokens = [w for w in norm(book["author"]).split() if len(w) > 1]
    hit = sum(w in norm(creators).split() for w in a_tokens) / len(a_tokens) if a_tokens else 0
    return round(0.7 * t + 0.3 * hit, 2)


def check(book, strict_types):
    """Return (status, match_by, best, score, candidates)."""
    mt = "" if not strict_types else " AND mediatype:texts"
    # 1. ISBN: exact, verified against the item's isbn list.
    if book["isbn"]:
        variants = isbn_variants(book["isbn"])
        qs = " OR ".join(f"isbn:{v}" for v in variants)
        items = ia_search(f"({qs}){mt}")
        if items is None:
            return "error", "", None, 0, []
        exact = [i for i in items if variants & {clean_isbn(x) for x in as_list(i.get("isbn"))}]
        if exact:
            return "match", "isbn", exact[0], 1.0, exact
    # 2. Title (+ author) search, scored by fuzzy similarity.
    if not book["title"]:
        return "not_found", "", None, 0, []
    title = re.sub(r"^(the|a|an)\s+", "", book["title"], flags=re.I)  # IA titles often omit the article
    query = f'title:("{q(title)}")'
    if book["author"]:
        toks = [q(w) for w in re.split(r"[\s,.]+", book["author"]) if len(w) > 1]
        if toks:
            query += " AND creator:(" + " AND ".join(toks) + ")"
    items = ia_search(query + mt)
    if items is None:
        return "error", "", None, 0, []
    if not items and book["author"]:  # retry title-only, author just affects score
        items = ia_search(f'title:("{q(title)}"){mt}') or []
    if not items:
        return "not_found", "", None, 0, []
    ranked = sorted(((score(book, i), i) for i in items), key=lambda x: -x[0])
    best_score, best = ranked[0]
    status = "match" if best_score >= 0.85 else "possible" if best_score >= 0.6 else "weak"
    return status, "title/author", best, best_score, [i for _, i in ranked]


def row_for(book, res):
    status, by, best, sc, cands = res
    r = {"input_title": book["title"], "input_author": book["author"], "input_isbn": book["isbn"],
         "status": status, "match_by": by, "score": sc, "num_candidates": len(cands)}
    if best:
        r.update(
            ia_identifier=best["identifier"],
            ia_url=f"https://archive.org/details/{best['identifier']}",
            ia_title=best.get("title", ""),
            ia_creator="; ".join(as_list(best.get("creator"))),
            ia_year=str(best.get("date", ""))[:4],
            ia_mediatype=best.get("mediatype", ""),
            other_candidates=" ".join(i["identifier"] for i in cands[1:4]),
        )
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", nargs="?", help="input file (default: stdin)")
    ap.add_argument("-o", "--output", help="output CSV (default: stdout)")
    ap.add_argument("--any-type", action="store_true", help="don't restrict to mediatype:texts")
    ap.add_argument("--delay", type=float, default=0.3, help="seconds between queries (default 0.3)")
    args = ap.parse_args()

    text = open(args.input, encoding="utf-8-sig").read() if args.input else sys.stdin.read()
    books = parse_input(text)
    out = open(args.output, "w", newline="", encoding="utf-8-sig") if args.output else sys.stdout
    w = csv.DictWriter(out, COLUMNS, restval="")
    w.writeheader()
    counts = {}
    for n, b in enumerate(books, 1):
        res = check(b, strict_types=not args.any_type)
        counts[res[0]] = counts.get(res[0], 0) + 1
        w.writerow(row_for(b, res))
        out.flush()
        label = b["title"] or b["isbn"]
        print(f"[{n}/{len(books)}] {res[0]:<9} {label[:60]}", file=sys.stderr)
        time.sleep(args.delay)
    print("Summary:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())), file=sys.stderr)


if __name__ == "__main__":
    main()
