from typing import Any
import logging

from app.schemas.guidance import (
    GuidanceLocation,
    GovernmentGuidanceRequest,
    GovernmentGuidanceResponse,
)
from app.services.authority import is_trusted_official_domain
from app.services.complaint import ISSUE_DEFINITIONS

logger = logging.getLogger("cvki.guidance")


def _format_location(location: Any) -> str:
    if not location:
        return "Location details not specified"
    if isinstance(location, dict):
        road = location.get("road")
        area = location.get("area")
        city = location.get("city")
        state = location.get("state")
        lat = location.get("latitude")
        lon = location.get("longitude")
    else:
        road = getattr(location, "road", None)
        area = getattr(location, "area", None)
        city = getattr(location, "city", None)
        state = getattr(location, "state", None)
        lat = getattr(location, "latitude", None)
        lon = getattr(location, "longitude", None)

    parts = [road, area, city, state]
    available = [p for p in parts if p]
    if available:
        return ", ".join(available)
    if lat is not None and lon is not None:
        try:
            return f"{float(lat):.5f}, {float(lon):.5f}"
        except (ValueError, TypeError):
            pass
    return "Location details not specified"


def generate_government_guidance(request: GovernmentGuidanceRequest) -> GovernmentGuidanceResponse:
    """
    Generates step-by-step citizen guidance for submitting civic complaints through official channels.
    Never submits automatically. Preserves external_submission_status = 'not_submitted'.
    Preserves factual official names and URLs untranslated.
    """
    definition = ISSUE_DEFINITIONS.get(request.issue_category)
    issue_label = definition.label if definition else request.issue_category.replace("_", " ").title()
    language = request.language or "en"
    location_summary = _format_location(request.location)

    authority = request.authority
    auth_status = authority.authority_status if authority else "not_verified"

    official_portal_url: str | None = None
    party_name: str | None = None
    official_source_name: str | None = None

    if authority:
        # Check maintenance authority first, then road owner
        preferred_party = authority.maintenance_authority or authority.road_owner
        if preferred_party and preferred_party.name:
            party_name = preferred_party.name
            candidate_url = preferred_party.official_portal_url or (
                preferred_party.contact.url if preferred_party.contact else None
            )
            if candidate_url and is_trusted_official_domain(candidate_url):
                official_portal_url = candidate_url

        # Check official sources list if portal URL not found on party
        if not official_portal_url and authority.sources:
            for src in authority.sources:
                if src.source_url and is_trusted_official_domain(src.source_url):
                    official_portal_url = src.source_url
                    official_source_name = src.source_name
                    break

        if not official_source_name and authority.sources:
            official_source_name = authority.sources[0].source_name
        elif not official_source_name and authority.evidence:
            official_source_name = authority.evidence[0].source_name

    # Determine channel and authority basis based on verification state
    limitations: list[str] = [
        "CVKI provides citizen guidance only. It does not automatically submit complaints to government portals.",
        "External government submission status remains 'not_submitted'. You must submit directly to receive an official government tracking number.",
    ]

    if auth_status == "verified":
        if official_portal_url:
            recommended_channel = f"Official Grievance Portal ({party_name or 'Responsible Road Authority'})"
            authority_basis = f"Grounding verified by official records for {party_name or 'the responsible agency'}."
        else:
            recommended_channel = f"Official Citizen Service Center / Office ({party_name or 'Responsible Road Authority'})"
            authority_basis = f"Authority verified for {party_name}, but online grievance portal URL was not verified."
            limitations.append("Official online portal URL could not be verified; submit via local municipal / division office.")
    elif auth_status == "partially_verified":
        road_owner_name = authority.road_owner.name if (authority and authority.road_owner) else "Identified Road Owner"
        recommended_channel = f"Jurisdictional Division Office ({road_owner_name})"
        authority_basis = f"Road ownership verified for {road_owner_name}; specific maintenance division or contractor requires verification."
        limitations.append("Authority information is partially verified. Confirm division jurisdiction before filing.")
    else:
        recommended_channel = "Official authority contact/process could not be verified."
        authority_basis = "No authoritative road ownership or maintenance source could be verified for this location."
        official_portal_url = None
        limitations.append("CVKI could not verify the responsible authority from available official sources. Please verify the authority before submitting a government complaint.")
        limitations.append("Administrative city or state context alone does not establish road maintenance jurisdiction.")

    # Step-by-step instructions in selected language
    if language == "hi":
        if official_portal_url:
            step_1 = f"आधिकारिक सरकारी शिकायत पोर्टल ({official_portal_url}) खोलें।"
        elif party_name:
            step_1 = f"{party_name} के आधिकारिक नागरिक सेवा केंद्र या पोर्टल पर जाएं।"
        else:
            step_1 = "संबंधित नगर निगम या सड़क विभाग के आधिकारिक कार्यालय/पोर्टल का पता लगाएं।"

        steps = [
            step_1,
            f"{issue_label} के लिए संबंधित नागरिक शिकायत / सड़क रखरखाव श्रेणी चुनें।",
            f"सत्यापित स्थान विवरण दर्ज करें ({location_summary})।",
            "घटनास्थल पर ली गई स्पष्ट फोटो संलग्न करें।",
            "पोर्टल के विवरण बॉक्स में CVKI द्वारा तैयार शिकायत ड्राफ्ट को पेस्ट या एडिट करें।",
            "सभी विवरणों की पुष्टि करें और आधिकारिक सरकारी पोर्टल के माध्यम से सीधे सबमिट करें।",
            "भविष्य की ट्रैकिंग के लिए प्राप्त आधिकारिक सरकारी संदर्भ / टोकन नंबर नोट करके सुरक्षित रखें।",
        ]

        what_to_attach = [
            "नागरिक समस्या (मैनहोल, क्षतिग्रस्त संकेत, या जलभराव) की घटनास्थल पर ली गई स्पष्ट फोटो।",
            "सटीक सड़क का नाम या जीपीएस निर्देशांक।",
        ]
        what_to_write = [
            "शीर्षक: CVKI द्वारा जनरेट किया गया संक्षिप्त शीर्षक उपयोग करें।",
            "विवरण: समस्या की गंभीरता और मरम्मत के अनुरोध सहित ड्राफ्ट विवरण पेस्ट करें।",
        ]

    elif language == "hinglish":
        if official_portal_url:
            step_1 = f"Official government complaint portal ({official_portal_url}) open kijiye."
        elif party_name:
            step_1 = f"{party_name} ke official citizen service center ya portal par visit kijiye."
        else:
            step_1 = "Local municipal corporation ya road department ke official office/portal ka pata kijiye."

        steps = [
            step_1,
            f"{issue_label} ke liye relevant civic issue / road maintenance category select kijiye.",
            f"Verified location details enter kijiye ({location_summary}).",
            "Site par li gayi clear photo attach kijiye.",
            "Portal ke description field mein CVKI ka banaya gaya complaint draft paste ya edit kijiye.",
            "Sabhi details check karke official government portal ke zariye direct submit kijiye.",
            "Future tracking ke liye official government acknowledgement / reference number save kijiye.",
        ]

        what_to_attach = [
            "Civic issue (manhole, damaged road sign, ya waterlogging) ki clear photo.",
            "Exact road name ya GPS coordinates.",
        ]
        what_to_write = [
            "Title: CVKI dwara generate kiya gaya concise complaint title use kijiye.",
            "Description: Issue severity aur repair request ke saath structured description paste kijiye.",
        ]

    else:  # English default
        if official_portal_url:
            step_1 = f"Open the verified official government portal: {official_portal_url}"
        elif party_name:
            step_1 = f"Access the official citizen grievance portal or division office of {party_name}."
        else:
            step_1 = "Identify and contact the authorized local municipal or road division office."

        steps = [
            step_1,
            f"Select the relevant civic grievance category for {issue_label}.",
            f"Enter the verified location details ({location_summary}).",
            "Attach the clear photograph of the civic defect captured at the site.",
            "Paste or edit the CVKI-generated complaint draft into the description field.",
            "Review all details and submit the complaint directly through the official government portal.",
            "Save the official government complaint registration / token number for tracking.",
        ]

        what_to_attach = [
            "Clear photograph showing the civic defect (manhole, damaged sign, or waterlogging).",
            "Exact street location or GPS coordinates.",
        ]
        what_to_write = [
            "Title: Use the concise complaint title generated by CVKI.",
            "Description: Paste the structured description with issue severity and request for repair.",
        ]

    return GovernmentGuidanceResponse(
        recommended_channel=recommended_channel,
        authority_basis=authority_basis,
        official_portal_url=official_portal_url,
        official_source=official_source_name or (party_name if auth_status != "not_verified" else None),
        steps=steps,
        what_to_attach=what_to_attach,
        what_to_write=what_to_write,
        external_submission_status="not_submitted",
        limitations=limitations,
        language=language,
    )
