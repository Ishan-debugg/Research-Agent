import asyncio
import os
from app.main import _run_pipeline

async def main():
    try:
        response = await _run_pipeline("jailbreaking large language models and security risks", "test_id")
        print("Success:", response.query)
    except Exception as e:
        print(f"Exception caught: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
