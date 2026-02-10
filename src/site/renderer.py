"""HTML rendering using Jinja2 templates."""

from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape


class PageRenderer:
    """Renders HTML pages using Jinja2 templates."""

    def __init__(self, template_dir: str = "site/templates"):
        """Initialize renderer.

        :param template_dir: directory containing Jinja2 templates
        """
        self.template_dir = Path(template_dir)
        if not self.template_dir.exists():
            raise ValueError(f"Template directory not found: {self.template_dir}")

        self.env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=select_autoescape(["html", "xml", "j2", "jinja2"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.env.filters["current_year"] = lambda: datetime.now().year

    def render_page(self, conferences: list[dict], areas: dict | None = None) -> str:
        """Render full HTML page.

        :param conferences: list of conference data dictionaries
        :param areas: area codes to full names mapping
        :return: rendered HTML string
        """
        template = self.env.get_template("index.html.j2")
        return template.render(
            conferences=conferences,
            areas=areas or {},
            current_year=datetime.now().year,
        )
