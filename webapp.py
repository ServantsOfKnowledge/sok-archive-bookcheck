#!/usr/bin/env python3
"""Local web UI for bookcheck.py with IA thumbnails, manual verification and SQLite history.

Run: python3 webapp.py [port]  ->  http://127.0.0.1:8765
"""
import csv
import io
import json
import re
import sqlite3
import sys
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import bookcheck as bc

DB_PATH = Path(__file__).with_name("books.db")
CSV_COLUMNS = bc.COLUMNS + ["verdict"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL,
  total INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS rows(
  id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  idx INTEGER NOT NULL, data TEXT NOT NULL, verdict TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS rows_run ON rows(run_id, idx);
"""


def db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c


def init_db():
    with db() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)


def cand_summary(i):
    return {"identifier": i["identifier"], "title": i.get("title", ""),
            "creator": "; ".join(bc.as_list(i.get("creator"))),
            "year": str(i.get("date", ""))[:4], "mediatype": i.get("mediatype", "")}


def row_obj(r):
    d = json.loads(r["data"])
    d["id"], d["verdict"] = r["id"], r["verdict"]
    return d


def import_csv(text, name):
    """Create a run from a CSV previously exported by this app (or bookcheck.py)."""
    rdr = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    if not rdr.fieldnames or not {"input_title", "status"} <= set(rdr.fieldnames):
        raise ValueError("Not a results CSV: expected input_title and status columns")
    rows = []
    for r in rdr:
        d = {c: (r.get(c) or "") for c in bc.COLUMNS}
        d["score"] = float(d["score"] or 0)
        d["num_candidates"] = int(d["num_candidates"] or 0)
        ids = ([d["ia_identifier"]] if d["ia_identifier"] else []) + d["other_candidates"].split()
        d["candidates"] = [{"identifier": i, "title": d["ia_title"] if i == d["ia_identifier"] else "",
                            "creator": d["ia_creator"] if i == d["ia_identifier"] else "",
                            "year": d["ia_year"] if i == d["ia_identifier"] else "",
                            "mediatype": d["ia_mediatype"] if i == d["ia_identifier"] else ""} for i in ids]
        v = (r.get("verdict") or "").strip()
        rows.append((d, v if v in ("ok", "no") else ""))
    with db() as c:
        run_id = c.execute("INSERT INTO runs(name, created_at, total) VALUES(?,?,?)",
                           (name, datetime.now().isoformat(timespec="seconds"), len(rows))).lastrowid
        c.executemany("INSERT INTO rows(run_id, idx, data, verdict) VALUES(?,?,?,?)",
                      [(run_id, i, json.dumps(d), v) for i, (d, v) in enumerate(rows)])
    return run_id


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ServantsOfKnowledge · Archive Book Check</title>
<link rel="icon" type="image/png" href="/static/favicon.png">
<style>
:root{--bg:#fafaf8;--fg:#1c1c1a;--mut:#6b6b66;--card:#fff;--bd:#dddcd6;--acc:#9a6b1f;--ok:#1f7a3d;--warn:#a86a00;--bad:#8a8a85;--err:#b3261e;--okbg:#e8f5ec;--rejbg:#fbeaea}
@media(prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ecebe6;--mut:#9a9a93;--card:#202020;--bd:#363632;--acc:#e0b25a;--ok:#5fd18a;--warn:#e0a63a;--bad:#8a8a85;--err:#ff8a80;--okbg:#17301f;--rejbg:#3a1f1f}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
main{max-width:1150px;margin:0 auto;padding:24px 16px 60px}
h1{font-size:22px;margin:0 0 4px}p.sub{color:var(--mut);margin:0 0 16px}
textarea,input[type=text],select{padding:8px 10px;border:1px solid var(--bd);border-radius:8px;background:var(--card);color:var(--fg);font:inherit}
textarea{width:100%;height:160px;font:13px/1.5 ui-monospace,monospace;resize:vertical}
.bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:10px 0}
button,label.btn{padding:8px 14px;border-radius:8px;border:1px solid var(--bd);background:var(--card);color:var(--fg);font:inherit;cursor:pointer}
button.pri{background:var(--acc);border-color:var(--acc);color:#fff}@media(prefers-color-scheme:dark){button.pri{color:#1a1206}}
.brand{display:flex;align-items:center;gap:14px;margin-bottom:14px}.brand img{width:56px;height:56px;border-radius:50%}.brand h1{margin:0;font-size:22px;line-height:1.2}.brand p{margin:0;color:var(--mut)}button:disabled{opacity:.5;cursor:default}
#prog{flex:1;min-width:120px;height:8px;background:var(--bd);border-radius:4px;overflow:hidden}#prog i{display:block;height:100%;width:0;background:var(--acc);transition:width .2s}
#sum{color:var(--mut)}
.wrap{overflow-x:auto;border:1px solid var(--bd);border-radius:8px;background:var(--card);margin-top:8px}
table{border-collapse:collapse;width:100%;font-size:13.5px}th,td{padding:8px 10px;text-align:left;border-bottom:1px solid var(--bd);vertical-align:top}
th{background:var(--card);color:var(--mut);font-weight:600;white-space:nowrap}
tr.v-ok td{background:var(--okbg)}tr.v-no td{background:var(--rejbg)}
.s{font-weight:600}.s.match{color:var(--ok)}.s.possible,.s.weak{color:var(--warn)}.s.not_found{color:var(--bad)}.s.error{color:var(--err)}
.mut{color:var(--mut);font-size:12.5px}
.thumb{width:72px;height:100px;object-fit:contain;background:var(--bd);border-radius:4px;display:block}
.alts{display:flex;gap:4px;margin-top:6px}.alts img{width:34px;height:48px;object-fit:contain;background:var(--bd);border-radius:3px;cursor:pointer;border:1px solid transparent}.alts img:hover{border-color:var(--acc)}
.vb{display:flex;gap:6px}.vb button{padding:4px 10px;font-size:16px}.vb button.on.y{background:var(--ok);color:#fff;border-color:var(--ok)}.vb button.on.n{background:var(--err);color:#fff;border-color:var(--err)}
.none{width:72px;height:100px;border:1px dashed var(--bd);border-radius:4px;display:grid;place-items:center;color:var(--mut);font-size:11px}
a{color:var(--acc)}
</style></head><body><main>
<div class="brand"><img src="/static/sok-logo.png" alt="ServantsOfKnowledge"><div><h1>ServantsOfKnowledge</h1><p>Archive Book Check</p></div></div>
<p class="sub">Paste one book per line (<code>Title | Author | ISBN</code>, free text, or CSV with a header). Each run is saved so you can reopen it later.</p>
<div class="bar">
 <select id="runs" style="min-width:260px"></select>
 <label class="btn" title="Reopen a results CSV you downloaded earlier">Import CSV<input id="imp" type="file" accept=".csv,text/csv" hidden></label>
 <button id="ren">Rename</button><button id="del">Delete</button>
</div>
<textarea id="in" placeholder="Pride and Prejudice | Jane Austen | 9780141439518&#10;Gitanjali by Rabindranath Tagore&#10;Moby Dick by Herman Melville 0142437247"></textarea>
<div class="bar">
 <input type="text" id="name" placeholder="Run name" size="26">
 <button class="pri" id="go">Check books</button>
 <label class="btn">Load file<input id="file" type="file" accept=".txt,.csv,text/*" hidden></label>
 <label><input type="checkbox" id="any"> any media type</label>
 <div id="prog"><i></i></div><span id="sum"></span>
</div>
<div class="bar">
 <select id="filter">
  <option value="all">Show all</option><option value="todo">Needs review</option>
  <option value="ok">Verified</option><option value="no">Rejected</option><option value="nf">Not found</option>
 </select>
 <button id="dl" disabled>Download CSV</button>
</div>
<div class="wrap"><table><thead><tr><th>Cover</th><th>Your input</th><th>Result</th><th>Archive match</th><th>Verify</th></tr></thead><tbody id="body"></tbody></table></div>
</main>
<script>
const CSV_COLS=%COLS%;
const $=id=>document.getElementById(id);let runId=null,rows=[];
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const img=(id,cls)=>`<img class="${cls}" loading="lazy" src="https://archive.org/services/img/${encodeURIComponent(id)}" alt="" onerror="this.style.opacity=.2">`;
const stamp=()=>"Run "+new Date().toLocaleString("sv").slice(0,16);
async function api(method,url,body,raw){const r=await fetch(url,{method,body:body===undefined?undefined:raw?body:JSON.stringify(body)});if(!r.ok)throw new Error(await r.text());return r.json()}

function rowHtml(r){
 const alts=(r.candidates||[]).filter(c=>c.identifier!==r.ia_identifier).slice(0,4);
 return `<td>${r.ia_identifier?`<a href="${esc(r.ia_url)}" target="_blank" rel="noopener">${img(r.ia_identifier,"thumb")}</a>`:'<div class="none">no match</div>'}</td>
 <td><b>${esc(r.input_title)}</b><div class="mut">${esc(r.input_author)}</div><div class="mut">${esc(r.input_isbn)}</div></td>
 <td><span class="s ${esc(r.status)}">${esc(r.status)}</span><div class="mut">${esc(r.match_by)} ${r.score?("· "+r.score):""}</div></td>
 <td>${r.ia_identifier?`<a href="${esc(r.ia_url)}" target="_blank" rel="noopener">${esc(r.ia_title)}</a>
   <div class="mut">${esc(r.ia_creator)} ${r.ia_year?("· "+esc(r.ia_year)):""}</div><div class="mut">${esc(r.ia_identifier)}</div>`:""}
   ${alts.length?`<div class="alts" title="Click to use this one instead">${alts.map(c=>`<img loading="lazy" data-pick="${esc(c.identifier)}" title="${esc(c.title)} — ${esc(c.creator)} ${esc(c.year)}" src="https://archive.org/services/img/${encodeURIComponent(c.identifier)}" alt="">`).join("")}</div>`:""}</td>
 <td><div class="vb"><button class="y ${r.verdict==="ok"?"on":""}" data-v="ok" title="Correct match">✓</button><button class="n ${r.verdict==="no"?"on":""}" data-v="no" title="Wrong match">✗</button></div></td>`}

function matchesFilter(r){const f=$("filter").value;
 return f==="all"||(f==="todo"&&!r.verdict&&r.status!=="not_found")||(f==="ok"&&r.verdict==="ok")||(f==="no"&&r.verdict==="no")||(f==="nf"&&r.status==="not_found")}
function paint(tr,r){tr.className=r.verdict==="ok"?"v-ok":r.verdict==="no"?"v-no":"";tr.innerHTML=rowHtml(r);tr.hidden=!matchesFilter(r)}
function addRow(r){rows.push(r);const tr=document.createElement("tr");tr.dataset.id=r.id;paint(tr,r);$("body").appendChild(tr)}
function summary(){const c={};rows.forEach(r=>c[r.status]=(c[r.status]||0)+1);
 const v=rows.filter(r=>r.verdict==="ok").length,x=rows.filter(r=>r.verdict==="no").length;
 return `${rows.length} books · `+Object.entries(c).map(([k,n])=>k+" "+n).join(", ")+` · verified ${v}, rejected ${x}`}

$("body").onclick=async e=>{
 const tr=e.target.closest("tr");if(!tr)return;const r=rows.find(x=>x.id==tr.dataset.id);
 const v=e.target.closest("button")?.dataset.v,pick=e.target.dataset.pick;
 if(v){const nv=r.verdict===v?"":v;await api("POST","/api/rows/"+r.id,{verdict:nv});r.verdict=nv}
 else if(pick){Object.assign(r,await api("POST","/api/rows/"+r.id,{pick}))}
 else return;
 paint(tr,r);$("sum").textContent=summary()};
$("filter").onchange=()=>[...$("body").children].forEach(tr=>tr.hidden=!matchesFilter(rows.find(x=>x.id==tr.dataset.id)));

async function loadRuns(select){
 const list=await api("GET","/api/runs");
 $("runs").innerHTML='<option value="">— saved runs —</option>'+list.map(r=>`<option value="${r.id}">${esc(r.name)} (${r.n} books, ${r.verified} verified)</option>`).join("");
 if(select)$("runs").value=select}
$("runs").onchange=async()=>{const id=$("runs").value;if(!id)return;
 const d=await api("GET","/api/runs/"+id);runId=d.id;$("name").value=d.name;rows=[];$("body").innerHTML="";
 d.rows.forEach(addRow);$("sum").textContent=summary();$("prog").firstChild.style.width="100%";$("dl").disabled=!rows.length};
$("ren").onclick=async()=>{if(!runId)return;const n=prompt("New name",$("name").value);if(!n)return;
 await api("POST","/api/runs/"+runId,{name:n});$("name").value=n;loadRuns(runId)};
$("del").onclick=async()=>{if(!runId||!confirm("Delete this run and its results?"))return;
 await api("DELETE","/api/runs/"+runId);runId=null;rows=[];$("body").innerHTML="";$("sum").textContent="";$("dl").disabled=true;loadRuns()};

$("imp").onchange=async e=>{const f=e.target.files[0];e.target.value="";if(!f)return;
 try{const r=await api("POST","/api/import?name="+encodeURIComponent(f.name.replace(/\.\w+$/,"")),await f.text(),true);
  await loadRuns(r.run);$("runs").onchange()}catch(err){alert("Import failed: "+err.message)}};
$("file").onchange=async e=>{const f=e.target.files[0];if(f){$("in").value=await f.text();if(!$("name").value)$("name").value=f.name.replace(/\.\w+$/,"")}};
$("go").onclick=async()=>{
 if(!$("in").value.trim())return;
 const name=$("name").value.trim()||stamp();$("name").value=name;
 rows=[];$("body").innerHTML="";$("dl").disabled=true;$("go").disabled=true;$("sum").textContent="Starting…";$("prog").firstChild.style.width="0";
 let total=0;
 try{const res=await fetch("/api/check?any="+($("any").checked?1:0)+"&name="+encodeURIComponent(name),{method:"POST",body:$("in").value});
  const rd=res.body.getReader(),dec=new TextDecoder();let buf="";
  for(;;){const {done,value}=await rd.read();if(done)break;buf+=dec.decode(value,{stream:true});
   let i;while((i=buf.indexOf("\n"))>=0){const line=buf.slice(0,i);buf=buf.slice(i+1);if(!line)continue;const m=JSON.parse(line);
    if(m.run!==undefined){runId=m.run;total=m.total;continue}
    addRow(m);$("prog").firstChild.style.width=(100*rows.length/total)+"%";$("sum").textContent=`${rows.length}/${total} · `+summary()}}
 }catch(e){$("sum").textContent="Error: "+e.message}
 $("go").disabled=false;$("dl").disabled=!rows.length;$("sum").textContent=summary();loadRuns(runId)};

$("dl").onclick=()=>{const q=v=>`"${String(v??"").replace(/"/g,'""')}"`;
 const csv="﻿"+[CSV_COLS.join(","),...rows.map(r=>CSV_COLS.map(c=>q(r[c])).join(","))].join("\r\n");
 const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([csv],{type:"text/csv"}));
 a.download=($("name").value||"book_matches").replace(/[^\w.-]+/g,"_")+".csv";a.click()};
loadRuns();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        return self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8", "replace")

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            body = PAGE.replace("%COLS%", json.dumps(CSV_COLUMNS)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif m := re.fullmatch(r"/static/([\w.-]+\.png)", path):
            f = Path(__file__).with_name("static") / m[1]
            if not f.is_file():
                return self._json({"error": "not found"}, 404)
            body = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Cache-Control", "max-age=3600")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/runs":
            with db() as c:
                rs = c.execute("""SELECT r.id, r.name, r.created_at, COUNT(w.id) n,
                    COALESCE(SUM(w.verdict='ok'),0) verified FROM runs r
                    LEFT JOIN rows w ON w.run_id=r.id GROUP BY r.id ORDER BY r.id DESC""").fetchall()
            self._json([dict(r) for r in rs])
        elif m := re.fullmatch(r"/api/runs/(\d+)", path):
            with db() as c:
                run = c.execute("SELECT * FROM runs WHERE id=?", (m[1],)).fetchone()
                if not run:
                    return self._json({"error": "not found"}, 404)
                rs = c.execute("SELECT * FROM rows WHERE run_id=? ORDER BY idx", (m[1],)).fetchall()
            self._json({"id": run["id"], "name": run["name"], "rows": [row_obj(r) for r in rs]})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        url = urlparse(self.path)
        if url.path == "/api/check":
            return self._check(url)
        text = self._body()
        if url.path == "/api/import":
            name = (parse_qs(url.query).get("name", [""])[0] or "Imported CSV").strip()
            try:
                return self._json({"run": import_csv(text, name)})
            except (ValueError, KeyError) as e:
                return self._json({"error": str(e)}, 400)
        data = json.loads(text) if text else {}
        if m := re.fullmatch(r"/api/runs/(\d+)", url.path):
            with db() as c:
                c.execute("UPDATE runs SET name=? WHERE id=?", (data["name"], m[1]))
            return self._json({"ok": True})
        if m := re.fullmatch(r"/api/rows/(\d+)", url.path):
            with db() as c:
                r = c.execute("SELECT * FROM rows WHERE id=?", (m[1],)).fetchone()
                if not r:
                    return self._json({"error": "not found"}, 404)
                d = json.loads(r["data"])
                verdict = r["verdict"]
                if "verdict" in data:
                    verdict = data["verdict"] if data["verdict"] in ("", "ok", "no") else ""
                if pick := data.get("pick"):
                    cand = next((x for x in d.get("candidates", []) if x["identifier"] == pick), None)
                    if cand:
                        d.update(ia_identifier=cand["identifier"], ia_url=f"https://archive.org/details/{cand['identifier']}",
                                 ia_title=cand["title"], ia_creator=cand["creator"], ia_year=cand["year"],
                                 ia_mediatype=cand["mediatype"], match_by="manual", status="possible", score=0)
                c.execute("UPDATE rows SET data=?, verdict=? WHERE id=?", (json.dumps(d), verdict, m[1]))
            d["id"], d["verdict"] = int(m[1]), verdict
            return self._json(d)
        self._json({"error": "not found"}, 404)

    def do_DELETE(self):
        if m := re.fullmatch(r"/api/runs/(\d+)", urlparse(self.path).path):
            with db() as c:
                c.execute("DELETE FROM runs WHERE id=?", (m[1],))
            return self._json({"ok": True})
        self._json({"error": "not found"}, 404)

    def _check(self, url):
        qs = parse_qs(url.query)
        strict = qs.get("any", ["0"])[0] != "1"
        name = (qs.get("name", [""])[0] or "Run " + datetime.now().strftime("%Y-%m-%d %H:%M")).strip()
        books = bc.parse_input(self._body())
        with db() as c:
            run_id = c.execute("INSERT INTO runs(name, created_at, total) VALUES(?,?,?)",
                               (name, datetime.now().isoformat(timespec="seconds"), len(books))).lastrowid
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        alive = True

        def emit(o):  # keep working (and saving) even if the browser goes away
            nonlocal alive
            if alive:
                try:
                    self.wfile.write(json.dumps(o).encode() + b"\n")
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    alive = False

        emit({"run": run_id, "total": len(books)})
        for idx, b in enumerate(books):
            res = bc.check(b, strict_types=strict)
            row = bc.row_for(b, res)
            row["candidates"] = [cand_summary(i) for i in res[4][:5]]
            with db() as c:
                rid = c.execute("INSERT INTO rows(run_id, idx, data) VALUES(?,?,?)",
                                (run_id, idx, json.dumps(row))).lastrowid
            row["id"], row["verdict"] = rid, ""
            emit(row)
            time.sleep(0.2)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    init_db()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"Open http://127.0.0.1:{port}  (Ctrl-C to stop)  — data in {DB_PATH}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
