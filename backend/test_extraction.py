import asyncio
import os
import sys

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from app.services.arxiv_service import search_arxiv
from app.services.pdf_service import get_paper_texts
from app.services.extraction_service import extract_papers
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()
genai.configure(api_key=os.environ["GEMINI_API_KEY"])

async def main():
    print("Searching arxiv...")
    papers = search_arxiv("Instruction Tuning", max_results=5)
    print(f"Found {len(papers)} papers")
    
    # We only care about the ones mentioned by the user or just take the top 5
    papers_to_extract = papers[:5]
    
    print("Getting paper texts...")
    texts = await get_paper_texts(papers_to_extract)
    
    print("Extracting papers...")
    results, errors = await extract_papers(papers_to_extract, texts)
    
    print(f"Results: {len(results)}")
    print(f"Errors: {len(errors)}")
    for e in errors:
        print(f"Error for {e.get('title')}: {e.get('error')}")

if __name__ == "__main__":
    asyncio.run(main())
