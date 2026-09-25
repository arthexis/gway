from pydantic import BaseModel

from gway.sampler import load as load_sampler

web_app = load_sampler("web/app")
ApplicationHTTPAdapter = web_app.ApplicationHTTPAdapter


class UserCreate(BaseModel):
    name: str
    age: int


class UserView(BaseModel):
    name: str
    age: int
    active: bool = True


def test_body_model_validates_single_body_binding(gateway):
    def create(user):
        assert isinstance(user, UserCreate)
        return {"name": user.name, "age": user.age, "active": True}

    gateway.wrap("users.create", create)
    gateway("setup app --topic users")
    app = gateway(
        "view create --route /users --method POST "
        "--body user --body-model UserCreate --response-model UserView"
    )
    application = ApplicationHTTPAdapter(gateway, app)

    assert application.response(
        "POST",
        "/users",
        headers={"content-type": "application/json"},
        body=b'{"name":"Ada","age":"42"}',
    ) == (
        200,
        {},
        {"name": "Ada", "age": 42, "active": True},
    )


def test_body_model_can_feed_multiple_body_bindings(gateway):
    def create(name, age: int):
        return {"name": name, "age": age, "active": True}

    gateway.wrap("users.create", create)
    gateway("setup app --topic users")
    app = gateway(
        "view create --route /users --method POST "
        "--body name,age --body-model UserCreate --response-model UserView"
    )
    application = ApplicationHTTPAdapter(gateway, app)

    assert application.response(
        "POST",
        "/users",
        headers={"content-type": "application/json"},
        body=b'{"name":"Ada","age":"42"}',
    ) == (
        200,
        {},
        {"name": "Ada", "age": 42, "active": True},
    )


def test_invalid_body_model_returns_422(gateway):
    gateway.wrap("users.create", lambda user: user)
    gateway("setup app --topic users")
    app = gateway(
        "view create --route /users --method POST "
        "--body user --body-model UserCreate"
    )
    application = ApplicationHTTPAdapter(gateway, app)

    status, _, payload = application.response(
        "POST",
        "/users",
        headers={"content-type": "application/json"},
        body=b'{"name":"Ada","age":"not-an-int"}',
    )

    assert status == 422
    assert payload["error"] == "invalid_body"


def test_response_model_serializes_pydantic_compatible_result(gateway):
    gateway.wrap(
        "users.read",
        lambda: {"name": "Ada", "age": "42"},
    )
    gateway("setup app --topic users")
    app = gateway(
        "view read --route /users/1 --response-model UserView"
    )
    application = ApplicationHTTPAdapter(gateway, app)

    assert application.response("GET", "/users/1") == (
        200,
        {},
        {"name": "Ada", "age": 42, "active": True},
    )


def test_response_model_preserves_explicit_status_and_headers(gateway):
    gateway.wrap(
        "users.create",
        lambda: (
            201,
            {"location": "/users/1"},
            {"name": "Ada", "age": 42},
        ),
    )
    gateway("setup app --topic users")
    app = gateway(
        "view create --route /users --method POST --response-model UserView"
    )
    application = ApplicationHTTPAdapter(gateway, app)

    assert application.response("POST", "/users") == (
        201,
        {"location": "/users/1"},
        {"name": "Ada", "age": 42, "active": True},
    )


def test_invalid_response_model_returns_500(gateway):
    gateway.wrap(
        "users.read",
        lambda: {"name": "Ada", "age": "invalid"},
    )
    gateway("setup app --topic users")
    app = gateway(
        "view read --route /users/1 --response-model UserView"
    )
    application = ApplicationHTTPAdapter(gateway, app)

    status, _, payload = application.response("GET", "/users/1")

    assert status == 500
    assert payload["error"] == "invalid_response"


def test_body_model_requires_body_binding():
    ViewSpec = web_app.ViewSpec

    try:
        ViewSpec("users.create", body_model="UserCreate")
    except ValueError as error:
        assert "body_model requires" in str(error)
    else:
        raise AssertionError("body_model without body binding should fail")
