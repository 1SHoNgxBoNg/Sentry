from __future__ import annotations

import html
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

import sentry_sdk
from django.db.models import Q
from django.http.request import HttpRequest, QueryDict

from sentry import features
from sentry.api.serializers import serialize
from sentry.incidents.charts import build_metric_alert_chart
from sentry.incidents.endpoints.serializers.alert_rule import AlertRuleSerializer
from sentry.incidents.endpoints.serializers.incident import (
    DetailedIncidentSerializer,
    DetailedIncidentSerializerResponse,
)
from sentry.incidents.models.alert_rule import AlertRule
from sentry.incidents.models.incident import Incident
from sentry.incidents.typings.metric_detector import AlertContext, OpenPeriodContext
from sentry.integrations.messaging.metrics import (
    MessagingInteractionEvent,
    MessagingInteractionType,
)
from sentry.integrations.models.integration import Integration
from sentry.integrations.services.integration import integration_service
from sentry.integrations.slack.message_builder.metric_alerts import SlackMetricAlertMessageBuilder
from sentry.integrations.slack.spec import SlackMessagingSpec
from sentry.integrations.slack.unfurl.types import (
    Handler,
    UnfurlableUrl,
    UnfurledUrl,
    make_type_coercer,
)
from sentry.models.organization import Organization
from sentry.users.models.user import User

map_incident_args = make_type_coercer(
    {
        "org_slug": str,
        "alert_rule_id": int,
        "incident_id": int,
        "period": str,
        "start": str,
        "end": str,
    }
)


def unfurl_metric_alerts(
    request: HttpRequest,
    integration: Integration,
    links: list[UnfurlableUrl],
    user: User | None = None,
) -> UnfurledUrl:
    event = MessagingInteractionEvent(
        MessagingInteractionType.UNFURL_METRIC_ALERTS, SlackMessagingSpec(), user=user
    )
    with event.capture():
        return _unfurl_metric_alerts(integration, links, user)


def _unfurl_metric_alerts(
    integration: Integration,
    links: list[UnfurlableUrl],
    user: User | None = None,
) -> UnfurledUrl:
    alert_filter_query = Q()
    incident_filter_query = Q()
    # Since we don't have real ids here, we use the org slug so that we can
    # make sure the identifiers correspond to the correct organization.
    for link in links:
        org_slug = link.args["org_slug"]
        alert_rule_id = link.args["alert_rule_id"]
        incident_id = link.args["incident_id"]

        if incident_id:
            incident_filter_query |= Q(
                identifier=incident_id, organization__slug=org_slug, alert_rule__id=alert_rule_id
            )
        else:
            alert_filter_query |= Q(id=alert_rule_id, organization__slug=org_slug)

    org_integrations = integration_service.get_organization_integrations(
        integration_id=integration.id
    )
    organizations = Organization.objects.filter(
        id__in=[oi.organization_id for oi in org_integrations]
    )
    alert_rule_map = {
        rule.id: rule
        for rule in AlertRule.objects.filter(
            alert_filter_query,
            # Filter by integration organization here as well to make sure that
            # we have permission to access these incidents.
            organization_id__in=[org.id for org in organizations],
        )
    }

    if not alert_rule_map:
        return {}

    incident_map = {}
    if bool(incident_filter_query):
        incident_map = {
            i.identifier: i
            for i in Incident.objects.filter(
                incident_filter_query,
                # Filter by integration organization here as well to make sure that
                # we have permission to access these incidents.
                organization_id__in=organizations,
            )
        }

    orgs_by_slug: dict[str, Organization] = {org.slug: org for org in organizations}

    result = {}
    for link in links:
        if link.args["alert_rule_id"] not in alert_rule_map:
            continue
        org = orgs_by_slug.get(link.args["org_slug"])
        if org is None:
            continue

        alert_rule = alert_rule_map[link.args["alert_rule_id"]]
        selected_incident = incident_map.get(link.args["incident_id"])

        chart_url = None
        if features.has("organizations:metric-alert-chartcuterie", org):
            try:
                alert_rule_serialized_response = serialize(alert_rule, user, AlertRuleSerializer())
                incident_serialized_response: DetailedIncidentSerializerResponse = serialize(
                    selected_incident, None, DetailedIncidentSerializer()
                )
                chart_url = build_metric_alert_chart(
                    organization=org,
                    alert_rule_serialized_response=alert_rule_serialized_response,
                    snuba_query=alert_rule.snuba_query,
                    alert_context=AlertContext.from_alert_rule_incident(alert_rule),
                    open_period_context=(
                        OpenPeriodContext.from_incident(selected_incident)
                        if selected_incident
                        else None
                    ),
                    selected_incident_serialized=incident_serialized_response,
                    period=link.args["period"],
                    start=link.args["start"],
                    end=link.args["end"],
                    user=user,
                    subscription=selected_incident.subscription if selected_incident else None,
                )
            except Exception as e:
                sentry_sdk.capture_exception(e)

        result[link.url] = SlackMetricAlertMessageBuilder(
            alert_rule=alert_rule,
            incident=selected_incident,
            chart_url=chart_url,
        ).build()

    return result


def map_metric_alert_query_args(url: str, args: Mapping[str, str | None]) -> Mapping[str, Any]:
    """Extracts selected incident id and some query parameters"""

    # Slack uses HTML escaped ampersands in its Event Links, when need
    # to be unescaped for QueryDict to split properly.
    url = html.unescape(url)
    parsed_url = urlparse(url)
    params = QueryDict(parsed_url.query)
    incident_id = params.get("alert", None)
    period = params.get("period", None)
    start = params.get("start", None)
    end = params.get("end", None)

    data = {**args, "incident_id": incident_id, "period": period, "start": start, "end": end}
    return map_incident_args(url, data)


metric_alerts_link_regex = re.compile(
    r"^https?\://(?#url_prefix)[^/]+/organizations/(?P<org_slug>[^/]+)/alerts/rules/details/(?P<alert_rule_id>\d+)"
)

customer_domain_metric_alerts_link_regex = re.compile(
    r"^https?\://(?P<org_slug>[^/]+?)\.(?#url_prefix)[^/]+/alerts/rules/details/(?P<alert_rule_id>\d+)"
)

metric_alert_handler = Handler(
    fn=unfurl_metric_alerts,
    matcher=[metric_alerts_link_regex, customer_domain_metric_alerts_link_regex],
    arg_mapper=map_metric_alert_query_args,
)
