import datetime
import logging
from typing import Dict, Any
from sqlalchemy.orm import Session
from . import models

logger = logging.getLogger("file_ingestion")

class DocumentIngestionEngine:
    """
    Module 5: Knowledge Base File Ingestion.
    Parses PDF, CSV, and text document contents into indexed CompanyKnowledgeChunks.
    """
    @staticmethod
    def process_and_index_document(
        db: Session,
        company_id: int,
        filename: str,
        content_text: str,
        category: str = "Catalog/Policy"
    ) -> Dict[str, Any]:
        if not content_text or not content_text.strip():
            return {"status": "error", "message": "File content is empty."}

        text = content_text.strip()
        # Chunk text into ~500 character sections for effective RAG retrieval
        chunk_size = 500
        overlap = 50
        chunks = []

        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunk_content = text[start:end]
            chunks.append(chunk_content)
            start += chunk_size - overlap

        now_iso = datetime.datetime.utcnow().isoformat() + "Z"
        created_count = 0

        for idx, chunk in enumerate(chunks):
            title = f"{filename} (Part {idx+1})"
            knowledge_entry = models.CompanyKnowledgeChunk(
                company_id=company_id,
                title=title,
                category=category,
                content=chunk,
                source_filename=filename,
                created_at=now_iso
            )
            db.add(knowledge_entry)
            created_count += 1

        try:
            db.commit()
            logger.info(f"[DocumentIngestion] Successfully indexed '{filename}' into {created_count} RAG chunks.")
            return {
                "status": "success",
                "filename": filename,
                "chunks_indexed": created_count,
                "total_chars": len(text)
            }
        except Exception as e:
            logger.error(f"[DocumentIngestion] Failed to save chunks: {e}")
            db.rollback()
            return {"status": "error", "message": str(e)}
