# M3.6 — NLP Complaint Intelligence

## 1. Objective
The objective of Module 3.6 is to transform unstructured citizen complaint text into structured, explainable civic intelligence without modifying or rewriting the citizen's original words. The module analyzes complaints across English, Hindi, and Hinglish, identifying civic issue categories, textual keywords, severity and safety risk signals, and geographic entities with explicit provenance.

## 2. Supported Languages
- **English (`en`)**: Supported via standard English civic lexicon and entity patterns.
- **Hindi (`hi`)**: Supported via Devanagari script detection (`[\u0900-\u097F]`) and native Hindi civic terminology.
- **Hinglish (`hinglish`)**: Supported via phonetic romanized Hindi vocabulary dictionaries (e.g., `paani`, `sadak`, `khula`, `gaddha`, `khatarnak`, `dhakkan`).

Language selection is explicit when provided by the citizen in the request; otherwise, automated heuristic script and token detection is executed.

## 3. NLP Architecture & Approach
To maintain full scientific integrity, CVKI does not fabricate training data or claim an unverified fine-tuned neural model. The module uses a transparent **rule-based multilingual lexicon baseline** combined with deterministic regular expression pattern matching and scikit-learn text feature extraction utilities:
- **Lexicons**: Curated multilingual dictionaries mapping domain terms across the three supported civic classes (`open_damaged_manhole`, `damaged_missing_road_sign`, `road_waterlogging`) and generic unclassified civic issues (`other_civic_issue`).
- **Severity Signals**: Textual indicators of citizen concern, such as `dangerous`, `accident`, `injury`, `blocked road`, `deep/open`, `night visibility issue`, `severe flooding`, `repeated occurrence`, and `emergency-like wording`.
- **Risk Signals**: Safety risk wording such as `fall hazard`, `vehicle damage risk`, `pedestrian vulnerability`, and `electrocution or submersion risk`.
- **Entity Extraction**: Deterministic extraction of road names (e.g., `MG Road`, `Ring Road`, `NH 44`, `... Marg`), landmarks (`near Metro Station`, `opposite City Hospital`), wards (`Ward 45`), and known localities/cities (`Koramangala`, `Bengaluru`, `Delhi`). All extracted entities are assigned provenance `source = "text"`.
- **Provenance Principle**: NLP-extracted entities never overwrite authoritative GPS-derived reverse-geocoding data.

## 4. Model & Runtime Dependencies
- **Library**: Python Standard Library (`re`, `math`) and `scikit-learn` (`1.9.1`).
- **Runtime Footprint**: Zero heavy transformer downloads; instantaneous deterministic evaluation under 5 milliseconds.

## 5. API Specification
- **Endpoint**: `POST /api/v1/nlp/analyze`
- **Request Schema**:
```json
{
  "title": "Open manhole on MG Road",
  "description": "Deep open drain pit near Metro station, someone may fall and get injured.",
  "language": "en",
  "issue_class": "open_damaged_manhole"
}
```
- **Response Schema**:
```json
{
  "detected_language": "en",
  "issue_category": "open_damaged_manhole",
  "issue_confidence": 0.85,
  "issue_keywords": ["manhole", "drain", "open"],
  "severity_signals": ["dangerous", "injury", "deep/open"],
  "risk_signals": ["fall hazard"],
  "extracted_entities": [
    {"name": "MG Road", "type": "road", "source": "text"},
    {"name": "Metro Station", "type": "landmark", "source": "text"}
  ],
  "normalized_summary": "[EN] Civic report of Open Damaged Manhole at MG Road with reported signals: dangerous, injury, deep/open.",
  "confidence": 0.87,
  "explanation": "Language identified as 'en'. Matched civic keywords for 'open_damaged_manhole'. Identified textual severity indicators: dangerous, injury, deep/open.",
  "approach": "rule_based_multilingual_lexicon_baseline"
}
```

## 6. Disclaimers & Known Limitations
> [!IMPORTANT]
> **NLP analysis is decision-support and is not guaranteed to perfectly understand every multilingual or Hinglish complaint.**

- **Textual Signals Only**: Textual severity signals indicate reported citizen concerns and wording; they do not verify that a physical accident, injury, or emergency actually occurred.
- **Hinglish Variability**: Hinglish exhibits diverse informal spellings; novel phonetic variations not in the indicator dictionary may default to English categorization with lower confidence.
- **Entity Coverage**: Entity extraction relies on structured syntactic markers (e.g. `Road`, `Marg`, `near`, `opp`) and known city dictionaries; unlisted informal slang landmarks will not be extracted to avoid hallucination.

## 7. Verification Tests
Implemented in `backend/tests/test_nlp_m36.py` (16 tests):
1. English complaint parsing
2. Hindi complaint parsing
3. Hinglish complaint parsing
4. Empty description handling
5. Unknown civic issue categorization (`other_civic_issue`)
6. Manhole complaint keyword matching
7. Road-sign complaint keyword matching
8. Waterlogging complaint keyword matching
9. Multilingual keyword extraction
10. Risk and severity signal extraction
11. Entity extraction with provenance `source = "text"`
12. Protection against fabricated entities
13. Explicit language preference selection
14. Confidence bounds verification [0.0, 1.0]
15. Malformed request validation (422)
16. Complaint drafting API regression
