from src.agent import select_outbound_channel
from src.schemas import Channel, RiskResult


def make_state(
    *,
    email_allowed=True,
    sms_consent=True,
    risk_band="LOW",
    communications=None,
):
    scores = {
        "LOW": 0.20,
        "MEDIUM": 0.45,
        "HIGH": 0.70,
        "CRITICAL": 0.90,
    }

    return {
        "account_evidence": {
            "status": "SUCCESS",
            "data": {
                "account": {
                    "email_allowed": int(email_allowed),
                    "sms_consent": int(sms_consent),
                },
                "recent_communications": communications or [],
            },
        },
        "risk": RiskResult(
            score=scores[risk_band],
            band=risk_band,
            model_version="step27-fixture-v0",
            contributing_factors=[],
        ),
    }


def test_selector_prefers_sms_when_recent_inbound_sms_responsiveness_is_greater():
    state = make_state(
        communications=[
            {"direction": "INBOUND", "channel": "SMS"},
            {"direction": "INBOUND", "channel": "SMS"},
            {"direction": "INBOUND", "channel": "EMAIL"},
        ],
    )

    channel, rationale = select_outbound_channel(state)

    assert channel == Channel.SMS
    assert "greater inbound responsiveness by SMS" in rationale


def test_selector_prefers_email_when_recent_inbound_email_responsiveness_is_greater():
    state = make_state(
        communications=[
            {"direction": "INBOUND", "channel": "EMAIL"},
            {"direction": "INBOUND", "channel": "EMAIL"},
            {"direction": "INBOUND", "channel": "SMS"},
        ],
    )

    channel, rationale = select_outbound_channel(state)

    assert channel == Channel.EMAIL
    assert "greater inbound responsiveness by email" in rationale


def test_selector_prefers_email_for_low_risk_when_responsiveness_is_equal():
    state = make_state()

    channel, rationale = select_outbound_channel(state)

    assert channel == Channel.EMAIL
    assert "prefers email for low-risk accounts" in rationale


def test_selector_prefers_human_followup_for_high_risk():
    state = make_state(
        risk_band="HIGH",
        communications=[
            {"direction": "INBOUND", "channel": "SMS"},
        ],
    )

    channel, rationale = select_outbound_channel(state)

    assert channel == Channel.HUMAN_CALL_FLAG
    assert "HIGH" in rationale


def test_selector_uses_email_when_it_is_only_permitted_channel():
    state = make_state(
        email_allowed=True,
        sms_consent=False,
        risk_band="MEDIUM",
    )

    channel, rationale = select_outbound_channel(state)

    assert channel == Channel.EMAIL
    assert "only permitted autonomous channel" in rationale


def test_selector_uses_sms_when_it_is_only_permitted_channel():
    state = make_state(
        email_allowed=False,
        sms_consent=True,
        risk_band="MEDIUM",
    )

    channel, rationale = select_outbound_channel(state)

    assert channel == Channel.SMS
    assert "only permitted autonomous channel" in rationale


def test_selector_flags_human_when_no_autonomous_channel_is_permitted():
    state = make_state(
        email_allowed=False,
        sms_consent=False,
        risk_band="MEDIUM",
    )

    channel, rationale = select_outbound_channel(state)

    assert channel == Channel.HUMAN_CALL_FLAG
    assert "Neither email nor SMS" in rationale
