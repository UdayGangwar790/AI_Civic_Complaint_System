from dataclasses import dataclass

from app.schemas.complaint import (
    ComplaintDraftRequest,
    ComplaintDraftResponse,
    ComplaintLocation,
)


class UnsupportedIssueError(ValueError):
    """The complaint generator received a class outside the M1.13 mapping."""


@dataclass(frozen=True)
class IssueDefinition:
    label: str
    severity: str
    severity_reason: str
    request_en: str
    request_hi: str
    request_hinglish: str


ISSUE_DEFINITIONS = {
    "open_damaged_manhole": IssueDefinition(
        label="Open/Damaged Manhole",
        severity="high",
        severity_reason="An open/damaged manhole can create a road safety hazard.",
        request_en="Please inspect the reported location and take appropriate corrective action.",
        request_hi="कृपया स्थान का निरीक्षण करके उचित सुधारात्मक कार्रवाई करें।",
        request_hinglish="Kripya location inspect karke zaroori corrective action liya jaye.",
    ),
    "damaged_missing_road_sign": IssueDefinition(
        label="Damaged/Missing Road Sign",
        severity="medium",
        severity_reason="A damaged or missing road sign can reduce road-user guidance.",
        request_en="Please inspect the reported location and restore or repair the road sign as appropriate.",
        request_hi="कृपया स्थान का निरीक्षण करके सड़क संकेत की मरम्मत या पुनर्स्थापना करें।",
        request_hinglish="Kripya location inspect karke road sign ki repair ya replacement ki jaye.",
    ),
    "road_waterlogging": IssueDefinition(
        label="Road Waterlogging",
        severity="medium",
        severity_reason="Road waterlogging can affect normal road use and should be inspected.",
        request_en="Please inspect the reported location and take appropriate corrective action.",
        request_hi="कृपया स्थान का निरीक्षण करके उचित सुधारात्मक कार्रवाई करें।",
        request_hinglish="Kripya location inspect karke zaroori corrective action liya jaye.",
    ),
}


def _location_text(location: ComplaintLocation, language: str) -> str:
    parts = [location.road, location.area, location.city, location.district, location.state]
    available = [part for part in parts if part]
    if available:
        if not location.road:
            if language == "hi":
                return f"सड़क की जानकारी उपलब्ध नहीं है; {', '.join(available)}"
            if language == "hinglish":
                return f"Road information available nahi hai; {', '.join(available)}"
            return f"Road information is not available; {', '.join(available)}"
        return ", ".join(available)
    if language == "hi":
        return "स्थान की सड़क जानकारी उपलब्ध नहीं है।"
    if language == "hinglish":
        return "Road information available nahi hai."
    return "Road information is not available."


def _authority_content(request: ComplaintDraftRequest) -> tuple[str, list[str]]:
    authority = request.authority
    if not authority:
        return "not_verified", [
            "Responsible road authority could not be verified from available authoritative data."
        ]
    limitations = list(authority.limitations)
    if authority.authority_status != "verified":
        limitations.append("Authority information is not fully verified; no responsible authority is suggested in this draft.")
    return authority.authority_status, limitations


def generate_complaint(request: ComplaintDraftRequest) -> ComplaintDraftResponse:
    definition = ISSUE_DEFINITIONS.get(request.detection.class_name)
    if definition is None:
        raise UnsupportedIssueError("Unsupported civic issue class.")

    language = request.language
    location = request.location or ComplaintLocation()
    location_text = _location_text(location, language)
    authority_status, limitations = _authority_content(request)
    suggested_authority = None
    if request.authority and request.authority.authority_status == "verified":
        suggested_authority = request.authority.maintenance_authority or request.authority.road_owner

    confidence_percent = round(request.detection.confidence * 100)
    if language == "hi":
        title = f"{definition.label} की शिकायत"
        description = (
            f"विषय: {definition.label}\n\n"
            f"स्थान: {location_text}\n\n"
            f"समस्या: CVKI कंप्यूटर-विज़न मॉडल ने इस छवि में {definition.label} का संकेत पाया "
            f"(विश्वास स्तर {confidence_percent}%)।\n\n"
            f"अनुरोध: {definition.request_hi}"
        )
        evidence = [f"छवि का CVKI कंप्यूटर-विज़न मॉडल द्वारा विश्लेषण किया गया; confidence {confidence_percent}%."]
        if request.image_attached:
            evidence.append("फोटो प्रमाण संलग्न है।")
    elif language == "hinglish":
        title = f"{definition.label} Report"
        description = (
            f"Subject: {definition.label}\n\n"
            f"Location: {location_text}\n\n"
            f"Issue: CVKI computer-vision model ne is image mein {definition.label} detect kiya "
            f"(confidence {confidence_percent}%).\n\n"
            f"Request: {definition.request_hinglish}"
        )
        evidence = [f"Image ko CVKI computer-vision model ne analyze kiya; confidence {confidence_percent}%."]
        if request.image_attached:
            evidence.append("Photo evidence attached hai.")
    else:
        title = f"{definition.label} Report"
        description = (
            f"Subject: {definition.label}\n\n"
            f"Location: {location_text}\n\n"
            f"Issue: The CVKI computer-vision model detected an instance of {definition.label} "
            f"in the uploaded image (confidence {confidence_percent}%).\n\n"
            f"Request: {definition.request_en}"
        )
        evidence = [f"The uploaded image was analyzed by the CVKI computer-vision model; confidence {confidence_percent}%."]
        if request.image_attached:
            evidence.append("Photo evidence is attached.")

    if request.authority:
        evidence.extend(
            f"Authority evidence: {item.source_name} - {item.claim}"
            for item in request.authority.evidence
        )

    if authority_status != "verified":
        if language == "hi":
            authority_note = "जिम्मेदार सड़क प्राधिकरण उपलब्ध प्रमाणित जानकारी से सत्यापित नहीं हो सका।"
        elif language == "hinglish":
            authority_note = "Responsible road authority available authoritative data se verify nahi ho saka."
        else:
            authority_note = "Responsible road authority could not be verified from available authoritative data."
        description = f"{description}\n\nAuthority: {authority_note}"

    # Generate M3.5 Government Complaint Guidance
    from app.schemas.guidance import GovernmentGuidanceRequest
    from app.services.guidance import generate_government_guidance

    guidance = generate_government_guidance(
        GovernmentGuidanceRequest(
            issue_category=request.detection.class_name,
            location=location,
            authority=request.authority,
            language=language,
            complaint_title=title,
            complaint_description=description,
        )
    )

    return ComplaintDraftResponse(
        issue_category=request.detection.class_name,
        issue_label=definition.label,
        title=title,
        description=description,
        language=language,
        severity=definition.severity,
        severity_reason=definition.severity_reason,
        location=location,
        authority_status=authority_status,
        suggested_authority=suggested_authority,
        evidence=evidence,
        limitations=limitations,
        draft_text=f"{title}\n\n{description}",
        guidance=guidance,
    )
