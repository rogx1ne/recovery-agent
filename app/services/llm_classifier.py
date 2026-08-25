"""
services/llm_classifier.py — AI-powered failure classification using Google Gemini.

This is the "AI" layer that differentiates this project from a plain rules engine.

What it does
------------
1. Sends the raw Razorpay error_reason to Gemini with a structured prompt.
2. Gemini returns: (a) the root-cause category, (b) a plain-English explanation
   written from the perspective of a payments expert.
3. The explanation goes verbatim into AuditLog.reasoning — making every audit
   entry genuinely AI-generated and human-readable.
4. Falls back to the rules-based classifier if:
   - GEMINI_API_KEY is not set
   - The API call fails (network, quota, etc.)
   - The response can't be parsed
   so the system always works, even without an API key.

Setup
-----
Get a free Gemini API key at: https://aistudio.google.com/app/apikey
Add to .env: GEMINI_API_KEY=AIza...

Cost: the free tier (Gemini 1.5 Flash) is 15 RPM / 1M tokens/day — more than
enough for a buildathon demo with hundreds of transactions.
"""

import json
import logging
from typing import Optional

from app.config import get_settings
from app.models.transaction import RootCauseCategory

logger = logging.getLogger(__name__)

# ─── Valid category names the LLM must choose from ───────────────────────────
_VALID_CATEGORIES = {c.value for c in RootCauseCategory}

# ─── Prompt template ─────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """You are a senior payments engineer at a fintech company.
Your job is to classify failed payment error codes and explain them clearly to business stakeholders.

You MUST respond with a single valid JSON object and nothing else. No markdown, no explanation outside the JSON.

JSON schema:
{
  "category": "<one of: card_declined | insufficient_fund | gateway_technical_error | authentication_failed | subscription_failed | unknown>",
  "confidence": "<high | medium | low>",
  "reasoning": "<2-3 sentences explaining: why this failure happened, what it means for the merchant, and why the chosen recovery action makes sense. Write for a business audience, not a developer.>"
}
"""

_USER_PROMPT_TEMPLATE = """Classify this Razorpay payment failure:

error_reason: "{error_reason}"
amount: ₹{amount_inr}
currency: {currency}

Pick the most specific category that applies. Explain why in plain business language."""


def classify_with_llm(
    error_reason: Optional[str],
    amount: int = 0,
    currency: str = "INR",
) -> tuple[RootCauseCategory, str, bool]:
    """
    Classify a payment failure using Gemini AI.

    Parameters
    ----------
    error_reason : str | None
        Raw error_reason from Razorpay.
    amount : int
        Amount in paise (for context in the prompt).
    currency : str
        Currency code.

    Returns
    -------
    tuple of:
        - RootCauseCategory (the classification)
        - str (human-readable reasoning for AuditLog)
        - bool (True = AI-generated, False = fell back to rules)
    """
    settings = get_settings()

    if not settings.gemini_api_key:
        logger.info("GEMINI_API_KEY not set — using rules-based classifier")
        return _fallback(error_reason)

    try:
        return _call_gemini(error_reason, amount, currency, settings.gemini_api_key)
    except Exception as exc:
        logger.warning("Gemini API call failed (%s) — falling back to rules-based", exc)
        return _fallback(error_reason)


def _call_gemini(
    error_reason: Optional[str],
    amount: int,
    currency: str,
    api_key: str,
) -> tuple[RootCauseCategory, str, bool]:
    """Make the Gemini API call and parse the response."""
    try:
        import google.generativeai as genai  # type: ignore[import]
    except ImportError:
        logger.warning("google-generativeai not installed — using rules-based classifier")
        return _fallback(error_reason)

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        system_instruction=_SYSTEM_PROMPT,
        generation_config=genai.GenerationConfig(
            temperature=0.1,            # Low temp for consistent structured output
            response_mime_type="application/json",
        ),
    )

    user_prompt = _USER_PROMPT_TEMPLATE.format(
        error_reason=error_reason or "(no reason provided)",
        amount_inr=round(amount / 100, 2),
        currency=currency,
    )

    response = model.generate_content(user_prompt)
    raw_text = response.text.strip()

    # Parse JSON response
    data = json.loads(raw_text)
    category_str = data.get("category", "unknown").strip().lower()
    reasoning = data.get("reasoning", "").strip()
    confidence = data.get("confidence", "medium")

    # Validate category
    if category_str not in _VALID_CATEGORIES:
        logger.warning("LLM returned unknown category %r — mapping to UNKNOWN", category_str)
        category_str = "unknown"

    category = RootCauseCategory(category_str)

    # Enrich the reasoning with AI attribution
    full_reasoning = (
        f"[AI-classified, confidence: {confidence}] {reasoning} "
        f"(Raw error_reason: '{error_reason}')"
    )

    logger.info(
        "Gemini classified %r -> %s (confidence: %s)",
        error_reason,
        category,
        confidence,
    )
    return category, full_reasoning, True


def _fallback(error_reason: Optional[str]) -> tuple[RootCauseCategory, str, bool]:
    """Fall back to rules-based classifier when Gemini is unavailable."""
    from app.services.classifier import classify, explain_classification

    category = classify(error_reason)
    reasoning = explain_classification(error_reason, category)
    reasoning = f"[Rules-based classifier] {reasoning}"
    return category, reasoning, False


def generate_recovery_message(
    error_reason: Optional[str],
    amount: int,
    currency: str,
    category: RootCauseCategory,
    link_url: str = "https://rzp.io/i/recovery",
) -> str:
    """
    Generate a friendly, high-converting WhatsApp message in conversational Hinglish.

    Uses Gemini if available, otherwise falls back to a smart Hinglish template.
    """
    settings = get_settings()
    amount_inr = round(amount / 100, 2)

    if settings.gemini_api_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.gemini_api_key)
            model = genai.GenerativeModel("gemini-1.5-flash")

            prompt = (
                f"You are a polite customer care agent for an Indian e-commerce store. "
                f"Write a short, friendly, 2-sentence WhatsApp message in conversational Hinglish "
                f"(mix of Hindi and English written in Latin script) telling the customer that their payment of ₹{amount_inr} "
                f"failed due to '{error_reason or category.value}'. "
                f"Reassure them their cart is reserved, and ask them to complete the payment via this link: {link_url}. "
                f"Keep it professional, empathetic, and urgent."
            )
            res = model.generate_content(prompt)
            return res.text.strip()
        except Exception as exc:
            logger.warning("Gemini recovery message generation failed (%s) — using template", exc)

    # Fallback Hinglish Templates
    cat_hints = {
        RootCauseCategory.CARD_DECLINED: "card decline hone ki wajah se",
        RootCauseCategory.INSUFFICIENT_FUND: "insufficient balance ki वजह se",
        RootCauseCategory.AUTHENTICATION_FAILED: "OTP / 3DS authentication complete na hone ki wajah se",
        RootCauseCategory.SUBSCRIPTION_FAILED: "mandate debit complete na hone ki वजह se",
        RootCauseCategory.GATEWAY_TECHNICAL_ERROR: "technical bank error ki वजह se",
        RootCauseCategory.UNKNOWN: "tecnical issue ki वजह se",
    }
    hint = cat_hints.get(category, "payment issue ki वजह se")

    return (
        f"Aapka ₹{amount_inr:,.0f} ka payment {hint} complete nahi ho paya. "
        f"Aapka order reserve rakha gaya hai! Safe recovery link se payment complete karein: {link_url}"
    )

