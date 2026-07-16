import urllib.request, json, time

url = "http://localhost:8000/search/stream?query=transformer+attention+mechanism"
print("Testing live search pipeline...")
t0 = time.time()

req = urllib.request.Request(url)
try:
    with urllib.request.urlopen(req, timeout=90) as r:
        for line in r:
            line = line.decode().strip()
            if not line or not line.startswith("data:"):
                continue
            try:
                data = json.loads(line[5:].strip())
                etype = data.get("type") or data.get("event", "")
                if etype == "stage":
                    stage = data.get("data", {})
                    name = stage.get("stage", "?")
                    msg = stage.get("message", "")
                    print(f"  [{time.time()-t0:5.1f}s] stage={name}  {msg}")
                elif etype == "error":
                    msg = data.get("data", {}).get("message", str(data))
                    print(f"  [{time.time()-t0:5.1f}s] ERROR: {msg}")
                elif etype == "complete":
                    payload = data.get("data", {})
                    papers = payload.get("papers", [])
                    errs = payload.get("errors", [])
                    print(f"\nDone in {time.time()-t0:.1f}s — {len(papers)} papers, {len(errs)} extraction errors")
                    for e in errs:
                        print(f"  FAIL: {e.get('title','?')} | {e.get('error','?')[:120]}")
            except Exception as ex:
                print(f"  parse err: {ex} | {line[:80]}")
except Exception as e:
    print(f"REQUEST FAILED: {e}")
