import logging
import tempfile
from pathlib import Path

import pandas as pd
import pdfplumber
import requests

logger = logging.getLogger(__name__)

class DeepScanner:
    """
    scans top scoring files to verify they are actually usable.
    Acts as a 'False Hope Detector'.
    """

    def __init__(self, limit_percent=0.1, min_items=5):
        self.limit_percent = limit_percent
        self.min_items = min_items

    def scan_items(self, items: list[dict]) -> list[dict]:
        """
        Select top items and try to parse them.
        Augments items with 'scan_result'.
        """
        # Sort by score
        sorted_items = sorted(items, key=lambda x: x.get("iwg_score", 0), reverse=True)
        
        # Determine how many to scan
        count_to_scan = max(self.min_items, int(len(items) * self.limit_percent))
        # Don't scan more than we have
        count_to_scan = min(count_to_scan, len(items))

        # Mark items to scan
        items_to_scan = sorted_items[:count_to_scan]
        scan_ids = {id(item) for item in items_to_scan}

        print(f"\nDeep Scan: Checking top {count_to_scan} items...")

        for item in items:
            if id(item) in scan_ids:
                scan_result = self._check_file(item)
                item["scan_result"] = scan_result
                if scan_result["status"] == "error":
                    # No penalty, just mark it (penalty skipped per user request)
                    # item["iwg_score"] = max(0, item.get("iwg_score", 0) - 30)
                    item["iwg_factors"].append(("Broken File (Deep Scan)", 0))
            else:
                item["scan_result"] = None
        
        return items

    def _check_file(self, item: dict) -> dict:
        url = item.get("url")
        file_type = item.get("file_type", "").lower()
        
        print(f"  Scanning: {file_type.upper()} {url}...")

        try:
            # Stream download
            with requests.get(url, stream=True, timeout=15) as r:
                r.raise_for_status()
                
                with tempfile.NamedTemporaryFile(delete=True) as tmp:
                    for chunk in r.iter_content(chunk_size=8192):
                        tmp.write(chunk)
                    tmp.flush()
                    
                    # Try to parse based on type
                    if file_type in ["csv"]:
                        self._try_csv(tmp.name)
                    elif file_type in ["xlsx", "xls"]:
                        self._try_excel(tmp.name)
                    elif file_type in ["pdf"]:
                        self._try_pdf(tmp.name)
                    else:
                        return {"status": "skipped", "reason": "unsupported_type"}

            return {"status": "ok", "message": "File is valid"}

        except Exception as e:
            logger.warning(f"  Scan failed for {url}: {e}")
            return {"status": "error", "message": str(e)}

    def _try_csv(self, path):
        # Try multiple separators
        try:
            pd.read_csv(path, sep=",", nrows=5)
        except:
            try:
                pd.read_csv(path, sep=";", nrows=5)
            except Exception as e:
                raise Exception(f"CSV parse error: {e}")

    def _try_excel(self, path):
        try:
            pd.read_excel(path, nrows=5)
        except Exception as e:
            raise Exception(f"Excel parse error: {e}")

    def _try_pdf(self, path):
        try:
            with pdfplumber.open(path) as pdf:
                if not pdf.pages:
                    raise Exception("Empty PDF")
                # Check for at least some text or tables on first page
                first_page = pdf.pages[0]
                text = first_page.extract_text() or ""
                tables = first_page.extract_tables()
                if not text.strip() and not tables:
                     raise Exception("PDF appears empty or scanned image")
        except Exception as e:
            raise Exception(f"PDF parse error: {e}")
