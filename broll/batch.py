import argparse
import hashlib
import json
import os
import time
from pathlib import Path
import httpx

def main():
    parser=argparse.ArgumentParser(description="Submit JSON requests and audio files; preserve success and failure evidence")
    parser.add_argument("inputs",type=Path); parser.add_argument("output",type=Path)
    parser.add_argument("--base-url",default="http://localhost:8000")
    parser.add_argument("--timeout",type=float,default=3600)
    args=parser.parse_args(); args.output.mkdir(parents=True,exist_ok=True)
    files=sorted(args.inputs.iterdir()) if args.inputs.is_dir() else [args.inputs]
    headers={"Authorization":"Bearer "+os.environ.get("BROLL_API_TOKEN","")}
    index=[]
    with httpx.Client(base_url=args.base_url,headers=headers,timeout=60) as client:
        for i,path in enumerate(files):
            if path.suffix.lower() not in (".json",".mp3",".wav",".m4a"): continue
            dest=args.output/f"{i:03}-{path.stem}"; dest.mkdir(exist_ok=True)
            try:
                raw=path.read_bytes(); key=hashlib.sha256(raw+path.name.encode()).hexdigest()
                if path.suffix.lower()==".json": body=json.loads(raw)
                else:
                    response=client.post("/api/v1/uploads",headers={"Idempotency-Key":key+"-upload"},files={"file":(path.name,raw)})
                    response.raise_for_status(); body={"upload_id":response.json()["upload_id"]}
                (dest/"request.json").write_text(json.dumps(body,indent=2),encoding="utf-8")
                response=client.post("/api/v1/broll/jobs",headers={"Idempotency-Key":key},json=body)
                (dest/"submission.json").write_text(response.text,encoding="utf-8"); response.raise_for_status()
                job=response.json()["job_id"]; deadline=time.monotonic()+args.timeout
                while True:
                    response=client.get(f"/api/v1/jobs/{job}"); response.raise_for_status(); result=response.json()
                    (dest/"status.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
                    if result["status"] in ("failed","succeeded"): break
                    if time.monotonic()>deadline: raise TimeoutError("Job exceeded batch wait limit")
                    time.sleep(1)
                if result["status"]=="succeeded":
                    for name,url in result["results"].items():
                        # Do not forward the API token to S3 or any other origin.
                        with httpx.Client(timeout=120) as downloads:
                            auth=headers if url.startswith(args.base_url.rstrip("/")+"/") else {}
                            download=downloads.get(url,headers=auth); download.raise_for_status()
                            (dest/Path(name).name).write_bytes(download.content)
                index.append({"input":path.name,"status":result["status"],"folder":dest.name})
            except Exception as exc:
                (dest/"batch-error.json").write_text(json.dumps({"type":type(exc).__name__,"message":"Batch step failed; inspect saved HTTP response/status"}),encoding="utf-8")
                index.append({"input":path.name,"status":"batch_failed","folder":dest.name})
    (args.output/"index.json").write_text(json.dumps(index,indent=2),encoding="utf-8")
if __name__=="__main__": main()
