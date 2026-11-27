from src.agent import mock_classify_reply
from src.schemas import Intent


def test_readme_promise_sentence_classifies_as_promise():
    result = mock_classify_reply("I'll pay the invoice on Friday.")

    assert result.primary_intent == Intent.PROMISE_TO_PAY


def test_readme_payment_plan_sentence_classifies_as_payment_plan():
    result = mock_classify_reply(
        "I can't pay everything today. Can I make payments?"
    )

    assert result.primary_intent == Intent.PAYMENT_PLAN_REQUEST


def test_readme_already_paid_sentence_classifies_as_already_paid():
    result = mock_classify_reply("I already paid this last week.")

    assert result.primary_intent == Intent.ALREADY_PAID_CLAIM
