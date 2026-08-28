"""
services/llm_classifier.py — AI-powered failure classification using Groq (openai/gpt-oss-20b).

This is the "AI" layer that differentiates this project from a plain rules engine.

What it does
------------
1. Sends the raw Razorpay error_reason to Groq with a structured prompt.
2. Groq returns: (a) the root-cause category, (b) a plain-English explanation
   written from the perspective of a payments expert.
3. The explanation goes verbatim into AuditLog.reasoning — making every audit
   entry genuinely AI-generated and human-readable.
4. Falls back to the rules-based classifier if:
   - GROQ_API_KEY is not set
   - The API call fails (network, quota, etc.)
   - The response can't be parsed
   so the system always works, even without an API key.

Setup
-----
Get a free Groq API key at: https://console.groq.com/keys
Add to .env: GROQ_API_KEY=gsk_...

Cost: the free tier on openai/gpt-oss-20b offers 14,400 requests/day — more than
enough for high-volume demo runs and production benchmarks.
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
    Classify a payment failure.

    Priority Order:
    1. Deterministic rules-based classifier (app/services/classifier.py) is authoritative.
       If it matches a known category (anything other than UNKNOWN), use that result directly
       without calling the LLM — eliminating cost, latency, and hallucinated overrides.
    2. Only when the rules table returns UNKNOWN (unrecognized error code), consult
       Groq AI (openai/gpt-oss-20b) to provide an AI-suggested category, clearly flagged in
       the audit trail as an unverified suggestion for an unrecognized error code.
    3. If Groq is unavailable or fails, fall back to rules-based UNKNOWN.

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
        - bool (True = AI-generated, False = fell back to / matched rules)
    """
    from app.services.classifier import classify as rules_classify, explain_classification

    # Step 1: Run deterministic rules lookup table FIRST
    rule_category = rules_classify(error_reason)
    if rule_category != RootCauseCategory.UNKNOWN:
        base_explanation = explain_classification(error_reason, rule_category)
        reasoning = f"[Rules-based classifier, confident match — no AI call needed] {base_explanation}"
        logger.info(
            "Rules-based classifier matched %r -> %s (bypassed AI)",
            error_reason,
            rule_category,
        )
        return rule_category, reasoning, False

    # Step 2: Unrecognized code (UNKNOWN from rules) — consult Groq AI
    settings = get_settings()
    api_key = settings.groq_api_key or settings.gemini_api_key

    if not api_key:
        logger.info("GROQ_API_KEY not set for unrecognized code %r — using fallback UNKNOWN", error_reason)
        return _fallback(error_reason)

    try:
        return _call_groq(error_reason, amount, currency, api_key)
    except Exception as exc:
        logger.warning("Groq API call failed for unrecognized code (%s) — falling back to rules-based", exc)
        return _fallback(error_reason)


def _call_groq(
    error_reason: Optional[str],
    amount: int,
    currency: str,
    api_key: str,
) -> tuple[RootCauseCategory, str, bool]:
    """Make the Groq API call and parse the response."""
    try:
        from groq import Groq
    except ImportError:
        logger.warning("groq not installed — using rules-based classifier")
        return _fallback(error_reason)

    client = Groq(api_key=api_key)

    user_prompt = _USER_PROMPT_TEMPLATE.format(
        error_reason=error_reason or "(no reason provided)",
        amount_inr=round(amount / 100, 2),
        currency=currency,
    )

    chat_completion = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        max_tokens=1000,
        response_format={"type": "json_object"},
    )

    raw_text = chat_completion.choices[0].message.content or "{}"

    # Parse JSON response
    data = json.loads(raw_text.strip())
    category_str = data.get("category", "unknown").strip().lower()
    reasoning = data.get("reasoning", "").strip()
    confidence = data.get("confidence", "medium")

    # Validate category
    if category_str not in _VALID_CATEGORIES:
        logger.warning("LLM returned unknown category %r — mapping to UNKNOWN", category_str)
        category_str = "unknown"

    category = RootCauseCategory(category_str)

    # Enrich the reasoning with unverified AI attribution for unrecognized code
    full_reasoning = (
        f"[AI-suggested, unverified — unrecognized error code not in rules table] {reasoning} "
        f"(Raw error_reason: '{error_reason}')"
    )

    logger.info(
        "Groq suggested classification for unrecognized code %r -> %s (confidence: %s)",
        error_reason,
        category,
        confidence,
    )
    return category, full_reasoning, True


def _fallback(error_reason: Optional[str]) -> tuple[RootCauseCategory, str, bool]:
    """Fall back to rules-based classifier when Groq is unavailable."""
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

    Uses Groq (openai/gpt-oss-20b) if available, otherwise falls back to a smart Hinglish template.
    """
    settings = get_settings()
    amount_inr = round(amount / 100, 2)
    api_key = settings.groq_api_key or settings.gemini_api_key

    if api_key:
        try:
            from groq import Groq
            client = Groq(api_key=api_key)

            prompt = (
                f"You are a polite customer care agent for an Indian e-commerce store. "
                f"Write a short, friendly, 2-sentence WhatsApp message in conversational Hinglish "
                f"(mix of Hindi and English written in Latin script) telling the customer that their payment of ₹{amount_inr} "
                f"failed due to '{error_reason or category.value}'. "
                f"Reassure them their cart is reserved, and ask them to complete the payment via this link: {link_url}. "
                f"Keep it professional, empathetic, and urgent."
            )
            chat_completion = client.chat.completions.create(
                model="openai/gpt-oss-20b",
                messages=[
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=500,
            )
            content = chat_completion.choices[0].message.content
            if content:
                return content.strip()
        except Exception as exc:
            logger.warning("Groq recovery message generation failed (%s) — using template", exc)

    # Fallback Hinglish Templates
    cat_hints = {
        RootCauseCategory.CARD_DECLINED: "card decline hone ki wajah se",
        RootCauseCategory.INSUFFICIENT_FUND: "insufficient balance ki वजह se",
        RootCauseCategory.AUTHENTICATION_FAILED: "OTP / 3DS authentication complete na hone ki wajah se",
        RootCauseCategory.SUBSCRIPTION_FAILED: "mandate debit complete na hone ki वजह se",
        RootCauseCategory.GATEWAY_TECHNICAL_ERROR: "technical bank error ki वजह se",
        RootCauseCategory.UNKNOWN: "technical issue ki वजह se",
    }
    hint = cat_hints.get(category, "payment issue ki वजह se")

    return (
        f"Aapka ₹{amount_inr:,.0f} ka payment {hint} complete nahi ho paya. "
        f"Aapka order reserve rakha gaya hai! Safe recovery link se payment complete karein: {link_url}"
    )
