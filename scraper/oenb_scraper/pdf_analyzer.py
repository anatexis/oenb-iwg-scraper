import io
import requests
import pdfplumber


def analyze_pdf(url: str, timeout: int = 30) -> dict:
    """
    Download and analyze a PDF for machine readability.

    Returns dict with:
        - machine_readable: bool
        - has_tables: bool
        - error: str or None
    """
    result = {
        "machine_readable": False,
        "has_tables": False,
        "error": None,
    }

    try:
        # Download PDF (first 5MB max to avoid huge files)
        response = requests.get(url, timeout=timeout, stream=True)
        response.raise_for_status()

        # Read up to 5MB
        content = b""
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            content += chunk
            if len(content) > 5 * 1024 * 1024:
                break

        # Analyze with pdfplumber
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            text_found = False
            tables_found = False

            # Check first 5 pages max
            for page in pdf.pages[:5]:
                text = page.extract_text() or ""
                if len(text.strip()) > 50:  # More than 50 chars = has text
                    text_found = True

                tables = page.extract_tables() or []
                if tables:
                    tables_found = True

                if text_found and tables_found:
                    break

            result["machine_readable"] = text_found
            result["has_tables"] = tables_found

    except requests.RequestException as e:
        result["error"] = f"Download error: {e}"
    except Exception as e:
        result["error"] = f"PDF analysis error: {e}"

    return result
