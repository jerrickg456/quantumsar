import base64
import io

import numpy as np
import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)
FAST = {"maxiter": 5, "shots": 128}


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert r.json()["samples"] >= 50


def test_samples_and_sample():
    names = client.get("/samples").json()
    assert names
    s = client.get(f"/samples/{names[0]}").json()
    assert np.array(s["image"]).shape == (64, 64)


@pytest.mark.parametrize("solver", ["graphcut", "otsu", "qaoa_local", "classiq"])
def test_segment(solver):
    r = client.post("/segment", json={"sample": "sar_000_normal", "params": {"solver": solver, **FAST}})
    assert r.status_code == 200, r.text
    j = r.json()
    assert np.array(j["labels"]).shape == (64, 64)
    assert j["metrics"]["accuracy"] > 0.9
    assert j["mode"]


def test_edges_and_upload():
    img = np.random.default_rng(0).gamma(3, 1 / 3, (32, 32)).astype(np.float32)
    img[10:20, 10:20] *= 8
    buf = io.BytesIO()
    np.save(buf, img)
    r = client.post("/edges", json={"image_b64": base64.b64encode(buf.getvalue()).decode(),
                                     "params": {"solver": "graphcut"}})
    assert r.status_code == 200, r.text
    assert np.array(r.json()["edges"]).sum() > 10


def test_benchmark_csv():
    r = client.post("/benchmark?format=csv", json={"sample": "sar_000_normal", "solvers": ["graphcut", "otsu"]})
    assert r.status_code == 200
    assert r.text.splitlines()[0].startswith("solver")


def test_bad_solver():
    r = client.post("/segment", json={"sample": "sar_000_normal", "params": {"solver": "nope"}})
    assert r.status_code == 400


def test_large_upload_is_downscaled():
    img = np.random.default_rng(1).gamma(3, 1 / 3, (300, 200)).astype(np.float32)
    buf = io.BytesIO()
    np.save(buf, img)
    r = client.post("/segment", json={"image_b64": base64.b64encode(buf.getvalue()).decode(),
                                       "params": {"solver": "graphcut"}})
    assert r.status_code == 200, r.text
    h, w = np.array(r.json()["labels"]).shape
    assert max(h, w) <= 128 and (h, w) == (100, 66)


def _wait(jid, timeout=120):
    import time

    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/jobs/{jid}").json()
        if j["status"] in ("done", "error"):
            return j
        time.sleep(0.2)
    raise AssertionError("job did not finish")


def test_async_job_roundtrip():
    r = client.post("/jobs", json={"sample": "sar_000_normal", "edges": True,
                                   "params": {"solver": "qaoa_local", **FAST}})
    assert r.status_code == 202, r.text
    j = _wait(r.json()["id"])
    assert j["status"] == "done", j
    assert j["progress"] == 1.0 and j["elapsed_s"] >= 0
    assert np.array(j["result"]["labels"]).shape == (64, 64)
    assert "edges" in j["result"]


def test_job_queue_limit(monkeypatch):
    import api.main as m

    monkeypatch.setattr(m, "MAX_QUEUE", 0)
    r = client.post("/jobs", json={"sample": "sar_000_normal", "params": {"solver": "otsu"}})
    assert r.status_code == 429


def test_unknown_job():
    assert client.get("/jobs/nope").status_code == 404
