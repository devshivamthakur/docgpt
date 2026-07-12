import logging

import fitz
import base64
from app.services.AIServices.schemas import DocumentContent

logger = logging.getLogger(__name__)


class DocumentParser:
    """Parses documents (PDF, DOCX, TXT, MD) and extracts text, images, and tables."""

    def __init__(self, file_path: str, file_extension: str):
        self.file_path = file_path
        self.file_extension = file_extension

    def get_content(self) -> DocumentContent:
        """Parse the document based on its file extension."""
        logger.info(
            "Parsing document: file_path=%s, extension=%s",
            self.file_path,
            self.file_extension,
        )
        try:
            if self.file_extension == "pdf":
                return self._extract_pdf_content()
            elif self.file_extension in ("docx", "doc"):
                return self._extract_docx_content()
            elif self.file_extension in ("txt", "md"):
                return self._extract_text_content()
            else:
                raise ValueError(f"Unsupported file type: {self.file_extension}")
        except Exception:
            logger.exception(
                "Failed to parse document: file_path=%s, extension=%s",
                self.file_path,
                self.file_extension,
            )
            raise

    def _extract_text_content(self) -> DocumentContent:
        """Extract content from a plain text file."""
        logger.debug("Extracting text content from: %s", self.file_path)
        try:
            with open(self.file_path, "r", encoding="utf-8") as file:
                text = file.read()
            logger.info("Text extraction complete: %d characters", len(text))
            return DocumentContent(
                texts=[{"page_index": 0, "text": text}],
                images=[],
                tables=[],
            )
        except Exception:
            logger.exception("Failed to extract text content from: %s", self.file_path)
            raise

    def _extract_pdf_content(self) -> DocumentContent:
        """Extract text, images, and tables from a PDF file."""
        logger.debug("Extracting PDF content from: %s", self.file_path)
        doc = None
        try:
            doc = fitz.open(self.file_path)
            images: list[dict] = []
            tables: list[dict] = []
            texts: list[dict] = []

            logger.debug("PDF has %d pages", len(doc))

            for i, page in enumerate(doc):
                # Process text
                text = page.get_text()
                if text.strip():
                    texts.append({"page_index": i, "text": text})

                # Process images
                image_list = page.get_images(full=True)
                for img_index, img in enumerate(image_list):
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    base64_image = base64.b64encode(image_bytes).decode("utf-8")
                    images.append({
                        "page_index": i,
                        "image_index": img_index,
                        "image_base64": base64_image,
                    })

                # Process tables
                table_list = page.find_tables()
                for table_index, table in enumerate(table_list):
                    df = table.to_pandas()
                    tables.append({
                        "page_index": i,
                        "table_index": table_index,
                        "table_df": df,
                    })

            logger.info(
                "PDF extraction complete: %d pages, %d texts, %d images, %d tables",
                len(doc),
                len(texts),
                len(images),
                len(tables),
            )
            return DocumentContent(texts=texts, images=images, tables=tables)
        except Exception:
            logger.exception(
                "Failed to extract PDF content from: %s", self.file_path
            )
            raise
        finally:
            if doc is not None:
                doc.close()

    def _extract_docx_content(self) -> DocumentContent:
        """Extract content from a DOCX file (stub implementation)."""
        logger.warning("DOCX extraction not yet implemented for: %s", self.file_path)
        return DocumentContent(texts=[], images=[], tables=[])   




