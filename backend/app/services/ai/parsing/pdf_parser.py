"""PDF document parser using PyMuPDF (fitz).

Extracts text, embedded images, and table structures from PDF files.

Multi-page PDFs are processed in **parallel batches** (up to 4 worker
threads) via ``ThreadPoolExecutor`` to leverage multi-core CPUs. Each
worker opens its own Fitz handle, making this thread-safe.
"""

import asyncio
import base64
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import fitz

from app.services.ai.parsing.base import DocumentParser
from app.services.ai.schemas import DocumentContent

logger = logging.getLogger(__name__)

# Maximum number of parallel worker threads for PDF page processing.
MAX_PDF_WORKERS = 4


def _is_qr_code(image_bytes: bytes) -> bool:
    """Detect if the image contains a QR code using OpenCV if available.

    Uses OpenCV's QRCodeDetector, which is fast and does not require
    external system libraries like zbar. Returns False if OpenCV is not
    installed or if no QR code is detected in the image.
    """
    try:
        import cv2
        import numpy as np

        # Convert raw bytes to a numpy array for OpenCV decoding
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return False

        detector = cv2.QRCodeDetector()
        retval, _ = detector.detect(img)
        return retval
    except ImportError:
        # Gracefully proceed if opencv-python-headless is not installed
        return False
    except Exception as e:
        logger.debug("Failed to check image for QR code: %s", e)
        return False


class PdfParser(DocumentParser):
    """PyMuPDF-based parser for PDF documents.

    Uses thread-pool parallelism to extract content from all pages.
    Results are merged and sorted back into page order.
    """

    async def get_content(self) -> DocumentContent:
        """Extract text, images, and tables from the PDF.

        The CPU-bound PyMuPDF operations are offloaded to a thread
        executor so the event loop remains responsive.
        """
        logger.debug("Extracting PDF content from: %s", self.file_path)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync_extract)

    # ── Synchronous internals (run in thread executor) ──────────────

    def _sync_extract(self) -> DocumentContent:
        """Synchronous entry point — runs inside a thread executor.

        Pages are divided into balanced batches and processed in parallel.
        """
        probe = fitz.open(self.file_path)
        num_pages = len(probe)
        probe.close()

        if num_pages == 0:
            return DocumentContent(texts=[], images=[], tables=[])

        # Divide pages into balanced batches
        num_workers = min(num_pages, MAX_PDF_WORKERS)
        pages_per_worker = max(1, num_pages // num_workers)
        extra = num_pages % num_workers

        batches: list[list[int]] = []
        start = 0
        for w in range(num_workers):
            size = pages_per_worker + (1 if w < extra else 0)
            batches.append(list(range(start, start + size)))
            start += size

        all_texts: list[dict] = []
        all_images: list[dict] = []
        all_tables: list[dict] = []

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            future_map = {
                executor.submit(self._extract_batch_pages, self.file_path, batch): batch
                for batch in batches
            }
            for future in as_completed(future_map):
                try:
                    texts, images, tables = future.result()
                    all_texts.extend(texts)
                    all_images.extend(images)
                    all_tables.extend(tables)
                except Exception as e:
                    logger.warning("PDF batch failed: %s", e)

        # Restore document order (batches complete out of order)
        all_texts.sort(key=lambda x: x["page_index"])
        all_images.sort(key=lambda x: (x["page_index"], x["image_index"]))
        all_tables.sort(key=lambda x: (x["page_index"], x["table_index"]))

        logger.info(
            "PDF extraction complete: %d pages, %d texts, %d images, %d tables",
            num_pages,
            len(all_texts),
            len(all_images),
            len(all_tables),
        )
        return DocumentContent(texts=all_texts, images=all_images, tables=all_tables)

    @staticmethod
    def _extract_batch_pages(file_path: str, page_indices: list[int]) -> tuple:
        """Extract content from a contiguous range of PDF pages.

        Args:
            file_path: Path to the PDF file.
            page_indices: List of 0-based page numbers to process.

        Returns:
            A 3-tuple ``(texts, images, tables)`` where each element is a
            list of dicts extracted from the requested pages.
        """
        doc = fitz.open(file_path)
        try:
            texts: list[dict] = []
            images: list[dict] = []
            tables: list[dict] = []

            for i in page_indices:
                page = doc[i]

                # ── Text ─────────────────────────────────────────
                text = page.get_text()
                if text.strip():
                    texts.append({"page_index": i, "text": text})

                # ── Images ───────────────────────────────────────
                image_list = page.get_images(full=True)
                for img_index, img in enumerate(image_list):
                    xref = img[0]

                    rects = page.get_image_rects(xref)
                    if not rects:
                        continue

                    rect = rects[0]

                    # Ignore tiny displayed images
                    if rect.width < 100 or rect.height < 100:
                        continue

                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]

                    # Skip QR codes to avoid sending them to multimodal models or indexing them
                    if _is_qr_code(image_bytes):
                        logger.info("Skipping QR code image p%d/i%d", i, img_index)
                        continue

                    base64_image = base64.b64encode(image_bytes).decode("utf-8")

                    # Save image for testing (uncomment to write extracted images to disk)
                    # import os
                    # os.makedirs("temp", exist_ok=True)
                    # ext = base_image.get("ext", "png")
                    # with open(os.path.join("temp", f"page_{i}_img_{img_index}.{ext}"), "wb") as f:
                    #     f.write(image_bytes)
                    images.append(
                        {
                            "page_index": i,
                            "image_index": img_index,
                            "image_base64": base64_image,
                        }
                    )

                # ── Tables ───────────────────────────────────────
                table_list = page.find_tables()
                for table_index, table in enumerate(table_list):
                    df = table.to_pandas()
                    tables.append(
                        {
                            "page_index": i,
                            "table_index": table_index,
                            "table_df": df,
                        }
                    )

            return texts, images, tables
        finally:
            doc.close()
