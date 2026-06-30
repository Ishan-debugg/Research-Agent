"""
Stage 3: Download PDFs and extract text with PyMuPDF.

Two practical safeguards built in:
1. Async/concurrent downloads (so 5 PDFs don't download one-by-one)
2. Fallback to abstract-only text if extraction fails or returns
   near-empty content (some arXiv PDFs are scanned or malformed)
"""
import asyncio
import io
import httpx
import fitz  # PyMuPDF
from app.models.schemas import PaperCandidate

MIN_VALID_TEXT_LENGTH = 500  # below this, treat extraction as failed


async def _download_pdf(client: httpx.AsyncClient, url: str) -> bytes | None:
    try:
        resp = await client.get(url, timeout=15.0, follow_redirects=True)
        resp.raise_for_status()
        return resp.content
    except Exception:
        return None


def _extract_text(pdf_bytes: bytes, max_pages: int = 6) -> str:
    """
    Extract text from the first N pages only - intro, method, and most
    results sections live early in arXiv papers, and this keeps token
    usage down for the Gemini extraction step that follows.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages_to_read = min(len(doc), max_pages)
    text_parts = [doc[i].get_text() for i in range(pages_to_read)]
    doc.close()
    return "\n".join(text_parts)


async def get_paper_texts(papers: list[PaperCandidate]) -> dict[str, str]:
    """
    Downloads + extracts text for all given papers concurrently.
    Returns a dict of arxiv_id -> text (falls back to abstract on failure).
    """
    async with httpx.AsyncClient() as client:
        pdf_bytes_list = await asyncio.gather(
            *[_download_pdf(client, p.pdf_url) for p in papers]
        )

    results: dict[str, str] = {}
    for paper, pdf_bytes in zip(papers, pdf_bytes_list):
        text = ""
        if pdf_bytes:
            try:
                text = _extract_text(pdf_bytes)
            except Exception:
                text = ""

        if len(text.strip()) < MIN_VALID_TEXT_LENGTH:
            # fallback: abstract-only extraction is still better than crashing
            text = f"Title: {paper.title}\n\nAbstract: {paper.abstract}"

        results[paper.arxiv_id] = text

    return results


if __name__ == "__main__":
    from app.services.arxiv_service import search_arxiv
    from app.services.rerank_service import rerank_papers

    async def main():
        query = "retrieval-augmented generation"
        candidates = search_arxiv(query, max_results=20)
        top = rerank_papers(query, candidates, top_k=5)
        texts = await get_paper_texts(top)
        for arxiv_id, text in texts.items():
            print(f"{arxiv_id}: {len(text)} chars extracted")

    asyncio.run(main())
    