import os,uuid
from flask import Flask,request,jsonify,render_template
from dotenv import load_dotenv
load_dotenv()
import db
from transfer import launch,resume_active
from storage import get_s3,bucket_name
app=Flask(__name__);db.init_db()
def authorized():
 expected=os.getenv("ADMIN_API_KEY","")
 return bool(expected) and request.headers.get("X-Admin-Key","")==expected
@app.get("/")
def home():return render_template("index.html")
@app.get("/health")
def health():return jsonify(ok=True,service="CyberData")
@app.post("/api/transfer/start")
def start():
 if not authorized():return jsonify(error="Unauthorized. Configure ADMIN_API_KEY."),401
 d=request.get_json(silent=True) or {};url=(d.get("drive_url") or os.getenv("GOOGLE_DRIVE_URL","")).strip()
 key=(d.get("object_key") or os.getenv("HF_OBJECT_KEY","data.json")).strip().lstrip("/")
 if not url:return jsonify(error="Google Drive URL required"),400
 if not key or ".." in key.split("/") or "\\" in key:return jsonify(error="Invalid object key"),400
 jid=str(uuid.uuid4());db.create_job(jid,url,key);launch(jid);return jsonify(job_id=jid),202
@app.get("/api/transfer/<jid>")
def status(jid):
 j=db.get_job(jid)
 if not j:return jsonify(error="Job not found"),404
 j.pop("upload_id",None);return jsonify(j)
@app.post("/api/transfer/<jid>/resume")
def resume(jid):
 if not authorized():return jsonify(error="Unauthorized"),401
 j=db.get_job(jid)
 if not j:return jsonify(error="Job not found"),404
 if j["status"]=="completed":return jsonify(error="Already completed"),409
 db.update(jid,status="queued",message="Resume requested");launch(jid);return jsonify(ok=True,job_id=jid),202
@app.get("/api/data")
def data():
 try:
  key=request.args.get("key",os.getenv("HF_OBJECT_KEY","data.json"));o=get_s3().head_object(Bucket=bucket_name(),Key=key)
  return jsonify(name=key,size=o.get("ContentLength"),content_type=o.get("ContentType"),etag=o.get("ETag"))
 except Exception as e:return jsonify(error=str(e)),503
@app.get("/api/data/download-url")
def download():
 try:
  key=request.args.get("key",os.getenv("HF_OBJECT_KEY","data.json"))
  return jsonify(url=get_s3().generate_presigned_url("get_object",Params={"Bucket":bucket_name(),"Key":key},ExpiresIn=900),expires_in=900)
 except Exception as e:return jsonify(error=str(e)),503
resume_active()
