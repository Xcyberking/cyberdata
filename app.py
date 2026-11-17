import os,threading,uuid
from flask import Flask,request,jsonify,render_template
from dotenv import load_dotenv
from transfer import start_transfer
from storage import get_s3,bucket_name
load_dotenv()
app=Flask(__name__)
jobs={}
lock=threading.Lock()
@app.get("/")
def home(): return render_template("index.html")
@app.get("/health")
def health(): return jsonify(ok=True,service="CyberData")
@app.post("/api/transfer/start")
def start():
 d=request.get_json(silent=True) or {}
 url=(d.get("drive_url") or os.getenv("GOOGLE_DRIVE_URL","")).strip()
 key=(d.get("object_key") or os.getenv("HF_OBJECT_KEY","data.json")).strip().lstrip("/")
 if not url:return jsonify(error="Google Drive URL required"),400
 if not key or ".." in key.split("/") or "\\" in key:return jsonify(error="Invalid object key"),400
 jid=str(uuid.uuid4())
 with lock: jobs[jid]={"id":jid,"status":"queued","progress":0,"message":"Queued"}
 threading.Thread(target=start_transfer,args=(jid,url,key,jobs,lock),daemon=True).start()
 return jsonify(job_id=jid),202
@app.get("/api/transfer/<jid>")
def status(jid):
 with lock: j=jobs.get(jid)
 return (jsonify(j),200) if j else (jsonify(error="Job not found; process restart clears in-memory status"),404)
@app.get("/api/data")
def data():
 try:
  key=request.args.get("key",os.getenv("HF_OBJECT_KEY","data.json"))
  o=get_s3().head_object(Bucket=bucket_name(),Key=key)
  return jsonify(name=key,size=o.get("ContentLength"),content_type=o.get("ContentType"))
 except Exception as e:return jsonify(error=str(e)),503
@app.get("/api/data/download-url")
def download():
 try:
  key=request.args.get("key",os.getenv("HF_OBJECT_KEY","data.json"))
  return jsonify(url=get_s3().generate_presigned_url("get_object",Params={"Bucket":bucket_name(),"Key":key},ExpiresIn=900),expires_in=900)
 except Exception as e:return jsonify(error=str(e)),503
