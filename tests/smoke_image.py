import json
import os
import subprocess
import sys
import time
from urllib.request import ProxyHandler, build_opener

expected_version, expected_commit = sys.argv[1:3]
port = "18080"
opener = build_opener(ProxyHandler({}))

process = subprocess.Popen(
    ["python", "/app/app.py"],
    env={**os.environ, "PORT": port},
    stdout=subprocess.DEVNULL,
    stderr=subprocess.PIPE,
)

try:
    base = f"http://127.0.0.1:{port}"

    for _ in range(50):
        if process.poll() is not None:
            raise RuntimeError("应用进程启动后立即退出")
        try:
            with opener.open(base + "/healthz", timeout=1) as response:
                assert response.status == 200
                assert response.read() == b"ok\n"
            break
        except OSError:
            time.sleep(0.1)
    else:
        raise RuntimeError("应用未在规定时间内通过健康检查")

    with opener.open(base + "/api/info", timeout=2) as response:
        info = json.load(response)

    assert info["version"] == expected_version, info
    assert info["commit"] == expected_commit, info
    print("Final image smoke test passed:", info)
finally:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
