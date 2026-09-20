from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from capture_api.errors import DomainError, ErrorBody, error_responses, install_error_handlers


def _app() -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)
    router = APIRouter()

    @router.get("/boom")
    async def boom() -> None:
        raise DomainError(
            409,
            "name_taken",
            "Taken.",
            extra={"field": "name", "code": "ignored"},
            headers={"X-Extra": "1"},
        )

    @router.get("/limited")
    async def limited() -> None:
        raise DomainError.rate_limited("estimate_rate_limited", "Slow down.", 0, scope="family")

    @router.get("/auth")
    async def auth() -> None:
        raise DomainError.unauthorized("token_expired", "Expired.")

    @router.get("/sensor")
    async def sensor() -> None:
        raise DomainError.forbidden_sensor("dc-east")

    @router.get("/perm")
    async def perm() -> None:
        raise DomainError.forbidden("pcap:download")

    @router.get("/down")
    async def down() -> None:
        raise DomainError.unavailable("pcap_store_degraded", "Degraded.", 30)

    @router.get("/items/{n}")
    async def items(n: int) -> dict[str, int]:
        return {"n": n}

    app.include_router(router)
    return app


def test_domain_error_body_headers_and_status() -> None:
    client = TestClient(_app())
    r = client.get("/boom")
    assert r.status_code == 409
    assert r.json() == {"detail": "Taken.", "code": "name_taken", "field": "name"}
    assert r.headers["x-extra"] == "1"
    assert ErrorBody.model_validate(r.json()).code == "name_taken"


def test_constructors() -> None:
    client = TestClient(_app())
    r = client.get("/limited")
    assert (r.status_code, r.headers["retry-after"]) == (429, "1")
    assert r.json()["scope"] == "family"
    r = client.get("/auth")
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == 'Bearer error="invalid_token"'
    assert r.json()["code"] == "token_expired"
    assert client.get("/sensor").json() == {
        "detail": "You do not have access to sensor 'dc-east'.",
        "code": "forbidden_sensor",
        "sensor_id": "dc-east",
    }
    assert client.get("/perm").json()["required"] == "pcap:download"
    r = client.get("/down")
    assert (r.status_code, r.headers["retry-after"]) == (503, "30")


def test_validation_errors_keep_the_fastapi_shape() -> None:
    r = TestClient(_app()).get("/items/abc")
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert isinstance(detail, list)
    assert detail[0]["loc"] == ["path", "n"]


def test_error_responses_document_retry_after_and_both_422_shapes() -> None:
    responses = error_responses(401, 422, 429)
    assert responses[401]["model"] is ErrorBody
    assert "WWW-Authenticate" in responses[401]["headers"]
    assert "Retry-After" in responses[429]["headers"]
    assert responses[422]["model"] is not ErrorBody
    assert "headers" not in error_responses(401, bearer=False)[401]
