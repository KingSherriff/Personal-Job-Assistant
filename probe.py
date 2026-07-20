# probe.py — sits next to modal_app.py
import modal
from modal_app import image as base_image, MODEL_TAG

image = base_image.add_local_python_source("modal_app")
probe_app = modal.App("cold-start-probe")

@probe_app.function(image=image, gpu="T4", timeout=900)
def probe_ab(prefault: bool = False):
    import time, glob, os, subprocess, urllib.request, json

    if prefault:
        t = time.perf_counter()
        paths = glob.glob("/root/.ollama/models/blobs/sha256-*")
        paths += [p for p in glob.glob("/usr/local/lib/ollama/**/*", recursive=True)
                  if os.path.isfile(p)]
        total = 0
        for p in sorted(paths, key=os.path.getsize, reverse=True):
            with open(p, "rb", buffering=0) as f:
                while chunk := f.read(8 << 20):
                    total += len(chunk)
        dt = time.perf_counter() - t
        print(f"PREFAULT: {total/2**30:.2f} GiB in {dt:.1f}s = {total/dt/2**20:.0f} MiB/s")

    env = os.environ.copy()
    env.setdefault("OLLAMA_HOST", "127.0.0.1:11434")
    env.setdefault("OLLAMA_KEEP_ALIVE", "-1")
    t = time.perf_counter()
    srv = subprocess.Popen(["ollama", "serve"], env=env)
    for _ in range(120):
        try:
            urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    print(f"OLLAMA READY: {time.perf_counter() - t:.1f}s")

    t = time.perf_counter()
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=json.dumps({
            "model": MODEL_TAG,
            "messages": [{"role": "user", "content": "warmup"}],
            "options": {"num_ctx": 8192, "num_predict": 1},
            "think": False, "stream": False,
        }).encode(),
        headers={"Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=600).read()
    print(f"FIRST INFERENCE: {time.perf_counter() - t:.1f}s")
    srv.terminate()

    print("--- JIT cache ---")
    subprocess.run(["du", "-sh", "/root/.nv/ComputeCache"])
    subprocess.run(["find", "/root/.nv", "-type", "f", "-exec", "ls", "-lh", "{}", ";"])
    subprocess.run("du -sh /root/.nv 2>/dev/null; ls -la /root/.nv 2>/dev/null", shell=True)