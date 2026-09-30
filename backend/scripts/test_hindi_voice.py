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
        audio_stream = client.text_to_speech.convert(
            text="नमस्ते, आज हम क्वांटम भौतिकी की दिलचस्प दुनिया के बारे में जानेंगे।",
            voice_id="pNInz6obpgDQGcFmaJgB",
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128",
        )
        
        with open("test_hindi.mp3", "wb") as f:
            async for chunk in audio_stream:
                if chunk:
                    f.write(chunk)
        print("Success")
    except Exception as e:
        print("Error details:", getattr(e, 'body', str(e)))

if __name__ == "__main__":
    asyncio.run(main())
