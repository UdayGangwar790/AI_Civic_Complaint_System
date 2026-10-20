"""
CVKI - Civic Vision & Knowledge Intelligence
Module 9.4: Multilingual Vernacular Normalizer

Normalizes informal Indian citizen language (English, Hindi, Hinglish/Roman Hindi)
into the controlled CVKI civic vocabulary. Layers deterministically on top of M3.6 NLP
without replacing it.

CRITICAL EPISTEMIC PRINCIPLE:
Citizen language normalization standardizes lexical tokens; it does NOT verify physical reality.
All outputs strictly maintain epistemic state USER_REPORTED.
Confidence represents lexical matching confidence, NOT the probability that a defect physically exists.
"""

from datetime import datetime, timezone
import logging
import re
import unicodedata
from typing import Any, Optional

from app.services.multimodal.contracts import (
    AssertionType,
    EpistemicState,
    IssueCategory,
    VernacularNormalizationResult,
)
from app.services.multimodal.security import sanitize_text_pii

logger = logging.getLogger("cvki.services.multimodal.vernacular")

# =============================================================================
# Script & Language Detection Constants
# =============================================================================
_DEVANAGARI_REGEX = re.compile(r"[\u0900-\u097F]")
_LATIN_REGEX = re.compile(r"[a-zA-Z]")

# Hinglish civic grammatical markers
_HINGLISH_MARKERS = {
    "hai", "h", "hein", "hain", "pe", "par", "mein", "me", "se", "ka", "ki", "ke", "ko",
    "gaya", "gya", "gaye", "gyi", "toot", "toota", "khula", "bhara", "jama", "pani",
    "paani", "sadak", "naali", "nali", "dhakkan", "dhakan", "bina", "nahi", "nahin",
    "nhi", "na", "shayad", "lagta", "wala", "wali", "khatra", "gaddha", "khadda",
}

# Vernacular Lexical Spelling Variant Replacements (Hinglish -> Canonical Token)
_SPELLING_VARIANTS = [
    (r"\bpani\b", "paani"),
    (r"\bh\b", "hai"),
    (r"\bhein\b", "hai"),
    (r"\bhain\b", "hai"),
    (r"\bgya\b", "gaya"),
    (r"\btoota\b", "toot gaya"),
    (r"\btut gaya\b", "toot gaya"),
    (r"\btuta\b", "toot gaya"),
    (r"\btoot gya\b", "toot gaya"),
    (r"\bkhula pda\b", "khula"),
    (r"\bkhula pada\b", "khula"),
    (r"\bkhula h\b", "khula hai"),
    (r"\bkhada h\b", "khada hai"),
    (r"\bkhada hai\b", "jama hai"),
    (r"\bnali\b", "naali"),
    (r"\bdhakan\b", "dhakkan"),
    (r"\bkhadda\b", "gaddha"),
    (r"\bsadak\b", "road"),
    (r"\bgayab h\b", "missing hai"),
    (r"\bgayab\b", "missing"),
    (r"\bsign board gir gaya\b", "sign gir gaya"),
    (r"(?<!sign )\bboard gir gaya\b", "sign gir gaya"),
]

# Negation particles
_NEGATION_TERMS = {
    "nahi", "nahin", "nhi", "na", "no", "not", "neither", "nor", "never",
}

# Uncertainty particles
_UNCERTAINTY_TERMS = [
    r"\bshayad\b",
    r"\blagta hai\b",
    r"\blag raha hai\b",
    r"\blag rahi hai\b",
    r"\bmaybe\b",
    r"\bperhaps\b",
    r"\bprobably\b",
    r"\bpossibly\b",
    r"\bpata nahi\b",
    r"\bnot sure\b",
    r"\buncertain\b",
    r"\bho sakta hai\b",
]

# Question particles
_QUESTION_PATTERNS = [
    r"^\s*kya\b",
    r"\bkya\b.*\?",
    r"\bis there\b",
    r"\bare there\b",
    r"\bany\b.*\?",
    r"\?$",
]

# Canonical Civic Concept Keywords (aligned with M3.6 / M9.2)
_CANONICAL_MANHOLE = {
    "manhole", "drain cover", "open lid", "gutter", "sewer", "sewage", "pit",
    "chamber", "inspection chamber", "drainage lid", "storm drain",
    "मैनहोल", "गटर", "नाली का ढक्कन", "खुला ढक्कन", "सीवर", "चैंबर", "गड्ढा", "नाला",
    "naali", "dhakkan", "open manhole", "khula manhole", "gaddha",
}

_CANONICAL_ROADSIGN = {
    "road sign", "traffic sign", "signboard", "sign board", "direction board",
    "broken sign", "missing sign", "speed limit sign", "street sign", "symbol board",
    "रोड साइन", "साइनबोर्ड", "यातायात संकेत", "दिशा बोर्ड", "टूटा साइन", "संकेतक",
    "सड़क संकेत", "बोर्ड गिर गया",
    "toota sign", "board gayab", "sign toot gaya", "sign missing", "signboard",
    "sign gir gaya", "sign", "board",
}

_CANONICAL_WATERLOGGING = {
    "waterlogging", "water logging", "water stagnation", "flooding", "waterlogged",
    "stagnant water", "puddle", "drainage blockage", "water accumulated", "rainwater",
    "जलभराव", "पानी भरा", "बाढ़", "सड़क पर पानी", "नाली जाम", "कीचड़", "पानी जमा",
    "जलजमाव",
    "paani bhara", "paani jama", "water jam", "road pe paani", "pani bhara",
    "pani jama", "water block", "water stagnation", "paani", "pani", "water",
}



class MultilingualVernacularNormalizer:
    """
    Deterministic Multilingual Vernacular Normalizer (M9.4).
    Maps raw Hindi, English, and Hinglish citizen inputs to standardized CVKI civic concepts.
    Preserves assertion type, negation, uncertainty, and question forms.
    """

    def __init__(self):
        pass

    def detect_script_and_language(self, text: str) -> tuple[str, str]:
        """
        Detects script ('devanagari', 'latin', 'mixed') and language ('hi', 'hinglish', 'en', 'unknown').
        """
        has_devanagari = bool(_DEVANAGARI_REGEX.search(text))
        has_latin = bool(_LATIN_REGEX.search(text))

        if has_devanagari and has_latin:
            script = "mixed"
            lang = "hinglish"
        elif has_devanagari:
            script = "devanagari"
            lang = "hi"
        elif has_latin:
            script = "latin"
            # Distinguish English vs Hinglish by lexical markers
            words = set(re.findall(r"\b\w+\b", text.lower()))
            hinglish_overlap = words.intersection(_HINGLISH_MARKERS)
            lang = "hinglish" if len(hinglish_overlap) >= 1 else "en"
        else:
            script = "unknown"
            lang = "unknown"

        return script, lang

    def normalize_spelling(self, text: str) -> tuple[str, bool]:
        """
        Applies deterministic spelling and slang normalizations.
        Returns (normalized_text, normalization_applied).
        """
        # Unicode normalization
        normalized = unicodedata.normalize("NFC", text)
        applied = False

        norm_lower = normalized.lower()
        working_text = norm_lower

        for pattern, replacement in _SPELLING_VARIANTS:
            new_text = re.sub(pattern, replacement, working_text, flags=re.IGNORECASE)
            if new_text != working_text:
                applied = True
                working_text = new_text

        # Re-capitalize first letter if changed
        final_text = working_text.strip()
        if final_text != text.strip():
            applied = True

        return final_text, applied

    def detect_assertion_type(self, text: str) -> AssertionType:
        """
        Determines whether the input is ASSERTED, NEGATED, UNCERTAIN, or a QUESTION.
        """
        clean = text.lower().strip()

        # 1. Question detection
        for q_pat in _QUESTION_PATTERNS:
            if re.search(q_pat, clean):
                return AssertionType.QUESTION

        # 2. Uncertainty detection
        for uncert in _UNCERTAINTY_TERMS:
            if re.search(uncert, clean):
                return AssertionType.UNCERTAIN

        # 3. Negation detection (general)
        words = re.findall(r"\b\w+\b", clean)
        # Avoid treating "without lid" / "bina dhakkan" as report negation
        neg_words = [w for w in words if w in _NEGATION_TERMS]
        if neg_words:
            return AssertionType.NEGATED

        return AssertionType.ASSERTED

    def extract_categories_and_negations(
        self,
        text: str,
    ) -> tuple[list[IssueCategory], list[IssueCategory], list[str]]:
        """
        Extracts positive and negated candidate issue categories and matched canonical terms.
        """
        clean = text.lower()
        words = re.findall(r"\b\w+\b", clean)

        positive: list[IssueCategory] = []
        negated: list[IssueCategory] = []
        canonical_terms: list[str] = []

        def check_proximity_negation(target_phrases: set[str]) -> tuple[bool, bool, Optional[str]]:
            # returns (matched, is_negated, matched_term)
            for phrase in target_phrases:
                phrase_tokens = re.findall(r"\b\w+\b", phrase)
                if not phrase_tokens:
                    continue
                p_len = len(phrase_tokens)
                for i in range(len(words) - p_len + 1):
                    if words[i:i + p_len] == phrase_tokens:
                        # Check window before (up to 3 words)
                        start_window = max(0, i - 3)
                        preceding = words[start_window:i]
                        # Check window after (up to 2 words, e.g. "manhole khula nahi hai")
                        end_window = min(len(words), i + p_len + 3)
                        succeeding = words[i + p_len:end_window]

                        is_neg = any(w in _NEGATION_TERMS for w in preceding) or any(w in _NEGATION_TERMS for w in succeeding)
                        return True, is_neg, phrase
            return False, False, None

        # 1. Check manhole
        m_matched, m_neg, m_term = check_proximity_negation(_CANONICAL_MANHOLE)
        if m_matched:
            canonical_terms.append(m_term or "manhole")
            if m_neg:
                negated.append(IssueCategory.OPEN_DAMAGED_MANHOLE)
            else:
                positive.append(IssueCategory.OPEN_DAMAGED_MANHOLE)

        # 2. Check road sign
        s_matched, s_neg, s_term = check_proximity_negation(_CANONICAL_ROADSIGN)
        if s_matched:
            canonical_terms.append(s_term or "road_sign")
            if s_neg:
                negated.append(IssueCategory.DAMAGED_MISSING_ROAD_SIGN)
            else:
                positive.append(IssueCategory.DAMAGED_MISSING_ROAD_SIGN)

        # 3. Check waterlogging
        w_matched, w_neg, w_term = check_proximity_negation(_CANONICAL_WATERLOGGING)
        if w_matched:
            canonical_terms.append(w_term or "waterlogging")
            if w_neg:
                negated.append(IssueCategory.ROAD_WATERLOGGING)
            else:
                positive.append(IssueCategory.ROAD_WATERLOGGING)

        # Remove negated from positive if overlap
        for n in negated:
            if n in positive:
                positive.remove(n)

        return positive, negated, canonical_terms

    def extract_civic_entities(self, text: str) -> list[str]:
        """
        Extracts civic geographical references (roads, landmarks, colonies).
        """
        entities: list[str] = []
        # Match road / marg / nagar / colony patterns
        patterns = [
            r"\b([A-Za-z0-9\u0900-\u097F\s]+(?:road|marg|street|lane|nagar|colony|chowk|rasta|sadak))\b",
            r"(?:near|ke paas|paas)\s+([A-Za-z0-9\u0900-\u097F\s]{2,30})",
        ]
        for pat in patterns:
            matches = re.findall(pat, text, flags=re.IGNORECASE)
            for m in matches:
                clean_m = m.strip()
                if len(clean_m) > 2 and clean_m not in entities:
                    entities.append(clean_m)
        return entities[:10]

    def normalize(self, raw_text: str) -> VernacularNormalizationResult:
        """
        Executes complete M9.4 vernacular normalization pipeline.
        Guaranteed deterministic, bounded, explainable, and locked to USER_REPORTED.
        """
        # Step 1: PII Sanitization
        sanitized = sanitize_text_pii(raw_text)

        # Step 2: Script & Language Identification
        script, lang = self.detect_script_and_language(sanitized)

        # Step 3: Spelling & Slang Variant Normalization
        norm_text, norm_applied = self.normalize_spelling(sanitized)

        # Step 4: Assertion, Negation & Uncertainty Analysis
        assertion_type = self.detect_assertion_type(norm_text)

        # Step 5: Canonical Category Extraction & Proximity Negation
        pos_cats, neg_cats, canonical_terms = self.extract_categories_and_negations(norm_text)

        # If categories were negated, reflect in assertion type unless uncertain or question
        if neg_cats and not pos_cats and assertion_type not in {AssertionType.QUESTION, AssertionType.UNCERTAIN}:
            assertion_type = AssertionType.NEGATED


        # Step 6: Entity Extraction
        entities = self.extract_civic_entities(norm_text)

        # Step 7: Fallback & Confidence Assignment
        fallback_used = False
        if not pos_cats and not neg_cats:
            fallback_used = True
            confidence = 0.40
            explanation = "No standard civic defect keywords recognized; categorized as unclassified citizen claim."
        else:
            fallback_used = False
            if assertion_type == AssertionType.UNCERTAIN:
                confidence = 0.70
                explanation = "Citizen report contains uncertainty qualifiers ('shayad', 'lagta hai'); lexical match preserved."
            elif assertion_type == AssertionType.QUESTION:
                confidence = 0.65
                explanation = "Citizen phrased report in question form; lexical match preserved as inquiry."
            elif assertion_type == AssertionType.NEGATED:
                confidence = 0.90
                explanation = "Citizen report expresses negative defect assertion; negation explicitly preserved."
            else:
                confidence = 0.95
                explanation = "Citizen vernacular successfully normalized to canonical civic concept."

        return VernacularNormalizationResult(
            original_text=raw_text,
            normalized_text=norm_text,
            detected_language=lang,
            script=script,
            canonical_terms=canonical_terms,
            civic_entities=entities,
            issue_candidates=pos_cats,
            negated_candidates=neg_cats,
            assertion_type=assertion_type,
            normalization_applied=norm_applied,
            confidence=round(confidence, 2),
            epistemic_state=EpistemicState.USER_REPORTED,
            explanation=explanation,
            fallback_used=fallback_used,
            metadata={
                "sanitized_length": len(sanitized),
                "script": script,
                "detected_language": lang,
                "assertion_type": assertion_type.value,
                "normalized_at": datetime.now(timezone.utc).isoformat(),
            },
        )


# Shared singleton instance
multilingual_vernacular_normalizer = MultilingualVernacularNormalizer()
