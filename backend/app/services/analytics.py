import csv
import io
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from pymongo.errors import PyMongoError

from app.core.config import settings
from app.core.database import COMPLAINT_CASES_COLLECTION, mongo_manager
from app.models.roles import UserRole
from app.schemas.analytics import (
    AnalyticsSummary,
    ConcentrationItem,
    DistributionItem,
    OperationalAnalyticsResponse,
    ResolutionMetrics,
    TimeSeriesItem,
)
from app.schemas.civic_intelligence import HotspotItem
from app.services.complaint_case import ComplaintCaseDatabaseError

logger = logging.getLogger("cvki.analytics")

_DEFAULT_DB = object()


def _get_collection(name: str = COMPLAINT_CASES_COLLECTION, db: object = None):
    if db is not None and hasattr(db, "__getitem__"):
        return db[name]
    database = mongo_manager.db
    if database is None:
        raise ComplaintCaseDatabaseError("MongoDB persistence is unavailable.")
    return database[name]


def _build_match_query(
    issue: Optional[str] = None,
    priority: Optional[str] = None,
    status: Optional[str] = None,
    city: Optional[str] = None,
    authority: Optional[str] = None,
    created_from: Optional[str] = None,
    created_to: Optional[str] = None,
) -> dict:
    query: dict = {}

    if issue and issue.strip():
        query["issue.class_name"] = issue.strip().lower()

    if priority and priority.strip():
        query["priority_analysis.priority_level"] = priority.strip().upper()

    if status and status.strip():
        query["status"] = status.strip().lower()

    if city and city.strip():
        query["location.city"] = {"$regex": f"^{re.escape(city.strip())}", "$options": "i"}

    if authority and authority.strip():
        query["$or"] = [
            {"authority.name": {"$regex": re.escape(authority.strip()), "$options": "i"}},
            {"authority.authority_status": authority.strip().lower()},
        ]

    date_filter: dict = {}
    if created_from and created_from.strip():
        try:
            norm_from = created_from.strip().replace(" ", "+").replace("Z", "+00:00")
            date_filter["$gte"] = datetime.fromisoformat(norm_from)
        except ValueError:
            pass
    if created_to and created_to.strip():
        try:
            norm_to = created_to.strip().replace(" ", "+").replace("Z", "+00:00")
            date_filter["$lte"] = datetime.fromisoformat(norm_to)
        except ValueError:
            pass
    if date_filter:
        query["created_at"] = date_filter

    return query


async def get_operational_analytics(
    issue: Optional[str] = None,
    priority: Optional[str] = None,
    status: Optional[str] = None,
    city: Optional[str] = None,
    authority: Optional[str] = None,
    created_from: Optional[str] = None,
    created_to: Optional[str] = None,
    group_by: str = "daily",
    db: object = _DEFAULT_DB,
) -> OperationalAnalyticsResponse:
    """
    Computes real operational analytics across CVKI complaint cases using native MongoDB aggregation.
    """
    cases_col = _get_collection(COMPLAINT_CASES_COLLECTION, db)
    match_query = _build_match_query(
        issue=issue,
        priority=priority,
        status=status,
        city=city,
        authority=authority,
        created_from=created_from,
        created_to=created_to,
    )

    try:
        total_cases = await cases_col.count_documents(match_query)

        # 1. Summary aggregations (avg score, open, resolved, assigned)
        open_query = dict(match_query)
        open_query["status"] = {"$nin": ["resolved", "closed"]}
        open_cases = await cases_col.count_documents(open_query)

        resolved_query = dict(match_query)
        resolved_query["status"] = "resolved"
        resolved_cases = await cases_col.count_documents(resolved_query)

        closed_query = dict(match_query)
        closed_query["status"] = "closed"
        closed_cases = await cases_col.count_documents(closed_query)

        assigned_query = dict(match_query)
        assigned_query["assignment.assignment_status"] = "assigned"
        assigned_query["assignment.assigned_to_user_id"] = {"$ne": None}
        assigned_cases = await cases_col.count_documents(assigned_query)

        unassigned_cases = max(0, total_cases - assigned_cases)

        # Average priority score
        avg_cursor = cases_col.aggregate([
            {"$match": match_query},
            {"$match": {"priority_analysis.priority_score": {"$exists": True, "$ne": None}}},
            {"$group": {"_id": None, "avg_score": {"$avg": "$priority_analysis.priority_score"}}},
        ])
        avg_res = await avg_cursor.to_list(length=1)
        avg_priority_score = round(float(avg_res[0]["avg_score"]), 1) if avg_res and avg_res[0].get("avg_score") else 0.0

        # 2. Issue distribution pipeline
        issue_cursor = cases_col.aggregate([
            {"$match": match_query},
            {"$group": {"_id": "$issue.class_name", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ])
        raw_issues = await issue_cursor.to_list(length=20)
        issue_distribution: list[DistributionItem] = []
        for r in raw_issues:
            key = r["_id"] or "other_civic_issue"
            cnt = int(r["count"])
            pct = round((cnt / total_cases * 100), 1) if total_cases > 0 else 0.0
            label = str(key).replace("_", " ").title()
            issue_distribution.append(DistributionItem(key=key, label=label, count=cnt, percentage=pct))

        # 3. Priority distribution pipeline
        prio_cursor = cases_col.aggregate([
            {"$match": match_query},
            {"$group": {"_id": "$priority_analysis.priority_level", "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}},
        ])
        raw_prio = await prio_cursor.to_list(length=10)
        prio_dict = {r["_id"]: int(r["count"]) for r in raw_prio if r.get("_id")}
        priority_distribution: list[DistributionItem] = []
        for p in ["P1", "P2", "P3", "P4"]:
            cnt = prio_dict.get(p, 0)
            pct = round((cnt / total_cases * 100), 1) if total_cases > 0 else 0.0
            priority_distribution.append(DistributionItem(key=p, label=f"Priority {p}", count=cnt, percentage=pct))

        # 4. Status distribution pipeline
        status_cursor = cases_col.aggregate([
            {"$match": match_query},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ])
        raw_statuses = await status_cursor.to_list(length=10)
        status_distribution: list[DistributionItem] = []
        for r in raw_statuses:
            key = r["_id"] or "submitted_to_cvki"
            cnt = int(r["count"])
            pct = round((cnt / total_cases * 100), 1) if total_cases > 0 else 0.0
            label = str(key).replace("_", " ").title()
            status_distribution.append(DistributionItem(key=key, label=label, count=cnt, percentage=pct))

        # 5. Duplicate distribution pipeline
        dup_cursor = cases_col.aggregate([
            {"$match": match_query},
            {"$group": {"_id": "$duplicate_analysis.classification", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ])
        raw_dup = await dup_cursor.to_list(length=10)
        duplicate_distribution: list[DistributionItem] = []
        for r in raw_dup:
            key = r["_id"] or "unique"
            cnt = int(r["count"])
            pct = round((cnt / total_cases * 100), 1) if total_cases > 0 else 0.0
            duplicate_distribution.append(DistributionItem(key=key, label=str(key).replace("_", " ").title(), count=cnt, percentage=pct))

        # 6. City distribution pipeline
        city_cursor = cases_col.aggregate([
            {"$match": match_query},
            {"$match": {"location.city": {"$exists": True, "$ne": None}}},
            {"$group": {"_id": "$location.city", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10},
        ])
        raw_cities = await city_cursor.to_list(length=10)
        city_distribution: list[DistributionItem] = []
        for r in raw_cities:
            city_name = str(r["_id"])
            cnt = int(r["count"])
            pct = round((cnt / total_cases * 100), 1) if total_cases > 0 else 0.0
            city_distribution.append(DistributionItem(key=city_name, label=city_name, count=cnt, percentage=pct))

        # 7. Authority status distribution
        auth_cursor = cases_col.aggregate([
            {"$match": match_query},
            {"$group": {"_id": "$authority.authority_status", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ])
        raw_auth = await auth_cursor.to_list(length=5)
        authority_distribution: list[DistributionItem] = []
        for r in raw_auth:
            key = r["_id"] or "unverified"
            cnt = int(r["count"])
            pct = round((cnt / total_cases * 100), 1) if total_cases > 0 else 0.0
            authority_distribution.append(DistributionItem(key=key, label=str(key).replace("_", " ").title(), count=cnt, percentage=pct))

        # 8. Geographic concentration (Road & City hotspots)
        hotspot_cursor = cases_col.aggregate([
            {"$match": match_query},
            {"$match": {"location.road": {"$exists": True, "$ne": None}}},
            {"$group": {"_id": {"road": "$location.road", "city": "$location.city"}, "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10},
        ])
        raw_hotspots = await hotspot_cursor.to_list(length=10)
        geographic_concentration: list[ConcentrationItem] = []
        for r in raw_hotspots:
            info = r["_id"] or {}
            geographic_concentration.append(
                ConcentrationItem(
                    road=info.get("road") or "Unknown Road",
                    city=info.get("city") or "Unknown City",
                    count=int(r["count"]),
                )
            )

        # 9. Recent, explainable road/city hotspots. Legacy all-time concentrations
        # above are preserved for existing clients.
        hotspot_window_days = settings.HOTSPOT_WINDOW_DAYS
        hotspot_cutoff = datetime.now(timezone.utc) - timedelta(days=hotspot_window_days)
        hotspot_query = {"$and": [match_query, {"created_at": {"$gte": hotspot_cutoff}}]}
        hotspot_cursor = cases_col.aggregate([
            {"$match": hotspot_query},
            {"$match": {"location.road": {"$type": "string", "$ne": ""}}},
            {"$addFields": {
                "_hotspot_road": {"$toLower": {"$trim": {"input": "$location.road"}}},
                "_hotspot_city": {"$toLower": {"$trim": {"input": {"$ifNull": ["$location.city", ""]}}}},
                "_hotspot_issue": {"$ifNull": ["$issue.class_name", "other_civic_issue"]},
                "_hotspot_unresolved": {"$cond": [{"$in": ["$status", ["resolved", "closed"]]}, 0, 1]},
            }},
            {"$group": {
                "_id": {"road": "$_hotspot_road", "city": "$_hotspot_city", "issue": "$_hotspot_issue"},
                "count": {"$sum": 1},
                "unresolved_count": {"$sum": "$_hotspot_unresolved"},
                "road_label": {"$first": "$location.road"},
                "city_label": {"$first": "$location.city"},
            }},
            {"$sort": {"count": -1, "_id.issue": 1}},
            {"$group": {
                "_id": {"road": "$_id.road", "city": "$_id.city"},
                "count": {"$sum": "$count"},
                "unresolved_count": {"$sum": "$unresolved_count"},
                "issues": {"$push": {"category": "$_id.issue", "count": "$count"}},
                "road": {"$first": "$road_label"},
                "city": {"$first": "$city_label"},
            }},
            {"$match": {"count": {"$gte": settings.HOTSPOT_MIN_CASES}}},
            {"$sort": {"count": -1, "_id.road": 1, "_id.city": 1}},
            {"$limit": 10},
        ])
        raw_hotspots = await hotspot_cursor.to_list(length=10)
        hotspots: list[HotspotItem] = []
        for item in raw_hotspots:
            categories = item.get("issues") or []
            dominant_issue = categories[0].get("category") if categories else "other_civic_issue"
            count = int(item.get("count", 0))
            unresolved_count = int(item.get("unresolved_count", 0))
            road = item.get("road") or "Unnamed road"
            city = item.get("city") or None
            hotspots.append(HotspotItem(
                road=road,
                city=city,
                count=count,
                dominant_issue_category=dominant_issue,
                unresolved_count=unresolved_count,
                time_window_days=hotspot_window_days,
                explanation=(
                    f"{count} reports were recorded for this road/city in the previous {hotspot_window_days} days; "
                    f"{unresolved_count} remain open. The most frequent category is {dominant_issue.replace('_', ' ')}. "
                    "This is a reporting concentration, not proof of a shared cause."
                ),
            ))

        # 10. Time series aggregation
        date_format = "%Y-%m-%d"
        if group_by == "weekly":
            date_format = "%Y-W%V"
        elif group_by == "monthly":
            date_format = "%Y-%m"

        time_cursor = cases_col.aggregate([
            {"$match": match_query},
            {"$match": {"created_at": {"$exists": True, "$ne": None}}},
            {"$group": {"_id": {"$dateToString": {"format": date_format, "date": "$created_at"}}, "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}},
            {"$limit": 50},
        ])
        raw_times = await time_cursor.to_list(length=50)
        time_series: list[TimeSeriesItem] = []
        for r in raw_times:
            if r.get("_id"):
                time_series.append(TimeSeriesItem(date=str(r["_id"]), count=int(r["count"])))

        # 11. Resolution metrics
        resolved_total = resolved_cases + closed_cases
        resolution_rate = round((resolved_total / total_cases * 100), 1) if total_cases > 0 else 0.0
        resolution_metrics = ResolutionMetrics(
            resolved_count=resolved_cases,
            closed_count=closed_cases,
            open_count=open_cases,
            resolution_rate_pct=resolution_rate,
        )

        return OperationalAnalyticsResponse(
            summary=AnalyticsSummary(
                total_cases=total_cases,
                open_cases=open_cases,
                resolved_cases=resolved_cases,
                assigned_cases=assigned_cases,
                unassigned_cases=unassigned_cases,
                average_priority_score=avg_priority_score,
            ),
            issue_distribution=issue_distribution,
            priority_distribution=priority_distribution,
            status_distribution=status_distribution,
            time_series=time_series,
            city_distribution=city_distribution,
            duplicate_distribution=duplicate_distribution,
            authority_distribution=authority_distribution,
            geographic_concentration=geographic_concentration,
            hotspots=hotspots,
            resolution_metrics=resolution_metrics,
        )

    except PyMongoError as exc:
        logger.error("Operational analytics query failed (error_type=%s).", type(exc).__name__)
        raise ComplaintCaseDatabaseError("Database service is unavailable.") from exc


def generate_analytics_csv(analytics: OperationalAnalyticsResponse) -> str:
    """
    Exports clean, non-sensitive aggregated operational analytics to CSV.
    Never includes passwords, credentials, or personal citizen identities.
    """
    output = io.StringIO(newline="")
    writer = csv.writer(output)

    def safe_cell(value: str) -> str:
        if value.lstrip().startswith(("=", "+", "-", "@")):
            return "'" + value
        return value

    writer.writerow(["=== CVKI OPERATIONAL ANALYTICS SUMMARY ==="])
    writer.writerow(["Metric", "Value"])
    writer.writerow(["Total Cases", analytics.summary.total_cases])
    writer.writerow(["Open Cases", analytics.summary.open_cases])
    writer.writerow(["Resolved Cases", analytics.summary.resolved_cases])
    writer.writerow(["Assigned Cases", analytics.summary.assigned_cases])
    writer.writerow(["Unassigned Cases", analytics.summary.unassigned_cases])
    writer.writerow(["Average Priority Score", analytics.summary.average_priority_score])
    writer.writerow(["Resolution Rate (%)", analytics.resolution_metrics.resolution_rate_pct])
    writer.writerow([])

    writer.writerow(["=== ISSUE DISTRIBUTION ==="])
    writer.writerow(["Issue Key", "Label", "Count", "Percentage"])
    for item in analytics.issue_distribution:
        writer.writerow([safe_cell(item.key), safe_cell(item.label), item.count, f"{item.percentage}%"])
    writer.writerow([])

    writer.writerow(["=== PRIORITY DISTRIBUTION ==="])
    writer.writerow(["Priority", "Count", "Percentage"])
    for item in analytics.priority_distribution:
        writer.writerow([safe_cell(item.key), item.count, f"{item.percentage}%"])
    writer.writerow([])

    writer.writerow(["=== GEOGRAPHIC CONCENTRATION (TOP ROADS) ==="])
    writer.writerow(["Road", "City", "Reported Count"])
    for item in analytics.geographic_concentration:
        writer.writerow([safe_cell(item.road), safe_cell(item.city), item.count])
    writer.writerow([])

    writer.writerow(["=== TIME TREND ==="])
    writer.writerow(["Period", "Cases Reported"])
    for item in analytics.time_series:
        writer.writerow([safe_cell(item.date), item.count])

    return output.getvalue()
