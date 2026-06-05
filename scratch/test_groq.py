import asyncio
from openai import AsyncOpenAI

async def test_groq():
    client = AsyncOpenAI(
        api_key="YOUR_API_KEY",
        base_url="https://api.groq.com/openai/v1"
    )
    try:
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "user", "content": "Hello"}
            ],
            max_tokens=10
        )
        print("SUCCESS:", response.choices[0].message.content)
    except Exception as e:
        print("ERROR:", str(e))

if __name__ == "__main__":
    asyncio.run(test_groq())
