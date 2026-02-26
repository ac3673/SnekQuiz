"""Tests for quiz_progress database functions."""

from __future__ import annotations

from snekquiz import database as db


async def test_save_and_get_progress(test_db, quiz_id):
    """Saving a single answer should be retrievable via get_progress."""
    await db.save_progress_answer("alice", quiz_id, 1, ["B"])

    progress = await db.get_progress("alice", quiz_id)
    assert progress == {1: ["B"]}


async def test_save_progress_multiple_questions(test_db, quiz_id):
    """Multiple questions accumulate in progress."""
    await db.save_progress_answer("alice", quiz_id, 1, ["B"])
    await db.save_progress_answer("alice", quiz_id, 2, ["A", "C"])

    progress = await db.get_progress("alice", quiz_id)
    assert progress == {1: ["B"], 2: ["A", "C"]}


async def test_save_progress_upsert(test_db, quiz_id):
    """Answering the same question again overwrites the previous answer."""
    await db.save_progress_answer("alice", quiz_id, 1, ["A"])
    await db.save_progress_answer("alice", quiz_id, 1, ["B"])

    progress = await db.get_progress("alice", quiz_id)
    assert progress == {1: ["B"]}


async def test_get_progress_empty(test_db, quiz_id):
    """No progress saved returns an empty dict."""
    progress = await db.get_progress("alice", quiz_id)
    assert progress == {}


async def test_progress_isolated_per_user(test_db, quiz_id):
    """Progress is scoped to individual users."""
    await db.save_progress_answer("alice", quiz_id, 1, ["B"])
    await db.save_progress_answer("bob", quiz_id, 1, ["A"])

    assert await db.get_progress("alice", quiz_id) == {1: ["B"]}
    assert await db.get_progress("bob", quiz_id) == {1: ["A"]}


async def test_progress_isolated_per_quiz(test_db, quiz_id):
    """Progress is scoped to individual quizzes."""
    quiz_id_2 = await db.insert_quiz("Other Quiz", '{"quiz_name":"Other Quiz","questions":[]}')

    await db.save_progress_answer("alice", quiz_id, 1, ["B"])
    await db.save_progress_answer("alice", quiz_id_2, 1, ["C"])

    assert await db.get_progress("alice", quiz_id) == {1: ["B"]}
    assert await db.get_progress("alice", quiz_id_2) == {1: ["C"]}


async def test_delete_progress(test_db, quiz_id):
    """delete_progress removes all saved answers for a user/quiz pair."""
    await db.save_progress_answer("alice", quiz_id, 1, ["B"])
    await db.save_progress_answer("alice", quiz_id, 2, ["A", "C"])

    await db.delete_progress("alice", quiz_id)

    progress = await db.get_progress("alice", quiz_id)
    assert progress == {}


async def test_delete_progress_only_affects_target(test_db, quiz_id):
    """Deleting progress for one user/quiz doesn't affect others."""
    await db.save_progress_answer("alice", quiz_id, 1, ["B"])
    await db.save_progress_answer("bob", quiz_id, 1, ["A"])

    await db.delete_progress("alice", quiz_id)

    assert await db.get_progress("alice", quiz_id) == {}
    assert await db.get_progress("bob", quiz_id) == {1: ["A"]}


async def test_get_in_progress_quiz_ids_empty(test_db, quiz_id):
    """No progress means no in-progress quiz ids."""
    ids = await db.get_in_progress_quiz_ids("alice")
    assert ids == set()


async def test_get_in_progress_quiz_ids(test_db, quiz_id):
    """Quizzes with saved progress appear in the set."""
    await db.save_progress_answer("alice", quiz_id, 1, ["B"])

    ids = await db.get_in_progress_quiz_ids("alice")
    assert quiz_id in ids


async def test_get_in_progress_quiz_ids_cleared_after_delete(test_db, quiz_id):
    """After deleting progress, the quiz id no longer appears."""
    await db.save_progress_answer("alice", quiz_id, 1, ["B"])
    await db.delete_progress("alice", quiz_id)

    ids = await db.get_in_progress_quiz_ids("alice")
    assert quiz_id not in ids


async def test_delete_quiz_clears_progress(test_db, quiz_id):
    """Deleting a quiz also removes its progress rows."""
    await db.save_progress_answer("alice", quiz_id, 1, ["B"])

    await db.delete_quiz(quiz_id)

    progress = await db.get_progress("alice", quiz_id)
    assert progress == {}
    ids = await db.get_in_progress_quiz_ids("alice")
    assert quiz_id not in ids
