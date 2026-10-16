"""Jinja templates for the approved desk design."""

from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


def render(request: Request, name: str, context: dict[str, object], status_code: int = 200):
    """Render one page. Context is data, not instructions."""
    payload = {"request": request, **context}
    return TEMPLATES.TemplateResponse(request, name, payload, status_code=status_code)


def render_status_html(context: dict[str, object]) -> str:
    """Render the status page template. It is not mounted on `/status`."""
    return TEMPLATES.env.get_template("status.html").render(**context)
