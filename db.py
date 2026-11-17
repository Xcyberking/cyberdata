import os,sqlite3
from contextlib import contextmanager
DB_PATH=os.getenv("DATABASE_PATH","/data/cyberdata.sqlite")
@contextmanager
def conn():
 os.makedirs(os.path.dirname(DB_PATH) or ".",exist_ok=True)
 c=sqlite3.connect(DB_PATH,timeout=30);c.row_factory=sqlite3.Row
 try:
  c.execute("PRAGMA journal_mode=WAL");c.execute("PRAGMA synchronous=FULL")
  yield c
  c.commit()
 finally:c.close()
def init_db():
 with conn() as c:
  c.execute("""CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,drive_url TEXT NOT NULL,object_key TEXT NOT NULL,status TEXT NOT NULL,progress REAL DEFAULT 0,total_bytes INTEGER DEFAULT 0,uploaded_bytes INTEGER DEFAULT 0,total_parts INTEGER DEFAULT 0,upload_id TEXT,message TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
  c.execute("""CREATE TABLE IF NOT EXISTS parts(job_id TEXT NOT NULL,part_number INTEGER NOT NULL,etag TEXT NOT NULL,size INTEGER NOT NULL,PRIMARY KEY(job_id,part_number))""")
def create_job(jid,url,key):
 with conn() as c:c.execute("INSERT INTO jobs(id,drive_url,object_key,status,message) VALUES(?,?,?,'queued','Queued')",(jid,url,key))
def get_job(jid):
 with conn() as c:
  r=c.execute("SELECT * FROM jobs WHERE id=?",(jid,)).fetchone()
  return dict(r) if r else None
def list_active():
 with conn() as c:return [dict(r) for r in c.execute("SELECT * FROM jobs WHERE status IN ('queued','running')")]
def update(jid,**kw):
 allowed={"status","progress","total_bytes","uploaded_bytes","total_parts","upload_id","message"}
 d={k:v for k,v in kw.items() if k in allowed}
 if d:
  cols=",".join(k+"=?" for k in d)
  with conn() as c:c.execute("UPDATE jobs SET "+cols+",updated_at=CURRENT_TIMESTAMP WHERE id=?",(*d.values(),jid))
def save_part(jid,n,etag,size):
 with conn() as c:c.execute("INSERT OR REPLACE INTO parts(job_id,part_number,etag,size) VALUES(?,?,?,?)",(jid,n,etag,size))
def get_parts(jid):
 with conn() as c:return [dict(r) for r in c.execute("SELECT * FROM parts WHERE job_id=? ORDER BY part_number",(jid,))]
