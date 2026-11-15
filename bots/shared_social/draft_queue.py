"""Durable, local review decisions bound to exact content. No publishing capability."""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import html
import json
import os
from pathlib import Path
import sqlite3
import tempfile

from bots.shared_social.draft_images import render_images
from bots.shared_social.shopify_catalog import SHOP_DOMAIN, SHOP_ID
from bots.shared_social.shopify_drafts import make_drafts


def now():
    return datetime.now(timezone.utc).isoformat()


def revision(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


@contextmanager
def locked(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".queue.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield directory


def connect(directory):
    db = sqlite3.connect(Path(directory) / "queue.sqlite3")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    expected = {"brand": "mod_panic", "schema_version": "1", "shop_id": SHOP_ID}
    existing = dict(db.execute("SELECT key, value FROM metadata"))
    if existing and existing != expected:
        db.close()
        raise ValueError("Queue belongs to another brand, shop, or schema")
    if not existing:
        db.executemany("INSERT INTO metadata VALUES (?, ?)", expected.items())
    db.execute("""CREATE TABLE IF NOT EXISTS drafts (
        design_key TEXT PRIMARY KEY, draft_id TEXT NOT NULL UNIQUE,
        revision TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL,
        reviewer TEXT, reviewed_at TEXT, last_seen TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY, draft_id TEXT NOT NULL, revision TEXT NOT NULL,
        decision TEXT NOT NULL, reviewer TEXT NOT NULL, reviewed_at TEXT NOT NULL)""")
    db.execute("CREATE TABLE IF NOT EXISTS used_artworks (design_key TEXT PRIMARY KEY)")
    db.execute("""CREATE TABLE IF NOT EXISTS sync_runs (
        id INTEGER PRIMARY KEY, completed_at TEXT NOT NULL, fetched_at TEXT,
        product_count INTEGER NOT NULL, eligible_product_count INTEGER NOT NULL,
        artwork_count INTEGER NOT NULL)""")
    db.commit()
    return db


def validate_snapshot(snapshot):
    if (not isinstance(snapshot, dict) or snapshot.get("schema_version") != 1 or
            snapshot.get("brand") != "mod_panic" or snapshot.get("shop_id") != SHOP_ID or
            snapshot.get("shop_domain") != SHOP_DOMAIN or snapshot.get("complete") is not True or
            not isinstance(snapshot.get("products"), list)):
        raise ValueError("A complete snapshot of the pinned Mod Panic catalog is required")
    ids = [p.get("id") for p in snapshot["products"] if isinstance(p, dict)]
    if (len(ids) != len(snapshot["products"]) or not all(isinstance(i, str) and i for i in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError("Catalog contains invalid or duplicate products")
    # Missing fields are an incomplete response, not evidence of product deletion.
    for product in snapshot["products"]:
        if (not all(isinstance(product.get(k), str) for k in ("id", "title", "handle", "status", "vendor"))
                or not isinstance(product.get("tags"), list)
                or not all(isinstance(tag, str) for tag in product["tags"])
                or "onlineStoreUrl" not in product or "featuredMedia" not in product
                or product["onlineStoreUrl"] is not None and not isinstance(product["onlineStoreUrl"], str)):
            raise ValueError("Incomplete product data; keep the existing queue")
        node = product["featuredMedia"]
        for field in ("preview", "image", "url"):
            if node is None:
                break
            if not isinstance(node, dict) or field not in node:
                raise ValueError("Incomplete product media; keep the existing queue")
            node = node[field]
        if node is not None and not isinstance(node, str):
            raise ValueError("Invalid product image URL")
    fetched_at = snapshot.get("fetched_at")
    if fetched_at is not None:
        if not isinstance(fetched_at, str):
            raise ValueError("Invalid catalog timestamp")
        parsed = datetime.fromisoformat(fetched_at)
        if parsed.tzinfo is None:
            raise ValueError("Catalog timestamp must include its timezone")


def sync(snapshot, directory, *, overrides=None, previously_used=(), renderer=render_images, progress=None):
    used = set(previously_used)
    if progress:
        progress("Opening the local review queue; waiting if another refresh is running...")
    with locked(directory) as directory:
        # Live readers run inside the queue lock so overlapping refreshes cannot apply out of order.
        if progress and callable(snapshot):
            progress("Reading the complete Shopify catalog...")
        snapshot = snapshot() if callable(snapshot) else snapshot
        validate_snapshot(snapshot)
        # Build the whole eligible set before touching stored review decisions.
        drafts = make_drafts(snapshot["products"], overrides=overrides)
        if progress:
            progress(f"Read {len(snapshot['products'])} products. Preparing {len(drafts)} artwork drafts...")
        db = connect(directory)
        try:
            prepared = []
            for index, draft in enumerate(drafts, 1):
                payload = {k: v for k, v in draft.items() if k not in {"status", "approved"}}
                old = db.execute("SELECT payload, status FROM drafts WHERE design_key=?", (draft["design_key"],)).fetchone()
                generation = json.loads(old["payload"]).get("review_generation", 0) if old else 0
                if old and old["status"] == "withdrawn":
                    generation += 1
                if generation:
                    payload["review_generation"] = generation
                payload["images"] = renderer(draft, directory)
                prepared.append((draft, payload, revision(payload)))
                if progress and (index == 1 or index % 10 == 0 or index == len(drafts)):
                    progress(f"Prepared images for {index} of {len(drafts)} artwork drafts.")
            if progress:
                progress("Saving the complete review queue...")
            stamp = now()
            with db:
                db.executemany("INSERT OR IGNORE INTO used_artworks VALUES (?)", ((key,) for key in used))
                used.update(row[0] for row in db.execute("SELECT design_key FROM used_artworks"))
                current = {d[0]["design_key"] for d in prepared}
                for row in db.execute("SELECT * FROM drafts").fetchall():
                    if row["design_key"] not in current and row["status"] != "suppressed":
                        db.execute("UPDATE drafts SET status='withdrawn', reviewer=NULL, reviewed_at=NULL WHERE design_key=?",
                                   (row["design_key"],))
                for draft, payload, digest in prepared:
                    old = db.execute("SELECT * FROM drafts WHERE design_key=?", (draft["design_key"],)).fetchone()
                    status, reviewer, reviewed_at = "needs_review", None, None
                    if old and old["revision"] == digest and old["status"] in {"approved", "rejected", "suppressed"}:
                        status, reviewer, reviewed_at = old["status"], old["reviewer"], old["reviewed_at"]
                    if draft["design_key"] in used or (old and old["status"] == "suppressed"):
                        status, reviewer, reviewed_at = "suppressed", None, None
                    db.execute("""INSERT INTO drafts VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(design_key) DO UPDATE SET revision=excluded.revision,
                        payload=excluded.payload, status=excluded.status, reviewer=excluded.reviewer,
                        reviewed_at=excluded.reviewed_at, last_seen=excluded.last_seen""",
                               (draft["design_key"], draft["draft_id"], digest,
                                json.dumps(payload, ensure_ascii=False), status, reviewer, reviewed_at, stamp))
                db.execute("""INSERT INTO sync_runs
                    (completed_at, fetched_at, product_count, eligible_product_count, artwork_count)
                    VALUES (?, ?, ?, ?, ?)""",
                           (stamp, snapshot.get("fetched_at"), len(snapshot["products"]),
                            sum(len(d["products"]) for d in drafts), len(drafts)))
            return export(db, directory)
        finally:
            db.close()


def verify_assets(payload, directory):
    images = payload.get("images", {})
    if set(images) != {"facebook", "instagram"}:
        raise ValueError("Both platform images are required")
    for asset in images.values():
        path = (Path(directory) / asset["path"]).resolve()
        if Path(directory).resolve() not in path.parents or not path.is_file():
            raise ValueError("Draft image is missing or outside the queue")
        if hashlib.sha256(path.read_bytes()).hexdigest() != asset["sha256"]:
            raise ValueError("Draft image changed; regenerate and review again")


def review(directory, draft_id, expected_revision, decision, reviewer):
    if decision not in {"approved", "rejected"} or not reviewer.strip() or len(reviewer) > 120:
        raise ValueError("A decision and reviewer name are required")
    with locked(directory) as directory:
        db = connect(directory)
        try:
            row = db.execute("SELECT * FROM drafts WHERE draft_id=?", (draft_id,)).fetchone()
            if not row or row["status"] in {"withdrawn", "suppressed"}:
                raise ValueError("Draft is unavailable for review")
            payload = json.loads(row["payload"])
            if row["revision"] != expected_revision or revision(payload) != expected_revision:
                raise ValueError("Draft changed; review the current revision")
            verify_assets(payload, directory)
            stamp = now()
            with db:
                db.execute("UPDATE drafts SET status=?, reviewer=?, reviewed_at=? WHERE draft_id=?",
                           (decision, reviewer.strip(), stamp, draft_id))
                db.execute("INSERT INTO reviews (draft_id, revision, decision, reviewer, reviewed_at) VALUES (?, ?, ?, ?, ?)",
                           (draft_id, expected_revision, decision, reviewer.strip(), stamp))
            return export(db, directory)
        finally:
            db.close()


def atomic_write(path, text):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as out:
            temporary = Path(out.name)
            out.write(text)
            out.flush()
            os.fsync(out.fileno())
        temporary.replace(path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def export(db, directory):
    entries = []
    for row in db.execute("SELECT * FROM drafts ORDER BY design_key"):
        payload = json.loads(row["payload"])
        payload.update({"revision": row["revision"], "status": row["status"],
                        "approved": row["status"] == "approved", "reviewer": row["reviewer"],
                        "reviewed_at": row["reviewed_at"], "last_seen": row["last_seen"]})
        entries.append(payload)
    latest = db.execute("SELECT * FROM sync_runs ORDER BY id DESC LIMIT 1").fetchone()
    report = {"brand": "mod_panic", "publishing_enabled": False,
              "last_sync": dict(latest) if latest else None, "drafts": entries}
    atomic_write(Path(directory) / "review.json", json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    esc = html.escape
    cards = []
    for draft in entries:
        if draft["status"] in {"withdrawn", "suppressed"}:
            continue
        platforms = "".join(
            f'<div><h3>{p.title()}</h3><img src="{esc(draft["images"][p]["path"], quote=True)}" alt="{esc(draft["product_title"], quote=True)}"><pre>{esc(draft[p+"_caption"])}</pre></div>'
            for p in ("facebook", "instagram"))
        links = " · ".join(f'<a href="{esc(p["url"], quote=True)}" rel="noreferrer">{esc(p["title"])}</a>' for p in draft["products"])
        cards.append(f'<article><h2>{esc(draft["design_key"])}</h2><p>{esc(draft["status"])} · {len(draft["products"])} products</p><div class="platforms">{platforms}</div><p>{links}</p><p>{esc(draft["review_notes"][0])}</p><details><summary>Review identifiers</summary><p>ID: {draft["draft_id"]}</p><p>Revision: {draft["revision"]}</p></details></article>')
    document = '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Mod Panic draft review</title><style>
body{font:17px system-ui;background:#f3eee4;color:#182626;max-width:1280px;margin:40px auto;padding:0 24px}
article{background:white;padding:28px;margin:30px 0;border-radius:16px}.platforms{display:grid;grid-template-columns:1fr 1fr;gap:30px}img{max-width:100%;max-height:570px;object-fit:contain}pre{white-space:pre-wrap;font:inherit;line-height:1.5}a{color:#245b64}details{overflow-wrap:anywhere}@media(max-width:700px){.platforms{grid-template-columns:1fr}}
</style><h1>Mod Panic · Draft review</h1><p>Review-only queue. Publishing is disabled. Approval records a local decision; it cannot send a post.</p>'''
    if latest:
        freshness = f'<p>Last successful queue refresh: <time>{esc(latest["completed_at"])}</time>.</p>'
        if latest["fetched_at"]:
            freshness += f'<p>Shopify catalog retrieved: <time>{esc(latest["fetched_at"])}</time>.</p>'
        else:
            freshness += '<p>Imported catalog snapshot; its retrieval time was not recorded.</p>'
        freshness += f'<p>{latest["product_count"]} products checked · {latest["eligible_product_count"]} eligible products · {latest["artwork_count"]} artwork groups.</p>'
    else:
        freshness = '<p>No refresh time has been recorded for this existing queue.</p>'
    freshness += '<p>Schedules are disabled. Product changes appear after a successful full refresh; reload this page afterward. Deleted products are removed from active drafts, and changed drafts require review again.</p>'
    atomic_write(Path(directory) / "review.html", document + freshness + "".join(cards) + "</html>")
    return report
