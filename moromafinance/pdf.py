"""Shared HTML->PDF rendering via wkhtmltopdf.

Previously this exact logic was copy-pasted into five modules (custom/views.py,
loan/views.py, loan/tasks.py, report/tasks.py, staff/views.py). It now lives
here; the per-module ``generate_pdf`` helpers delegate to ``render_pdf`` so the
template directory stays the same as before.
"""
import logging
import shutil
import subprocess

from django.conf import settings
from django.http import HttpResponse
from django.template.loader import render_to_string
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)


def _pdf_command():
    """Return an installed HTML-to-PDF command, preferring wkhtmltopdf."""
    configured = getattr(settings, 'WKHTMLTOPDF_CMD', '')
    wkhtmltopdf = configured if configured and shutil.which(configured) else shutil.which('wkhtmltopdf')
    if wkhtmltopdf:
        return [wkhtmltopdf, '-q', '-', '-']

    configured = getattr(settings, 'WEASYPRINT_CMD', '')
    weasyprint = configured if configured and shutil.which(configured) else shutil.which('weasyprint')
    if weasyprint:
        return [weasyprint, '-', '-']

    raise RuntimeError(
        'No PDF renderer is installed. Install wkhtmltopdf or weasyprint.'
    )


def render_html_pdf(html):
    """Convert rendered HTML to PDF bytes using an available system renderer."""
    command = _pdf_command()
    proc = subprocess.run(
        command,
        input=html.encode('utf-8'),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
        check=False,
    )
    if proc.returncode or not proc.stdout.startswith(b'%PDF'):
        detail = proc.stderr.decode('utf-8', 'ignore')[:500]
        logger.error("PDF renderer failed (%s): %s", proc.returncode, detail)
        raise RuntimeError('Unable to generate PDF document.')
    return proc.stdout


def django_pdf_response(request, template, context, filename, inline=False):
    """Render a Django template and return it as a PDF response."""
    html = render_to_string(template, context=context, request=request)
    response = HttpResponse(render_html_pdf(html), content_type='application/pdf')
    disposition = 'inline' if inline else 'attachment'
    response['Content-Disposition'] = f'{disposition}; filename="{filename}"'
    return response


def render_pdf(templatefile, data, template_dir='custom/templates'):
    """Render *templatefile* (Jinja2) with *data* and return PDF bytes."""
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template(templatefile)
    html = template.render(data)

    return render_html_pdf(html)
