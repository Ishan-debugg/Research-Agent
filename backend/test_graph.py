import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from app.services.arxiv_service import search_arxiv
from app.services.pdf_service import get_paper_texts
from app.services.extraction_service import extract_papers
from app.services.graph_service import build_knowledge_graph
from app.services import gemini_client
from dotenv import load_dotenv
import google.generativeai as genai
import json

import logging
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

load_dotenv()
genai.configure(api_key=os.environ["GEMINI_API_KEY"])

async def main():
    papers = search_arxiv("Instruction Tuning", max_results=5)
    texts = await get_paper_texts(papers)
    extracted, _ = await extract_papers(papers, texts)
    
    print(f"Extracted {len(extracted)} papers.")
    
    # Now let's try to build the knowledge graph and print raw output
    # We will temporarily bypass sanitize_json inside graph_service by just printing the raw output from gemini
    prompt = "Create a knowledge graph..." # not the real prompt, let's just call the service and see what it does
    
    # The real prompt is in graph_service.py
    graph = await build_knowledge_graph("test_hash", "Instruction Tuning", papers, extracted)
    
    print(json.dumps(graph.dict(), indent=2))
    
if __name__ == "__main__":
    asyncio.run(main())
