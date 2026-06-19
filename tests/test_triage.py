"""Triage classification in mock mode."""

from __future__ import annotations

from router.models import Category, Priority
from router.triage import triage_message

from .helpers import make_message


def test_outage_is_urgent(config):
    msg = make_message(
        subject="URGENT: Production is down — 503 errors everywhere",
        body="Our entire Acme Cloud deployment is returning 503s.",
    )
    triage = triage_message(msg, config)
    assert triage.category is Category.OUTAGE
    assert triage.priority is Priority.URGENT
    assert triage.source == "mock"


def test_billing_double_charge_is_high(config):
    msg = make_message(
        subject="Double charged on my invoice",
        body="I was billed twice for my subscription. Please refund the duplicate.",
    )
    triage = triage_message(msg, config)
    assert triage.category is Category.BILLING
    assert triage.priority is Priority.HIGH


def test_feature_request_is_low(config):
    msg = make_message(
        subject="Feature idea: dark mode",
        body="Would love a dark mode option. Not urgent, just a nice-to-have.",
    )
    triage = triage_message(msg, config)
    assert triage.category is Category.FEATURE_REQUEST
    assert triage.priority is Priority.LOW


def test_how_to_is_normal(config):
    msg = make_message(
        subject="How do I reset my API key?",
        body="Where do I regenerate my key? Can you point me to the settings page?",
    )
    triage = triage_message(msg, config)
    assert triage.category is Category.HOW_TO
    assert triage.priority is Priority.NORMAL


def test_extracts_customer_name(config):
    msg = make_message(sender_name="Jordan Lee")
    triage = triage_message(msg, config)
    assert triage.customer == "Jordan Lee"
