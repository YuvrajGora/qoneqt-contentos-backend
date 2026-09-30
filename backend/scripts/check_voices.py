import asyncio
import os
from elevenlabs.client import AsyncElevenLabs

async def main():
    token = os.getenv("ELEVENLABS_API_KEY")
    if not token:
        print("Error: ELEVENLABS_API_KEY is not configured.")
        return
    client = AsyncElevenLabs(api_key=token)
    try:
        response = await client.voices.get_all()
        voices = response.voices
        for v in voices:
            labels = v.labels or {}
            print(f"Name: {v.name}, ID: {v.voice_id}, Labels: {labels}")
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(main())
