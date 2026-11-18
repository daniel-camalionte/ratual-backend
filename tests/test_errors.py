def test_404_is_json_and_generic(client):
    resp = client.get("/nao-existe")
    assert resp.status_code == 404
    err = resp.get_json()["error"]
    assert err["code"] == "not_found"
    assert err["request_id"]


def test_405_is_json(client):
    resp = client.post("/v1/hello")
    assert resp.status_code == 405
    assert resp.get_json()["error"]["code"] == "method_not_allowed"


def test_payload_too_large(client, settings):
    big = b"x" * (settings.max_content_length + 1)
    resp = client.post("/health", data=big, content_type="application/json")
    assert resp.status_code in (405, 413)


def test_unexpected_error_does_not_leak(settings):
    from app import create_app

    app = create_app(settings)
    app.config["PROPAGATE_EXCEPTIONS"] = False

    @app.get("/boom")
    def boom():
        raise RuntimeError("segredo interno")

    resp = app.test_client().get("/boom")
    assert resp.status_code == 500
    assert "segredo" not in resp.get_data(as_text=True)
    assert resp.get_json()["error"]["code"] == "internal_error"
