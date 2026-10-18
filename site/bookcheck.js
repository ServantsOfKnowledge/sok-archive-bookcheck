/* Browser port of bookcheck.py: same parsing, ISBN handling, search and scoring.
   Calls the Internet Archive advancedsearch API directly (CORS-enabled). */
(function (root) {
  const FIELDS = ["identifier", "title", "creator", "date", "isbn", "mediatype", "language"];
  const COLUMNS = [
    "input_title", "input_author", "input_isbn",
    "status", "match_by", "score", "num_candidates",
    "ia_identifier", "ia_url", "ia_title", "ia_creator", "ia_year", "ia_mediatype",
    "other_candidates",
  ];
  const ISBN_RE = /\b(?:97[89][- ]?)?\d(?:[- ]?\d){8}[- ]?[\dXx]\b/;
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const asList = v => Array.isArray(v) ? v : (v == null || v === "" ? [] : [v]);
  const norm = s => (s || "").toLowerCase().replace(/\s+/g, " ").replace(/[^a-z0-9 ]/g, "").trim();
  const cleanIsbn = s => (s || "").replace(/[^0-9Xx]/g, "").toUpperCase();
  const q = s => s.replace(/([+\-&|!(){}\[\]^"~*?:\\/])/g, "\\$1");
  const round2 = x => Math.round(x * 100) / 100;

  function isbn10to13(i) {
    if (!/^\d{9}[\dX]$/.test(i)) return null;
    const core = "978" + i.slice(0, 9);
    let sum = 0;
    for (let n = 0; n < 12; n++) sum += Number(core[n]) * (n % 2 === 0 ? 1 : 3);
    return core + ((10 - sum % 10) % 10);
  }
  function isbn13to10(i) {
    if (!/^978\d{10}$/.test(i)) return null;
    const core = i.slice(3, 12);
    let sum = 0;
    for (let n = 0; n < 9; n++) sum += Number(core[n]) * (10 - n);
    const chk = (11 - sum % 11) % 11;
    return core + (chk === 10 ? "X" : chk);
  }
  function isbnVariants(raw) {
    const i = cleanIsbn(raw), out = new Set([i]);
    for (const v of [isbn10to13(i), isbn13to10(i)]) if (v) out.add(v);
    out.delete("");
    return out;
  }

  // ---- difflib.SequenceMatcher.ratio() equivalent (no junk heuristics; titles are short)
  function matches(a, alo, ahi, b, blo, bhi) {
    let best = 0, bi = alo, bj = blo, prev = new Array(bhi - blo + 1).fill(0);
    for (let i = alo; i < ahi; i++) {
      const cur = new Array(bhi - blo + 1).fill(0);
      for (let j = blo; j < bhi; j++) {
        if (a[i] === b[j]) {
          const k = prev[j - blo] + 1;
          cur[j - blo + 1] = k;
          if (k > best) { best = k; bi = i - k + 1; bj = j - k + 1; }
        }
      }
      prev = cur;
    }
    if (!best) return 0;
    return best + matches(a, alo, bi, b, blo, bj) + matches(a, bi + best, ahi, b, bj + best, bhi);
  }
  function ratio(a, b) {
    const n = a.length + b.length;
    return n ? 2 * matches(a, 0, a.length, b, 0, b.length) / n : 1;
  }

  // ---- input parsing
  function parseFree(line) {
    let isbn = "", author = "";
    const m = line.match(ISBN_RE);
    if (m) {
      isbn = cleanIsbn(m[0]);
      line = (line.slice(0, m.index) + " " + line.slice(m.index + m[0].length)).replace(/^[\s,;\-()\[\]]+|[\s,;\-()\[\]]+$/g, "");
    }
    const by = line.match(/\s+by\s+/i);
    if (by) { author = line.slice(by.index + by[0].length); line = line.slice(0, by.index); }
    else if (line.includes(" - ")) { const k = line.indexOf(" - "); author = line.slice(k + 3); line = line.slice(0, k); }
    return { title: line.trim(), author: author.trim(), isbn };
  }

  function parseCSV(text) {
    const rows = []; let row = [], f = "", inq = false;
    text = text.replace(/^﻿/, "");
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (inq) {
        if (c === '"') { if (text[i + 1] === '"') { f += '"'; i++; } else inq = false; } else f += c;
      } else if (c === '"') inq = true;
      else if (c === ",") { row.push(f); f = ""; }
      else if (c === "\n" || c === "\r") {
        if (c === "\r" && text[i + 1] === "\n") i++;
        row.push(f); f = ""; rows.push(row); row = [];
      } else f += c;
    }
    if (f !== "" || row.length) { row.push(f); rows.push(row); }
    return rows.filter(r => r.some(x => x.trim() !== ""));
  }

  function parseInput(text) {
    const lines = text.split(/\r?\n/).filter(l => l.trim());
    if (!lines.length) return [];
    const first = lines[0].toLowerCase();
    if (first.includes(",") && (first.includes("title") || first.includes("isbn"))) {
      const [head, ...body] = parseCSV(lines.join("\n"));
      const keys = head.map(h => h.trim().toLowerCase());
      return body.map(cells => {
        const r = {}; keys.forEach((k, i) => r[k] = (cells[i] || "").trim());
        return {
          title: r.title || r.book || r.name || "",
          author: r.author || r.authors || r.creator || "",
          isbn: cleanIsbn(r.isbn || r.isbn13 || r.isbn10 || ""),
        };
      });
    }
    return lines.map(l => {
      const sep = l.includes("|") ? "|" : (l.includes("\t") ? "\t" : null);
      if (!sep) return parseFree(l);
      const p = l.split(sep).map(x => x.trim()).concat(["", ""]);
      let [title, author, isbn] = p;
      if (new RegExp("^(?:" + ISBN_RE.source + ")$").test(author) && !isbn) { isbn = author; author = ""; }
      return { title, author, isbn: cleanIsbn(isbn) };
    });
  }

  // ---- Internet Archive search
  async function iaSearch(query, rows = 15) {
    const p = new URLSearchParams({ q: query, rows, page: 1, output: "json" });
    FIELDS.forEach(f => p.append("fl[]", f));
    for (let a = 0; a < 3; a++) {
      try {
        const r = await fetch("https://archive.org/advancedsearch.php?" + p);
        if (r.ok) return (await r.json()).response.docs;
      } catch (e) { /* retry */ }
      await sleep(2000 * (a + 1));
    }
    return null;
  }

  function score(book, item) {
    const t = book.title ? ratio(norm(book.title), norm(item.title || "")) : 0;
    if (!book.author) return round2(t);
    const creators = norm(asList(item.creator).join(" ")).split(" ");
    const toks = norm(book.author).split(" ").filter(w => w.length > 1);
    const hit = toks.length ? toks.filter(w => creators.includes(w)).length / toks.length : 0;
    return round2(0.7 * t + 0.3 * hit);
  }

  const result = (status, by = "", best = null, sc = 0, cands = []) => ({ status, by, best, score: sc, cands });

  async function check(book, strict = true) {
    const mt = strict ? " AND mediatype:texts" : "";
    if (book.isbn) {
      const variants = isbnVariants(book.isbn);
      const items = await iaSearch(`(${[...variants].map(v => "isbn:" + v).join(" OR ")})${mt}`);
      if (items === null) return result("error");
      const exact = items.filter(i => asList(i.isbn).some(x => variants.has(cleanIsbn(x))));
      if (exact.length) return result("match", "isbn", exact[0], 1.0, exact);
    }
    if (!book.title) return result("not_found");
    const title = book.title.replace(/^(the|a|an)\s+/i, "");
    let query = `title:("${q(title)}")`;
    if (book.author) {
      const toks = book.author.split(/[\s,.]+/).filter(w => w.length > 1).map(q);
      if (toks.length) query += " AND creator:(" + toks.join(" AND ") + ")";
    }
    let items = await iaSearch(query + mt);
    if (items === null) return result("error");
    if (!items.length && book.author) items = (await iaSearch(`title:("${q(title)}")${mt}`)) || [];
    if (!items.length) return result("not_found");
    const ranked = items.map(i => [score(book, i), i]).sort((a, b) => b[0] - a[0]);
    const [bs, best] = ranked[0];
    return result(bs >= 0.85 ? "match" : bs >= 0.6 ? "possible" : "weak", "title/author", best, bs, ranked.map(x => x[1]));
  }

  const candSummary = i => ({
    identifier: i.identifier, title: i.title || "", creator: asList(i.creator).join("; "),
    year: String(i.date || "").slice(0, 4), mediatype: i.mediatype || "",
  });

  function rowFor(book, res) {
    const r = {
      input_title: book.title, input_author: book.author, input_isbn: book.isbn,
      status: res.status, match_by: res.by, score: res.score, num_candidates: res.cands.length,
      ia_identifier: "", ia_url: "", ia_title: "", ia_creator: "", ia_year: "", ia_mediatype: "", other_candidates: "",
      candidates: res.cands.slice(0, 5).map(candSummary),
    };
    if (res.best) {
      const c = candSummary(res.best);
      Object.assign(r, {
        ia_identifier: c.identifier, ia_url: "https://archive.org/details/" + c.identifier,
        ia_title: c.title, ia_creator: c.creator, ia_year: c.year, ia_mediatype: c.mediatype,
        other_candidates: res.cands.slice(1, 4).map(i => i.identifier).join(" "),
      });
    }
    return r;
  }

  // Rebuild a row object from a CSV record (for re-importing downloaded results).
  function rowFromCSV(r) {
    const d = {};
    COLUMNS.forEach(c => d[c] = r[c] || "");
    d.score = parseFloat(d.score) || 0;
    d.num_candidates = parseInt(d.num_candidates, 10) || 0;
    const ids = (d.ia_identifier ? [d.ia_identifier] : []).concat(d.other_candidates.split(/\s+/).filter(Boolean));
    d.candidates = ids.map(i => {
      const own = i === d.ia_identifier;
      return { identifier: i, title: own ? d.ia_title : "", creator: own ? d.ia_creator : "", year: own ? d.ia_year : "", mediatype: own ? d.ia_mediatype : "" };
    });
    const v = (r.verdict || "").trim();
    d.verdict = v === "ok" || v === "no" ? v : "";
    return d;
  }

  const api = { COLUMNS, parseInput, parseCSV, check, rowFor, rowFromCSV, ratio, norm, isbnVariants, candSummary, sleep };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.BC = api;
})(typeof self !== "undefined" ? self : globalThis);
