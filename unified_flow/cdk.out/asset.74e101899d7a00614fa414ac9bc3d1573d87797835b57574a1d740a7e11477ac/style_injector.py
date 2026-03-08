"""
Style Injector Module

Injects culturally resonant visual keywords into image/video prompts
based on the selected style context (festival, region, industry).

Used by the Orchestrator Lambda to enrich Claude's visual prompts
with Indian color psychology, regional art motifs, and seasonal cues.
"""

# Cultural palette definitions based on PRD color psychology section
STYLE_PRESETS = {
    # ── Festivals ─────────────────────────────────────────────────
    "diwali": {
        "colors": "warm golden lighting, saffron and gold palette, deep orange glow, flickering diyas",
        "motifs": "rangoli patterns, marigold garlands, oil lamps, fireworks bokeh",
        "mood": "festive, celebratory, joyful, prosperous"
    },
    "holi": {
        "colors": "vibrant splashes of magenta, cyan, yellow, and green powder",
        "motifs": "color powder clouds, water splashes, pichkari, gulal",
        "mood": "energetic, playful, colorful, youthful"
    },
    "dussehra": {
        "colors": "rich red and green, golden borders, warm sunset tones",
        "motifs": "victory celebrations, traditional Indian architecture, mythological motifs",
        "mood": "triumphant, powerful, traditional, auspicious"
    },
    "eid": {
        "colors": "emerald green, white, silver, crescent moon glow",
        "motifs": "crescent moon, lanterns, intricate geometric patterns, dates and sweets",
        "mood": "spiritual, warm, generous, communal"
    },
    "pongal": {
        "colors": "earthy terracotta, turmeric yellow, green sugarcane fields",
        "motifs": "kolam patterns, clay pots, sugarcane, rice harvest",
        "mood": "harvest celebration, gratitude, rural warmth"
    },
    "christmas": {
        "colors": "red and green with gold accents, snow white, fairy light warmth",
        "motifs": "stars, bells, candles, pine branches, wrapped gifts",
        "mood": "joyful, cozy, giving, festive"
    },

    # ── Regional Art Styles ───────────────────────────────────────
    "warli": {
        "colors": "terracotta brown background, white line art",
        "motifs": "Warli tribal art, geometric human figures, circle formations, Maharashtra folk art",
        "mood": "earthy, indigenous, authentic, storytelling"
    },
    "madhubani": {
        "colors": "vibrant primary colors, red borders, intricate fills",
        "motifs": "Madhubani painting style, fish motifs, lotus, Bihar folk art, double-line borders",
        "mood": "ornate, heritage, detailed, colorful"
    },
    "kalamkari": {
        "colors": "natural dyes, indigo, rust red, earthy olive green",
        "motifs": "Kalamkari pen-drawn florals, mythological scenes, Andhra Pradesh textile art",
        "mood": "elegant, handcrafted, narrative"
    },
    "pattachitra": {
        "colors": "bold red, yellow, green on dark backgrounds",
        "motifs": "Pattachitra scroll paintings, ornate borders, Odisha folk art",
        "mood": "mythological, intricate, traditional"
    },

    # ── Seasons ───────────────────────────────────────────────────
    "winter": {
        "colors": "cool blue tones, warm amber indoor lighting, soft whites",
        "motifs": "steam from hot drinks, cozy blankets, misty mountains, warm sweaters",
        "mood": "cozy, warm, inviting, nurturing"
    },
    "monsoon": {
        "colors": "lush greens, grey skies, silver rain streaks, petrichor ambiance",
        "motifs": "rain droplets on leaves, chai and pakoras, umbrellas, wet streets",
        "mood": "romantic, refreshing, nostalgic"
    },
    "summer": {
        "colors": "bright yellows, cyan sky, mango orange, cooling blues",
        "motifs": "mangoes, lassi, fans, water splashes, bright sunshine",
        "mood": "vibrant, refreshing, energetic"
    },

    # ── Industry-specific Aesthetics ──────────────────────────────
    "healthcare": {
        "colors": "ethereal blue, clean white, soft green, calming lavender",
        "motifs": "clean medical environments, caring hands, healthy lifestyle imagery",
        "mood": "trustworthy, clinical, caring, professional"
    },
    "fintech": {
        "colors": "deep navy, electric blue, gold accents, neon green highlights",
        "motifs": "digital interfaces, secure lock icons, growth charts, smartphone payments",
        "mood": "modern, secure, innovative, reliable"
    },
    "education": {
        "colors": "warm yellow, ocean blue, chalkboard green, bright white",
        "motifs": "books, graduation caps, lightbulbs, classroom settings, notebooks",
        "mood": "inspiring, approachable, knowledgeable"
    },
    "agriculture": {
        "colors": "earthy brown, harvest gold, lush green, sky blue",
        "motifs": "fields, tractors, crops, farmer hands, sunrise over farmland",
        "mood": "rooted, prosperous, hardworking, natural"
    }
}


def inject_style(visual_prompt: str, style_key: str) -> str:
    """
    Enriches a visual prompt with culturally appropriate color,
    motif, and mood keywords based on the selected style.

    Args:
        visual_prompt: The original prompt from Claude's manifest.
        style_key: One of the keys in STYLE_PRESETS (e.g., "diwali", "warli").

    Returns:
        An enriched prompt string with style cues appended.
    """
    style = STYLE_PRESETS.get(style_key.lower())
    if not style:
        return visual_prompt

    enrichment = (
        f" Style: {style['colors']}. "
        f"Motifs: {style['motifs']}. "
        f"Mood: {style['mood']}."
    )

    return visual_prompt.rstrip('.') + '.' + enrichment


def get_available_styles() -> list:
    """Returns a list of all available style preset keys."""
    return list(STYLE_PRESETS.keys())
