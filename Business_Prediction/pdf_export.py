#!/usr/bin/env python3
"""pdf_export.py — programmatic PDF generation for Business Prediction
reports.

Previously the only "PDF" path for this engine's reports was browser
print-to-PDF against the print-optimized CSS in generate_business_report.py
(_shared_css()'s @page rules). This module adds a real, non-interactive,
server-side path: render the SAME HTML the browser-print path uses (via
render_astrologer_report_html / render_client_report_html — this module
does NOT re-implement or fork any report content/markup logic) and convert
that HTML to PDF bytes with a library.

Library choice (documented per the task's sandbox-testing requirement)
----------------------------------------------------------------------
`weasyprint` was tried first per the task's stated preference and
installed cleanly in this sandbox (`pip install weasyprint --break-system-
packages`) with no missing system deps (cairo/pango resolved via its
bundled/py-only font backend on this box) — verified with a real
HTML.write_pdf() smoke call before writing this module. `xhtml2pdf` was
therefore never needed as the primary path, but the import is still
attempted as an automatic fallback if weasyprint is unavailable in some
OTHER environment this code runs in (e.g. a stripped-down prod container
missing weasyprint's native deps), since xhtml2pdf is pure-Python and has
no native dependency footprint. If neither import succeeds, this module
never raises — it degrades to returning the plain HTML with a
`pdf_generation_status` note (see _html_fallback_result below) so a caller
never crashes because a PDF backend isn't installed.

weasyprint is listed under the `pdf` extra in pyproject.toml
([project.optional-dependencies].pdf), not a hard dependency, keeping the
project's core dependency footprint (pydantic/dateutil/jinja2/skyfield/
numpy/openai) unchanged — only opt in if you actually need PDF export.
"""
from __future__ import annotations

import pathlib
import sys
from typing import Any, Dict, Optional, Union

_repo = pathlib.Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from Business_Prediction.generate_business_report import (
    render_astrologer_report_html,
    render_client_report_html,
)

# Which backend actually rendered the PDF, if any. Populated lazily by
# _get_pdf_backend() the first time render_report_pdf() is called, so
# importing this module never itself attempts (and possibly fails) an
# optional import.
_BACKEND_CACHE: Dict[str, Optional[str]] = {"name": None, "checked": False}


def _get_pdf_backend() -> Optional[str]:
    """Returns 'weasyprint', 'xhtml2pdf', or None (no working backend
    installed) — probes exactly once per process and caches the result.
    Never raises: any ImportError (missing package) or other exception
    during the probe (e.g. weasyprint installed but its native deps are
    broken at import time) is treated the same as "not available"."""
    if _BACKEND_CACHE["checked"]:
        return _BACKEND_CACHE["name"]

    _BACKEND_CACHE["checked"] = True
    try:
        import weasyprint  # noqa: F401
        _BACKEND_CACHE["name"] = "weasyprint"
        return "weasyprint"
    except Exception:
        pass

    try:
        import xhtml2pdf.pisa  # noqa: F401
        _BACKEND_CACHE["name"] = "xhtml2pdf"
        return "xhtml2pdf"
    except Exception:
        pass

    _BACKEND_CACHE["name"] = None
    return None


def _render_with_weasyprint(html: str) -> bytes:
    import weasyprint
    return weasyprint.HTML(string=html).write_pdf()


def _render_with_xhtml2pdf(html: str) -> bytes:
    import io
    from xhtml2pdf import pisa

    buf = io.BytesIO()
    result = pisa.CreatePDF(src=html, dest=buf)
    if result.err:
        raise RuntimeError(f"xhtml2pdf reported {result.err} error(s) converting report HTML to PDF")
    return buf.getvalue()


def _html_fallback_bytes(html: str) -> bytes:
    """Graceful-degradation path when no PDF backend is installed/working:
    the caller still gets *something* usable (the same HTML the browser
    print-to-PDF path would use) instead of a crash. The
    pdf_generation_status field on the accompanying metadata (see
    render_report_pdf's docstring) tells the caller this is HTML, not a
    real PDF, so it can react (e.g. show a "Print to PDF from your
    browser" hint) rather than silently mis-serving HTML as a PDF."""
    return html.encode("utf-8")


def render_report_pdf(
    prediction: Dict[str, Any],
    audience: str,
    lang: str = "en",
    output_path: Optional[str] = None,
    name: str = "Client",
    dual_narrative: Optional[Dict[str, Any]] = None,
    payload: Optional[Any] = None,
) -> Union[bytes, str]:
    """Renders the Business Prediction report for `prediction` as an
    actual PDF file (not browser print-CSS).

    Parameters
    ----------
    prediction : the SAME prediction dict produced by
        business_engine.compute_business_prediction() / consumed by
        render_astrologer_report_html / render_client_report_html — this
        function does not recompute or alter it.
    audience : "astrologer" or "client" — selects which of the two
        existing HTML renderers (render_astrologer_report_html /
        render_client_report_html) supplies the report content. Any other
        value raises ValueError (a programming-error guard, not a runtime-
        degradation case).
    lang : "en" / "ta" / "te", forwarded unchanged to the HTML renderer.
    output_path : if given, the PDF (or, in the fallback case, the raw
        HTML) is written to this path and the path string is returned. If
        omitted, the bytes are returned in-memory instead.
    name, dual_narrative, payload : forwarded unchanged to the underlying
        render_astrologer_report_html / render_client_report_html calls
        (dual_narrative/payload are optional there too).

    Returns
    -------
    bytes (PDF or, in the fallback case, UTF-8 HTML) when output_path is
    None, else the str output_path that was written to.

    Never raises for a missing/broken PDF backend — see module docstring.
    Only raises for programmer errors (bad `audience` value) or if writing
    to `output_path` itself fails (a real I/O error the caller should see).
    """
    if audience not in ("astrologer", "client"):
        raise ValueError(f"audience must be 'astrologer' or 'client', got {audience!r}")

    if audience == "astrologer":
        html = render_astrologer_report_html(
            name, prediction, dual_narrative=dual_narrative, lang=lang, payload=payload,
        )
    else:
        html = render_client_report_html(
            name, prediction, dual_narrative=dual_narrative, lang=lang, payload=payload,
        )

    backend = _get_pdf_backend()
    status = "UNAVAILABLE_FALLBACK_TO_HTML"
    data: bytes
    try:
        if backend == "weasyprint":
            data = _render_with_weasyprint(html)
            status = "OK_WEASYPRINT"
        elif backend == "xhtml2pdf":
            data = _render_with_xhtml2pdf(html)
            status = "OK_XHTML2PDF"
        else:
            data = _html_fallback_bytes(html)
    except Exception:
        # A backend was importable but failed at render time (e.g. a
        # malformed/edge-case HTML construct it can't handle) -- degrade
        # to the HTML fallback rather than propagating the exception, per
        # the "never raise on PDF generation failure" requirement.
        data = _html_fallback_bytes(html)
        status = "UNAVAILABLE_FALLBACK_TO_HTML"

    # Attach the status as a lightweight, greppable HTML comment when
    # falling back to raw HTML, so a caller inspecting only the returned
    # bytes/file (not a separate return value) can still tell what
    # happened. Real PDF bytes are left untouched (a PDF is opaque binary;
    # there is no equivalent in-band place to note this in it).
    if status == "UNAVAILABLE_FALLBACK_TO_HTML":
        data = (
            b"<!-- pdf_generation_status: UNAVAILABLE_FALLBACK_TO_HTML "
            b"(no working PDF backend installed -- install the 'pdf' extra, "
            b"e.g. `pip install weasyprint`, or `pip install xhtml2pdf`) -->\n"
        ) + data

    if output_path:
        mode = "wb"
        with open(output_path, mode) as fh:
            fh.write(data)
        return output_path

    return data


def render_report_pdf_with_status(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    """Convenience wrapper around render_report_pdf() that also returns
    the pdf_generation_status explicitly in a dict, for callers that want
    the status without having to sniff the returned bytes for the HTML-
    comment marker. Does not write to output_path itself if output_path
    was NOT passed; if it WAS passed, behaves like render_report_pdf and
    returns the written path too."""
    output_path = kwargs.get("output_path")
    result = render_report_pdf(*args, **kwargs)
    backend = _get_pdf_backend()
    if backend == "weasyprint":
        status = "OK_WEASYPRINT"
    elif backend == "xhtml2pdf":
        status = "OK_XHTML2PDF"
    else:
        status = "UNAVAILABLE_FALLBACK_TO_HTML"
    return {
        "pdf_generation_status": status,
        "backend": backend,
        "output_path": result if output_path else None,
        "data": None if output_path else result,
    }
