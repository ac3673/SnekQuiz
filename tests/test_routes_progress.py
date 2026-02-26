"""Tests for quiz progress & resume in web routes."""

from __future__ import annotations

from snekquiz import database as db

# ---------------------------------------------------------------------------
# Helper to answer a question via POST (returns the HTMX feedback response)
# ---------------------------------------------------------------------------


async def _answer_question(client, quiz_id, question_id, answers):
    """Submit an answer and return the response."""
    return await client.post(
        f"/quiz/{quiz_id}/answer/{question_id}",
        data={"answers": answers},
    )


# ---------------------------------------------------------------------------
# quiz_start - resume behaviour
# ---------------------------------------------------------------------------


async def test_quiz_start_fresh_redirects_to_q1(client, quiz_id):
    """Starting a quiz with no progress redirects to question 1."""
    resp = await client.get(f"/quiz/{quiz_id}", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == f"/quiz/{quiz_id}/q/1"


async def test_quiz_start_resumes_at_first_unanswered(client, quiz_id):
    """Starting a quiz with partial progress skips to the first unanswered question."""
    # Answer question 1 via the DB directly
    await db.save_progress_answer("testuser", quiz_id, 1, ["B"])

    resp = await client.get(f"/quiz/{quiz_id}", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == f"/quiz/{quiz_id}/q/2"


async def test_quiz_start_resumes_skips_answered(client, quiz_id):
    """If questions 1 and 2 are answered, resume goes to question 3."""
    await db.save_progress_answer("testuser", quiz_id, 1, ["B"])
    await db.save_progress_answer("testuser", quiz_id, 2, ["A", "C"])

    resp = await client.get(f"/quiz/{quiz_id}", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == f"/quiz/{quiz_id}/q/3"


async def test_quiz_start_all_answered_goes_to_finish(client, quiz_id):
    """If all questions are answered, resume goes to the finish page."""
    await db.save_progress_answer("testuser", quiz_id, 1, ["B"])
    await db.save_progress_answer("testuser", quiz_id, 2, ["A", "C"])
    await db.save_progress_answer("testuser", quiz_id, 3, ["B"])

    resp = await client.get(f"/quiz/{quiz_id}", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == f"/quiz/{quiz_id}/finish"


# ---------------------------------------------------------------------------
# quiz_question - skip-forward on already-answered questions
# ---------------------------------------------------------------------------


async def test_question_page_renders_for_unanswered(client, quiz_id):
    """An unanswered question renders the question page normally."""
    resp = await client.get(f"/quiz/{quiz_id}/q/1")
    assert resp.status_code == 200
    assert "What is 1+1?" in resp.text


async def test_question_page_skips_answered(client, quiz_id):
    """Navigating to an already-answered question skips forward."""
    await db.save_progress_answer("testuser", quiz_id, 1, ["B"])

    resp = await client.get(f"/quiz/{quiz_id}/q/1", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == f"/quiz/{quiz_id}/q/2"


async def test_question_page_skips_to_finish_when_all_done(client, quiz_id):
    """If all questions answered, navigating to any redirects to finish."""
    await db.save_progress_answer("testuser", quiz_id, 1, ["B"])
    await db.save_progress_answer("testuser", quiz_id, 2, ["A", "C"])
    await db.save_progress_answer("testuser", quiz_id, 3, ["B"])

    resp = await client.get(f"/quiz/{quiz_id}/q/1", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == f"/quiz/{quiz_id}/finish"


# ---------------------------------------------------------------------------
# submit_answer - answers are persisted to DB immediately
# ---------------------------------------------------------------------------


async def test_submit_answer_persists_to_db(client, quiz_id):
    """Submitting an answer saves it to the quiz_progress table."""
    resp = await _answer_question(client, quiz_id, 1, ["B"])
    assert resp.status_code == 200

    progress = await db.get_progress("testuser", quiz_id)
    assert 1 in progress
    assert progress[1] == ["B"]


async def test_submit_answer_correct_feedback(client, quiz_id):
    """Submitting a correct answer returns positive feedback."""
    resp = await _answer_question(client, quiz_id, 1, ["B"])
    assert resp.status_code == 200
    # The feedback partial should indicate correct
    assert "Correct" in resp.text or "correct" in resp.text


async def test_submit_answer_incorrect_feedback(client, quiz_id):
    """Submitting an incorrect answer returns negative feedback."""
    resp = await _answer_question(client, quiz_id, 1, ["A"])
    assert resp.status_code == 200
    assert "Incorrect" in resp.text or "incorrect" in resp.text


async def test_submit_answer_includes_next_url(client, quiz_id):
    """Feedback for a non-last question includes a link to the next question."""
    resp = await _answer_question(client, quiz_id, 1, ["B"])
    assert resp.status_code == 200
    assert f"/quiz/{quiz_id}/q/2" in resp.text


async def test_submit_answer_last_question_has_complete_form(client, quiz_id):
    """Feedback for the last question includes a form to complete the quiz."""
    resp = await _answer_question(client, quiz_id, 3, ["B"])
    assert resp.status_code == 200
    assert f"/quiz/{quiz_id}/complete" in resp.text


async def test_submit_multiple_answers_accumulate(client, quiz_id):
    """Answering multiple questions accumulates progress in the DB."""
    await _answer_question(client, quiz_id, 1, ["B"])
    await _answer_question(client, quiz_id, 2, ["A", "C"])

    progress = await db.get_progress("testuser", quiz_id)
    assert progress == {1: ["B"], 2: ["A", "C"]}


# ---------------------------------------------------------------------------
# quiz_complete - finalization clears progress
# ---------------------------------------------------------------------------


async def test_complete_creates_attempt_and_clears_progress(client, quiz_id):
    """Completing a quiz persists the attempt and clears progress."""
    # Answer all three questions
    await db.save_progress_answer("testuser", quiz_id, 1, ["B"])
    await db.save_progress_answer("testuser", quiz_id, 2, ["A", "C"])
    await db.save_progress_answer("testuser", quiz_id, 3, ["B"])

    resp = await client.post(f"/quiz/{quiz_id}/complete", follow_redirects=False)
    assert resp.status_code == 303
    assert "/quiz/" in resp.headers["location"]
    assert "/results/" in resp.headers["location"]

    # Progress should be cleared
    progress = await db.get_progress("testuser", quiz_id)
    assert progress == {}


async def test_complete_scores_correctly(client, quiz_id):
    """Completing a quiz computes the correct score from progress."""
    # 2 out of 3 correct
    await db.save_progress_answer("testuser", quiz_id, 1, ["B"])  # correct
    await db.save_progress_answer("testuser", quiz_id, 2, ["A"])  # wrong (missing C)
    await db.save_progress_answer("testuser", quiz_id, 3, ["B"])  # correct

    resp = await client.post(f"/quiz/{quiz_id}/complete", follow_redirects=False)
    assert resp.status_code == 303

    # Extract attempt_id from redirect URL
    location = resp.headers["location"]
    attempt_id = int(location.rsplit("/", 1)[-1])

    attempt = await db.get_attempt_by_id(attempt_id)
    assert attempt["score"] == 2
    assert attempt["total"] == 3


async def test_complete_perfect_score(client, quiz_id):
    """All correct answers produce a perfect score."""
    await db.save_progress_answer("testuser", quiz_id, 1, ["B"])
    await db.save_progress_answer("testuser", quiz_id, 2, ["A", "C"])
    await db.save_progress_answer("testuser", quiz_id, 3, ["B"])

    resp = await client.post(f"/quiz/{quiz_id}/complete", follow_redirects=False)
    location = resp.headers["location"]
    attempt_id = int(location.rsplit("/", 1)[-1])

    attempt = await db.get_attempt_by_id(attempt_id)
    assert attempt["score"] == 3
    assert attempt["total"] == 3


# ---------------------------------------------------------------------------
# Home page - badge states
# ---------------------------------------------------------------------------


async def test_home_shows_new_badge(client, quiz_id):
    """A quiz with no progress and no attempts shows 'New'."""
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "New" in resp.text


async def test_home_shows_in_progress_badge(client, quiz_id):
    """A quiz with saved progress shows 'In Progress'."""
    await db.save_progress_answer("testuser", quiz_id, 1, ["B"])

    resp = await client.get("/")
    assert resp.status_code == 200
    assert "In Progress" in resp.text


async def test_home_shows_completed_badge(client, quiz_id):
    """A quiz with a completed attempt shows 'Completed'."""
    await db.save_attempt(
        username="testuser",
        quiz_id=quiz_id,
        score=3,
        total=3,
        answers={"1": ["B"], "2": ["A", "C"], "3": ["B"]},
    )

    resp = await client.get("/")
    assert resp.status_code == 200
    assert "Completed" in resp.text


async def test_home_completed_takes_precedence_over_progress(client, quiz_id):
    """If a quiz is both completed and has leftover progress, show 'Completed'."""
    await db.save_progress_answer("testuser", quiz_id, 1, ["B"])
    await db.save_attempt(
        username="testuser",
        quiz_id=quiz_id,
        score=1,
        total=3,
        answers={"1": ["B"]},
    )

    resp = await client.get("/")
    assert resp.status_code == 200
    assert "Completed" in resp.text
    # Should NOT show In Progress
    assert "In Progress" not in resp.text


# ---------------------------------------------------------------------------
# Full end-to-end flow
# ---------------------------------------------------------------------------


async def test_full_quiz_flow_with_resume(client, quiz_id):
    """Simulate starting a quiz, leaving, resuming, and completing it."""
    # Start: redirects to Q1
    resp = await client.get(f"/quiz/{quiz_id}", follow_redirects=False)
    assert resp.headers["location"] == f"/quiz/{quiz_id}/q/1"

    # Answer Q1
    await _answer_question(client, quiz_id, 1, ["B"])

    # "Leave" and come back - should resume at Q2
    resp = await client.get(f"/quiz/{quiz_id}", follow_redirects=False)
    assert resp.headers["location"] == f"/quiz/{quiz_id}/q/2"

    # Answer Q2
    await _answer_question(client, quiz_id, 2, ["A", "C"])

    # Resume - should go to Q3
    resp = await client.get(f"/quiz/{quiz_id}", follow_redirects=False)
    assert resp.headers["location"] == f"/quiz/{quiz_id}/q/3"

    # Answer Q3
    await _answer_question(client, quiz_id, 3, ["B"])

    # Resume - all answered, go to finish
    resp = await client.get(f"/quiz/{quiz_id}", follow_redirects=False)
    assert resp.headers["location"] == f"/quiz/{quiz_id}/finish"

    # Complete
    resp = await client.post(f"/quiz/{quiz_id}/complete", follow_redirects=False)
    assert resp.status_code == 303

    # Progress is cleared
    progress = await db.get_progress("testuser", quiz_id)
    assert progress == {}

    # Attempt is saved with perfect score
    location = resp.headers["location"]
    attempt_id = int(location.rsplit("/", 1)[-1])
    attempt = await db.get_attempt_by_id(attempt_id)
    assert attempt["score"] == 3

    # Results page is accessible
    resp = await client.get(location)
    assert resp.status_code == 200


async def test_progress_isolated_between_users(client, admin_client, quiz_id):
    """Two users' progress on the same quiz doesn't interfere."""
    # testuser answers Q1
    await _answer_question(client, quiz_id, 1, ["B"])

    # admin answers Q1 differently
    await _answer_question(admin_client, quiz_id, 1, ["A"])

    # Each user sees their own progress
    assert await db.get_progress("testuser", quiz_id) == {1: ["B"]}
    assert await db.get_progress("admin", quiz_id) == {1: ["A"]}

    # testuser resumes at Q2
    resp = await client.get(f"/quiz/{quiz_id}", follow_redirects=False)
    assert resp.headers["location"] == f"/quiz/{quiz_id}/q/2"

    # admin also resumes at Q2
    resp = await admin_client.get(f"/quiz/{quiz_id}", follow_redirects=False)
    assert resp.headers["location"] == f"/quiz/{quiz_id}/q/2"
