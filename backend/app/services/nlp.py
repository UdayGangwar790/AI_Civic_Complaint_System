import re
from typing import Optional

from app.schemas.nlp import (
    CivicIssueCategory,
    ExtractedEntity,
    Language,
    NLPAnalysisRequest,
    NLPAnalysisResponse,
)

# Multilingual keywords for civic issue classification
MANHOLE_KEYWORDS = {
    "en": [
        "manhole", "drain cover", "open lid", "gutter", "sewer", "sewage", "pit",
        "chamber", "inspection chamber", "drainage lid", "storm drain"
    ],
    "hi": [
        "मैनहोल", "गटर", "नाली का ढक्कन", "खुला ढक्कन", "सीवर", "चैंबर", "गड्ढा", "नाला"
    ],
    "hinglish": [
        "manhole", "gutter", "naali", "nali", "khula manhole", "dhakkan", "dhakan",
        "sewer", "sewage", "pit", "gaddha", "chamber", "open manhole"
    ],
}

ROADSIGN_KEYWORDS = {
    "en": [
        "road sign", "traffic sign", "signboard", "sign board", "direction board",
        "broken sign", "missing sign", "speed limit sign", "street sign", "symbol board"
    ],
    "hi": [
        "रोड साइन", "साइनबोर्ड", "यातायात संकेत", "दिशा बोर्ड", "टूटा साइन", "संकेतक",
        "सड़क संकेत", "बोर्ड गिर गया"
    ],
    "hinglish": [
        "road sign", "sign board", "signboard", "traffic sign", "toota sign",
        "board gayab", "direction board", "symbol", "board gir gaya"
    ],
}

WATERLOGGING_KEYWORDS = {
    "en": [
        "waterlogging", "water logging", "water stagnation", "flooding", "waterlogged",
        "stagnant water", "puddle", "drainage blockage", "water accumulated", "rainwater"
    ],
    "hi": [
        "जलभराव", "पानी भरा", "बाढ़", "सड़क पर पानी", "नाली जाम", "कीचड़", "पानी जमा",
        "जलजमाव"
    ],
    "hinglish": [
        "waterlogging", "water logging", "paani bhara", "pani bhara", "pani jama",
        "paani jama", "water jam", "road pe pani", "drainage block", "puddle", "flood",
        "water block"
    ],
}

# Textual Severity Signals (Textual indicators of reported urgency / severity)
SEVERITY_PATTERNS = [
    (r"\b(dangerous|danger|hazardous|perilous)\b", "dangerous"),
    (r"\b(खतरनाक|खतरा|जोखिम)\b", "dangerous"),
    (r"\b(khatarnak|khatra|danger)\b", "dangerous"),

    (r"\b(accident|crashed|collision)\b", "accident"),
    (r"\b(दुर्घटना|हादसा|टक्कर)\b", "accident"),
    (r"\b(accident|hadsa|takkar)\b", "accident"),

    (r"\b(injury|injured|hurt|bleeding|wound|fracture)\b", "injury"),
    (r"\b(चोट|घायल|जख्मी)\b", "injury"),
    (r"\b(chot|ghayal|injur)\b", "injury"),

    (r"\b(blocked road|road blocked|impassable|traffic halted)\b", "blocked road"),
    (r"\b(सड़क बंद|रास्ता बंद|जाम)\b", "blocked road"),
    (r"\b(road block|rasta band|sadak band)\b", "blocked road"),

    (r"\b(deep|open|uncovered|deep pit)\b", "deep/open"),
    (r"\b(गहरा|खुला|बिना ढक्कन)\b", "deep/open"),
    (r"\b(gehra|khula|bina dhakkan|deep)\b", "deep/open"),

    (r"\b(night visibility|dark|no street light|unlit|darkness)\b", "night visibility issue"),
    (r"\b(रात में|अंधेरा|दिखाई नहीं देता)\b", "night visibility issue"),
    (r"\b(raat me|andhera|dikhta nahi)\b", "night visibility issue"),

    (r"\b(severe flooding|submerged|massive water|knee deep)\b", "severe flooding"),
    (r"\b(गंभीर जलभराव|जलमग्न|डूब)\b", "severe flooding"),
    (r"\b(bahut pani|doob|massive water)\b", "severe flooding"),

    (r"\b(repeated|repeatedly|again|multiple times|frequent)\b", "repeated occurrence"),
    (r"\b(बार-बार|फिर से|लगातार)\b", "repeated occurrence"),
    (r"\b(baar baar|bar bar|phir se|repeated)\b", "repeated occurrence"),

    (r"\b(emergency|urgent|immediate action|critical)\b", "emergency-like wording"),
    (r"\b(आपातकालीन|तुरंत|जल्द से जल्द)\b", "emergency-like wording"),
    (r"\b(emergency|urgent|turant|jald)\b", "emergency-like wording"),
]

# Risk Signals (Physical hazard risks mentioned in text)
RISK_PATTERNS = [
    (r"\b(fall|falling|fell into|someone may fall|drop)\b", "fall hazard"),
    (r"\b(गिर|गिरना|गिर सकता|गिर गया)\b", "fall hazard"),
    (r"\b(gir sakta|gir gaya|girne ka)\b", "fall hazard"),

    (r"\b(vehicle damage|tyre damage|bike skid|car trapped)\b", "vehicle damage risk"),
    (r"\b(गाड़ी फंस|टायर|गाड़ी खराब)\b", "vehicle damage risk"),
    (r"\b(gadi|gaadi|skid|tyre)\b", "vehicle damage risk"),

    (r"\b(pedestrian|walking|school child|children|elderly)\b", "pedestrian vulnerability"),
    (r"\b(पैदल|बच्चे|बुजुर्ग)\b", "pedestrian vulnerability"),
    (r"\b(paidal|bachhe|buzurg)\b", "pedestrian vulnerability"),

    (r"\b(drowning|electrocution|electric pole|open wire)\b", "electrocution or submersion risk"),
    (r"\b(करंट|तार|डूबने)\b", "electrocution or submersion risk"),
    (r"\b(current|taar|wire)\b", "electrocution or submersion risk"),
]

# Common Indian localities, cities, states for entity extraction
KNOWN_CITIES = {
    "delhi", "new delhi", "bengaluru", "bangalore", "mumbai", "pune", "hyderabad",
    "chennai", "kolkata", "noida", "gurgaon", "gurugram", "lucknow", "jaipur",
    "ahmedabad", "chandigarh", "ghaziabad", "faridabad"
}

KNOWN_STATES = {
    "karnataka", "maharashtra", "delhi", "uttar pradesh", "haryana",
    "tamil nadu", "telangana", "rajasthan", "gujarat", "west bengal"
}

KNOWN_LOCALITIES = {
    "koramangala", "indiranagar", "whitefield", "jayanagar", "hsr layout",
    "jp nagar", "electronic city", "hebbal", "rohini", "dwarka", "connaught place",
    "karol bagh", "saket", "lajpat nagar", "andheri", "bandra", "dadar", "borivali",
    "kothrud", "wakad", "hinjewadi", "gomti nagar", "aliganj", "hazratganj"
}

HINGLISH_INDICATOR_WORDS = {
    "paani", "pani", "sadak", "gaddha", "khatra", "gir", "bahut", "hai", "yeh",
    "yahan", "pe", "khula", "dhakkan", "toota", "bhi", "karo", "hoga", "raat",
    "dikhta", "nahi", "tha", "raha", "gaya", "kripya", "samne", "pass", "mein"
}


def detect_language(text: str, explicit_lang: Optional[str] = None) -> tuple[str, float]:
    """
    Identifies text language: English ('en'), Hindi ('hi'), or Hinglish ('hinglish').
    If explicit_lang is provided and supported, respects it with high confidence.
    """
    if explicit_lang in ("en", "hi", "hinglish"):
        return explicit_lang, 0.95

    if not text.strip():
        return "en", 0.50

    # Check for Devanagari script range \u0900-\u097F
    devanagari_chars = len(re.findall(r"[\u0900-\u097F]", text))
    total_alpha = len(re.findall(r"[a-zA-Z\u0900-\u097F]", text))

    if total_alpha > 0 and (devanagari_chars / total_alpha) > 0.30:
        return "hi", 0.92

    # Check for Hinglish vocabulary
    tokens = set(re.findall(r"\b[a-zA-Z]{2,}\b", text.lower()))
    hinglish_matches = tokens.intersection(HINGLISH_INDICATOR_WORDS)

    if len(hinglish_matches) >= 2 or (len(tokens) > 0 and len(hinglish_matches) / len(tokens) >= 0.15):
        confidence = min(0.85, 0.60 + len(hinglish_matches) * 0.08)
        return "hinglish", round(confidence, 2)

    return "en", 0.88


def extract_keywords_and_category(
    text: str,
    lang: str,
    cv_issue_class: Optional[str] = None,
) -> tuple[CivicIssueCategory, float, list[str]]:
    """
    Extracts civic issue keywords and matches category with explainable confidence.
    Supports CV issue class alignment if provided.
    """
    text_lower = text.lower()
    matched_manhole: list[str] = []
    matched_sign: list[str] = []
    matched_water: list[str] = []

    # Check all languages in lexicons for cross-lingual coverage
    for l_key in ("en", "hi", "hinglish"):
        for kw in MANHOLE_KEYWORDS[l_key]:
            if kw.lower() in text_lower:
                matched_manhole.append(kw)
        for kw in ROADSIGN_KEYWORDS[l_key]:
            if kw.lower() in text_lower:
                matched_sign.append(kw)
        for kw in WATERLOGGING_KEYWORDS[l_key]:
            if kw.lower() in text_lower:
                matched_water.append(kw)

    # De-duplicate
    matched_manhole = list(dict.fromkeys(matched_manhole))
    matched_sign = list(dict.fromkeys(matched_sign))
    matched_water = list(dict.fromkeys(matched_water))

    counts = {
        "open_damaged_manhole": len(matched_manhole),
        "damaged_missing_road_sign": len(matched_sign),
        "road_waterlogging": len(matched_water),
    }

    # Best text match
    sorted_classes = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    best_cat, best_count = sorted_classes[0]

    # Incorporate CV prior if provided and compatible
    if cv_issue_class in counts and counts[cv_issue_class] > 0:
        best_cat = cv_issue_class
        best_count = counts[cv_issue_class]

    if best_count == 0:
        # Check if CV issue was supplied without contradictory text
        if cv_issue_class in counts:
            return cv_issue_class, 0.50, []
        return "other_civic_issue", 0.30, []

    if best_cat == "open_damaged_manhole":
        keywords = matched_manhole
    elif best_cat == "damaged_missing_road_sign":
        keywords = matched_sign
    else:
        keywords = matched_water

    confidence = min(0.95, 0.60 + (best_count * 0.10))
    return best_cat, round(confidence, 2), keywords


def extract_severity_and_risk(text: str) -> tuple[list[str], list[str]]:
    """
    Extracts textual severity signals and risk signals.
    Note: These are TEXTUAL SIGNALS only and do not verify real-world occurrence.
    """
    severity_signals: list[str] = []
    for pattern, signal_name in SEVERITY_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            if signal_name not in severity_signals:
                severity_signals.append(signal_name)

    risk_signals: list[str] = []
    for pattern, risk_name in RISK_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            if risk_name not in risk_signals:
                risk_signals.append(risk_name)

    return severity_signals, risk_signals


def extract_entities(text: str) -> list[ExtractedEntity]:
    """
    Extracts road name, locality, landmark, ward, city, district, state from text.
    Does NOT fabricate entities. Returns provenance source='text'.
    """
    entities: list[ExtractedEntity] = []
    seen: set[str] = set()

    def add_entity(name: str, entity_type: str):
        cleaned = name.strip(" ,.-:;")
        if cleaned and len(cleaned) >= 2 and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            entities.append(ExtractedEntity(name=cleaned, type=entity_type, source="text"))

    # 1. Ward pattern (e.g. Ward 12, Ward No. 45, ward number 102)
    ward_matches = re.finditer(r"\b(?:ward\s*(?:no\.?|number)?\s*(\d+))\b", text, re.IGNORECASE)
    for m in ward_matches:
        add_entity(f"Ward {m.group(1)}", "ward")

    # 2. Road pattern (e.g. MG Road, Ring Road, Outer Ring Road, 100 Feet Road, NH 44, ... Marg, ... Rasta)
    road_matches = re.finditer(
        r"\b([A-Za-z0-9][a-zA-Z0-9\s\.\-]{1,30}?\s+(?:Road|Marg|Street|Avenue|Lane|Path|Rasta|Highway|Expressway|Flyover|Bypass|Chowk))\b",
        text,
        re.IGNORECASE,
    )
    for m in road_matches:
        cand = m.group(1).strip()
        # Filter out common false positives
        if not re.match(r"^(the|this|that|near|on|a|an)\s", cand, re.IGNORECASE):
            add_entity(cand, "road")
        else:
            add_entity(re.sub(r"^(the|this|that|near|on|a|an)\s+", "", cand, flags=re.IGNORECASE), "road")

    # Sector pattern (e.g. Sector 14, Sector 62)
    sector_matches = re.finditer(r"\b(Sector\s*[-]?\s*\d+[A-Za-z]?)\b", text, re.IGNORECASE)
    for m in sector_matches:
        add_entity(m.group(1), "locality")

    # 3. Landmark pattern (e.g. near Metro Station, opposite City Hospital, ke pass, ke samne)
    landmark_matches = re.finditer(
        r"\b(?:near|opp|opposite|behind|next to|beside|in front of|ke\s+pass|ke\s+samne)\s+([A-Za-z0-9][a-zA-Z0-9\s\.\-]{2,30}?)(?=[,.;\n]|$|\s+near|\s+and|\s+is|\s+hai)",
        text,
        re.IGNORECASE,
    )
    for m in landmark_matches:
        cand = m.group(1).strip()
        if len(cand) >= 3 and not re.match(r"^(a|an|the|my|our)\s*$", cand, re.IGNORECASE):
            add_entity(cand, "landmark")

    # 4. Dictionary lookup for Known Cities, Localities, States
    text_lower = text.lower()
    for loc in KNOWN_LOCALITIES:
        if re.search(r"\b" + re.escape(loc) + r"\b", text_lower):
            add_entity(loc.title(), "locality")

    for city in KNOWN_CITIES:
        if re.search(r"\b" + re.escape(city) + r"\b", text_lower):
            add_entity(city.title(), "city")

    for state in KNOWN_STATES:
        if re.search(r"\b" + re.escape(state) + r"\b", text_lower):
            add_entity(state.title(), "state")

    return entities


def generate_normalized_summary(
    title: str,
    category: str,
    lang: str,
    severity_signals: list[str],
    entities: list[ExtractedEntity],
) -> str:
    """
    Generates a clear, neutral summary representing the citizen complaint text.
    """
    cat_label = category.replace("_", " ").title()
    loc_names = [e.name for e in entities if e.type in ("road", "locality", "landmark")]
    loc_str = f" at {', '.join(loc_names[:2])}" if loc_names else ""
    sev_str = f" with reported signals: {', '.join(severity_signals[:3])}" if severity_signals else ""
    return f"[{lang.upper()}] Civic report of {cat_label}{loc_str}{sev_str}."


def analyze_complaint_text(request: NLPAnalysisRequest) -> NLPAnalysisResponse:
    """
    Primary NLP analysis pipeline for M3.6 Complaint Intelligence.
    Preserves original complaint text without silent modification.
    """
    full_text = f"{request.title or ''} {request.description or ''}".strip()

    # Handle completely empty text
    if not full_text:
        return NLPAnalysisResponse(
            detected_language="en",
            issue_category="other_civic_issue",
            issue_confidence=0.0,
            issue_keywords=[],
            severity_signals=[],
            risk_signals=[],
            extracted_entities=[],
            normalized_summary="Empty complaint text provided.",
            confidence=0.0,
            explanation="No complaint title or description was provided for NLP processing.",
            approach="rule_based_multilingual_lexicon_baseline",
        )

    # 1. Language detection
    detected_lang, lang_conf = detect_language(full_text, explicit_lang=request.language)

    # 2. Issue categorization and keyword extraction
    category, cat_conf, keywords = extract_keywords_and_category(
        full_text,
        lang=detected_lang,
        cv_issue_class=request.issue_class,
    )

    # 3. Severity and risk signals extraction
    severity_signals, risk_signals = extract_severity_and_risk(full_text)

    # 4. Entity extraction
    entities = extract_entities(full_text)

    # 5. Summary generation
    summary = generate_normalized_summary(
        title=request.title,
        category=category,
        lang=detected_lang,
        severity_signals=severity_signals,
        entities=entities,
    )

    # 6. Overall confidence calculation
    overall_conf = round(min(1.0, (cat_conf * 0.70) + (lang_conf * 0.30)), 2)

    # 7. Transparent explanation
    reasons: list[str] = []
    reasons.append(f"Language identified as '{detected_lang}' (confidence {lang_conf}).")
    if keywords:
        reasons.append(f"Matched civic keywords for '{category}': {', '.join(keywords)}.")
    else:
        reasons.append(f"Categorized as '{category}' based on baseline context without specific keyword match.")
    if severity_signals:
        reasons.append(f"Identified textual severity indicators: {', '.join(severity_signals)}.")
    if risk_signals:
        reasons.append(f"Identified safety risk wording: {', '.join(risk_signals)}.")
    if entities:
        ent_desc = [f"{e.name} ({e.type})" for e in entities]
        reasons.append(f"Extracted entities from text: {', '.join(ent_desc)}.")
    reasons.append(
        "Note: Textual signals represent reported citizen concerns and do not prove that an accident or injury occurred."
    )

    explanation = " ".join(reasons)

    return NLPAnalysisResponse(
        detected_language=detected_lang,
        issue_category=category,
        issue_confidence=cat_conf,
        issue_keywords=keywords,
        severity_signals=severity_signals,
        risk_signals=risk_signals,
        extracted_entities=entities,
        normalized_summary=summary,
        confidence=overall_conf,
        explanation=explanation,
        approach="rule_based_multilingual_lexicon_baseline",
    )