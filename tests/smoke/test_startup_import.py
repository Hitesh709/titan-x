"""Startup smoke test: catch import/router failures before deployment."""


def test_application_imports_and_registers_routes() -> None:
    from titan_x.main import app

    assert app is not None
    assert len(app.routes) > 0
