from app.version import __version__


def test_hello_world(client):
    resp = client.get("/v1/hello")
    assert resp.status_code == 200
    assert resp.get_json() == {
        "message": "Hello, World!",
        "service": "ratual-backend",
        "version": __version__,
    }


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_request_id_is_generated_and_echoed(client):
    assert len(client.get("/health").headers["X-Request-ID"]) == 32
    resp = client.get("/health", headers={"X-Request-ID": "abc12345-trace"})
    assert resp.headers["X-Request-ID"] == "abc12345-trace"


def test_malicious_request_id_is_replaced(client):
    resp = client.get("/health", headers={"X-Request-ID": "<script>alert(1)</script>"})
    assert "<script>" not in resp.headers["X-Request-ID"]
    assert len(resp.headers["X-Request-ID"]) == 32


def test_build_header_is_present(client):
    assert client.get("/health").headers["X-Build"] == "dev"
