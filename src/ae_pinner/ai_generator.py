"""AI-powered Pinterest pin description generator.

Supports both OpenAI (GPT) and Google Gemini as AI providers.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ae_pinner.aliexpress import Product


class AIProvider(str, Enum):
    OPENAI = "openai"
    GEMINI = "gemini"


@dataclass
class PinContent:
    """Generated content for a Pinterest pin."""

    title: str
    description: str
    alt_text: str


SYSTEM_PROMPT = (
    "You are a Pinterest marketing expert. Generate engaging, click-worthy "
    "pin content for product affiliate marketing.\n\n"
    "Rules:\n"
    "- Title: Max 100 chars, catchy, include price if there's a big discount\n"
    "- Description: 2-3 sentences max, include relevant hashtags (5-8), "
    "mention key features, price drop, and urgency\n"
    "- Alt text: Brief factual description of the product for accessibility "
    "(max 50 words)\n"
    "- Use emojis sparingly (2-3 max) for visual appeal\n"
    "- Focus on value proposition and deal urgency\n"
    "- Never use misleading claims\n"
    "- Make it feel organic, not spammy"
)

USER_PROMPT_TEMPLATE = """Generate Pinterest pin content for this product:

Product: {title}
Original Price: {original_price}
Sale Price: {discount_price}
Discount: {discount_rate}% OFF
Sales (30 days): {sales_30day}
Rating: {comment_score}/5

Return EXACTLY in this format (no extra text):
TITLE: [your title here]
DESCRIPTION: [your description here]
ALT_TEXT: [your alt text here]"""


async def generate_with_openai(api_key: str, product: Product) -> PinContent:
    """Generate pin content using OpenAI GPT."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key)

    user_prompt = USER_PROMPT_TEMPLATE.format(
        title=product.title,
        original_price=product.original_price,
        discount_price=product.discount_price,
        discount_rate=product.discount_rate,
        sales_30day=product.sales_30day,
        comment_score=product.comment_score,
    )

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.8,
        max_tokens=300,
    )

    return _parse_response(response.choices[0].message.content or "")


async def generate_with_gemini(api_key: str, product: Product) -> PinContent:
    """Generate pin content using Google Gemini."""
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")

    user_prompt = USER_PROMPT_TEMPLATE.format(
        title=product.title,
        original_price=product.original_price,
        discount_price=product.discount_price,
        discount_rate=product.discount_rate,
        sales_30day=product.sales_30day,
        comment_score=product.comment_score,
    )

    full_prompt = f"{SYSTEM_PROMPT}\n\n{user_prompt}"
    response = await model.generate_content_async(full_prompt)

    return _parse_response(response.text or "")


def _parse_response(text: str) -> PinContent:
    """Parse AI response into structured PinContent."""
    title = ""
    description = ""
    alt_text = ""

    for line in text.strip().split("\n"):
        line = line.strip()
        if line.upper().startswith("TITLE:"):
            title = line[6:].strip()
        elif line.upper().startswith("DESCRIPTION:"):
            description = line[12:].strip()
        elif line.upper().startswith("ALT_TEXT:") or line.upper().startswith("ALT TEXT:"):
            alt_text = line.split(":", 1)[1].strip()

    # Fallbacks if parsing fails
    if not title:
        title = "Amazing Deal - Check This Out!"
    if not description:
        description = "Great product at an unbeatable price. Shop now!"
    if not alt_text:
        alt_text = "Product image"

    # Enforce Pinterest limits
    title = title[:100]
    description = description[:500]
    alt_text = alt_text[:500]

    return PinContent(title=title, description=description, alt_text=alt_text)


async def generate_pin_content(
    product: Product,
    provider: AIProvider = AIProvider.GEMINI,
    openai_api_key: str = "",
    gemini_api_key: str = "",
) -> PinContent:
    """Generate pin content using the selected AI provider.

    Args:
        product: The AliExpress product to generate content for.
        provider: Which AI provider to use.
        openai_api_key: OpenAI API key (required if provider is OPENAI).
        gemini_api_key: Gemini API key (required if provider is GEMINI).

    Returns:
        PinContent with title, description, and alt_text.
    """
    if provider == AIProvider.OPENAI:
        if not openai_api_key:
            raise ValueError("OpenAI API key is required when using OpenAI provider")
        return await generate_with_openai(openai_api_key, product)
    elif provider == AIProvider.GEMINI:
        if not gemini_api_key:
            raise ValueError("Gemini API key is required when using Gemini provider")
        return await generate_with_gemini(gemini_api_key, product)
    else:
        raise ValueError(f"Unsupported AI provider: {provider}")
