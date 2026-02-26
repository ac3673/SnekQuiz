"""Web and API routes."""

from __future__ import annotations

import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from . import database as db
from .models import Quiz

logger = logging.getLogger(__name__)

router = APIRouter()

security = HTTPBasic()


def get_current_user(
    request: Request,
    credentials: Annotated[HTTPBasicCredentials, Depends(security)],
) -> tuple[str, bool]:
    """FastAPI dependency - returns (username, is_admin)."""
    return request.app.state.auth.authenticate_user(credentials)


def get_admin_user(
    user: Annotated[tuple[str, bool], Depends(get_current_user)],
) -> str:
    """FastAPI dependency - returns admin username or raises 403."""
    username, is_admin = user
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return username


# ---- helpers ---------------------------------------------------------------


def _tpl(request: Request, name: str, ctx: dict, *, status_code: int = 200) -> HTMLResponse:
    """Shorthand for rendering a template."""
    ctx.setdefault("app_title", request.app.state.settings.app_title)
    ctx["request"] = request
    return request.app.state.templates.TemplateResponse(name, ctx, status_code=status_code)


def _build_question_stats(quiz: Quiz, attempts: list[dict]) -> list[dict]:
    """Compute per-question accuracy from all attempts, sorted by hardest first."""
    if not attempts:
        return []

    total_attempts = len(attempts)
    stats: list[dict] = []

    for i, q in enumerate(quiz.questions, 1):
        correct_count = 0
        for attempt in attempts:
            saved: dict[str, list[str]] = json.loads(attempt["answers_json"])
            user_ans = saved.get(str(q.id), [])
            if sorted(user_ans) == sorted(q.correct_answers):
                correct_count += 1

        pct = round(correct_count * 100.0 / total_attempts, 1)
        stats.append(
            {
                "num": i,
                "question_id": q.id,
                "question_text": q.question_text,
                "correct_answers": q.correct_answers,
                "correct_count": correct_count,
                "total_attempts": total_attempts,
                "correct_pct": pct,
            }
        )

    # Sort by correct_pct ascending (hardest questions first)
    stats.sort(key=lambda s: s["correct_pct"])
    return stats


# ---- Quiz-taker web routes -------------------------------------------------


@router.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    user: Annotated[tuple[str, bool], Depends(get_current_user)],
):
    username, is_admin = user
    quizzes = await db.get_all_quizzes()
    completed_ids = await db.get_completed_quiz_ids(username)
    in_progress_ids = await db.get_in_progress_quiz_ids(username)
    # Don't show "in progress" for quizzes that are already completed
    in_progress_ids -= completed_ids
    return _tpl(
        request,
        "home.html",
        {
            "username": username,
            "is_admin": is_admin,
            "quizzes": quizzes,
            "completed_ids": completed_ids,
            "in_progress_ids": in_progress_ids,
        },
    )


@router.get("/quiz/{quiz_id}", response_class=HTMLResponse)
async def quiz_start(
    quiz_id: int,
    request: Request,
    user: Annotated[tuple[str, bool], Depends(get_current_user)],
):
    """Redirect to the first unanswered question, resuming any saved progress."""
    username, _is_admin = user
    row = await db.get_quiz_by_id(quiz_id)
    if not row:
        raise HTTPException(status_code=404, detail="Quiz not found")

    quiz = Quiz.model_validate_json(row["data_json"])
    progress = await db.get_progress(username, quiz_id)

    # Find the first unanswered question
    for i, q in enumerate(quiz.questions, 1):
        if q.id not in progress:
            return RedirectResponse(url=f"/quiz/{quiz_id}/q/{i}", status_code=302)

    # All questions answered - go straight to the finish interstitial
    return RedirectResponse(url=f"/quiz/{quiz_id}/finish", status_code=302)


@router.get("/quiz/{quiz_id}/q/{question_num}", response_class=HTMLResponse)
async def quiz_question(
    quiz_id: int,
    question_num: int,
    request: Request,
    user: Annotated[tuple[str, bool], Depends(get_current_user)],
):
    username, is_admin = user
    row = await db.get_quiz_by_id(quiz_id)
    if not row:
        raise HTTPException(status_code=404, detail="Quiz not found")

    quiz = Quiz.model_validate_json(row["data_json"])
    if question_num < 1 or question_num > len(quiz.questions):
        raise HTTPException(status_code=404, detail="Question not found")

    question = quiz.questions[question_num - 1]

    # If user already answered this question, skip forward
    progress = await db.get_progress(username, quiz_id)
    if question.id in progress:
        for next_num in range(question_num + 1, len(quiz.questions) + 1):
            next_q = quiz.questions[next_num - 1]
            if next_q.id not in progress:
                return RedirectResponse(url=f"/quiz/{quiz_id}/q/{next_num}", status_code=302)
        return RedirectResponse(url=f"/quiz/{quiz_id}/finish", status_code=302)

    return _tpl(
        request,
        "question.html",
        {
            "username": username,
            "is_admin": is_admin,
            "quiz_id": quiz_id,
            "quiz_name": quiz.quiz_name,
            "question": question,
            "question_num": question_num,
            "total_questions": len(quiz.questions),
        },
    )


@router.post("/quiz/{quiz_id}/answer/{question_id}", response_class=HTMLResponse)
async def submit_answer(
    quiz_id: int,
    question_id: int,
    request: Request,
    user: Annotated[tuple[str, bool], Depends(get_current_user)],
    answers: Annotated[list[str], Form()] = [],  # noqa: B006
):
    username, _is_admin = user
    row = await db.get_quiz_by_id(quiz_id)
    if not row:
        raise HTTPException(status_code=404, detail="Quiz not found")

    quiz = Quiz.model_validate_json(row["data_json"])
    question = next((q for q in quiz.questions if q.id == question_id), None)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")

    await db.save_progress_answer(username, quiz_id, question_id, answers)

    is_correct = sorted(answers) == sorted(question.correct_answers)

    question_num = next(i + 1 for i, q in enumerate(quiz.questions) if q.id == question_id)
    next_url = None
    if question_num < len(quiz.questions):
        next_url = f"/quiz/{quiz_id}/q/{question_num + 1}"

    return _tpl(
        request,
        "partials/answer_feedback.html",
        {
            "quiz_id": quiz_id,
            "question": question,
            "user_answers": answers,
            "correct_answers": question.correct_answers,
            "is_correct": is_correct,
            "next_url": next_url,
        },
    )


@router.get("/quiz/{quiz_id}/finish", response_class=HTMLResponse)
async def quiz_finish(
    quiz_id: int,
    request: Request,
    user: Annotated[tuple[str, bool], Depends(get_current_user)],
):
    """Interstitial page shown when all questions are answered."""
    username, is_admin = user
    row = await db.get_quiz_by_id(quiz_id)
    if not row:
        raise HTTPException(status_code=404, detail="Quiz not found")

    quiz = Quiz.model_validate_json(row["data_json"])
    return _tpl(
        request,
        "complete.html",
        {
            "username": username,
            "is_admin": is_admin,
            "quiz_id": quiz_id,
            "quiz_name": quiz.quiz_name,
            "total_questions": len(quiz.questions),
        },
    )


@router.post("/quiz/{quiz_id}/complete", response_class=HTMLResponse)
async def quiz_complete(
    quiz_id: int,
    request: Request,
    user: Annotated[tuple[str, bool], Depends(get_current_user)],
):
    """Persist the attempt and redirect to the results page (PRG pattern)."""
    username, _is_admin = user
    row = await db.get_quiz_by_id(quiz_id)
    if not row:
        raise HTTPException(status_code=404, detail="Quiz not found")

    quiz = Quiz.model_validate_json(row["data_json"])
    progress = await db.get_progress(username, quiz_id)

    score = 0
    total = len(quiz.questions)
    for q in quiz.questions:
        user_ans = progress.get(q.id, [])
        if sorted(user_ans) == sorted(q.correct_answers):
            score += 1

    attempt_id = await db.save_attempt(
        username=username,
        quiz_id=quiz_id,
        score=score,
        total=total,
        answers={str(k): v for k, v in progress.items()},
    )
    await db.delete_progress(username, quiz_id)
    return RedirectResponse(url=f"/quiz/{quiz_id}/results/{attempt_id}", status_code=303)


@router.get("/quiz/{quiz_id}/results/{attempt_id}", response_class=HTMLResponse)
async def quiz_results(
    quiz_id: int,
    attempt_id: int,
    request: Request,
    user: Annotated[tuple[str, bool], Depends(get_current_user)],
):
    """Show results for a persisted attempt (safe to refresh)."""
    username, is_admin = user
    row = await db.get_quiz_by_id(quiz_id)
    if not row:
        raise HTTPException(status_code=404, detail="Quiz not found")

    attempt = await db.get_attempt_by_id(attempt_id)
    if not attempt or attempt["username"] != username or attempt["quiz_id"] != quiz_id:
        raise HTTPException(status_code=404, detail="Attempt not found")

    quiz = Quiz.model_validate_json(row["data_json"])
    saved_answers: dict[str, list[str]] = json.loads(attempt["answers_json"])

    score = attempt["score"]
    total = attempt["total"]

    review: list[dict] = []
    for i, q in enumerate(quiz.questions, 1):
        user_ans = saved_answers.get(str(q.id), [])
        correct = sorted(user_ans) == sorted(q.correct_answers)
        review.append(
            {
                "num": i,
                "question_text": q.question_text,
                "user_answers": user_ans,
                "correct_answers": q.correct_answers,
                "is_correct": correct,
            }
        )

    return _tpl(
        request,
        "results.html",
        {
            "username": username,
            "is_admin": is_admin,
            "quiz_id": quiz_id,
            "quiz_name": quiz.quiz_name,
            "score": score,
            "total": total,
            "review": review,
        },
    )


# ---- Admin web routes ------------------------------------------------------


@router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    username: Annotated[str, Depends(get_admin_user)],
):
    """Admin portal - overview of all quizzes and aggregated results."""
    stats = await db.get_quiz_stats()
    return _tpl(
        request,
        "admin/dashboard.html",
        {
            "username": username,
            "is_admin": True,
            "stats": stats,
        },
    )


@router.get("/admin/quiz/{quiz_id}", response_class=HTMLResponse)
async def admin_quiz_detail(
    quiz_id: int,
    request: Request,
    username: Annotated[str, Depends(get_admin_user)],
):
    """Admin drilldown - per-question analytics and all attempts."""
    row = await db.get_quiz_by_id(quiz_id)
    if not row:
        raise HTTPException(status_code=404, detail="Quiz not found")

    quiz = Quiz.model_validate_json(row["data_json"])
    attempts = await db.get_quiz_attempts(quiz_id)

    # Build per-question stats from all attempts
    question_stats = _build_question_stats(quiz, attempts)

    return _tpl(
        request,
        "admin/quiz_detail.html",
        {
            "username": username,
            "is_admin": True,
            "quiz_id": quiz_id,
            "quiz_name": quiz.quiz_name,
            "question_count": len(quiz.questions),
            "attempts": attempts,
            "question_stats": question_stats,
        },
    )


@router.get("/admin/quiz/{quiz_id}/attempt/{attempt_id}", response_class=HTMLResponse)
async def admin_attempt_detail(
    quiz_id: int,
    attempt_id: int,
    request: Request,
    username: Annotated[str, Depends(get_admin_user)],
):
    """Admin view of a specific user's quiz submission."""
    row = await db.get_quiz_by_id(quiz_id)
    if not row:
        raise HTTPException(status_code=404, detail="Quiz not found")

    attempt = await db.get_attempt_by_id(attempt_id)
    if not attempt or attempt["quiz_id"] != quiz_id:
        raise HTTPException(status_code=404, detail="Attempt not found")

    quiz = Quiz.model_validate_json(row["data_json"])
    saved_answers: dict[str, list[str]] = json.loads(attempt["answers_json"])

    review: list[dict] = []
    for i, q in enumerate(quiz.questions, 1):
        user_ans = saved_answers.get(str(q.id), [])
        correct = sorted(user_ans) == sorted(q.correct_answers)
        review.append(
            {
                "num": i,
                "question_text": q.question_text,
                "question_type": q.question_type,
                "options": q.options,
                "user_answers": user_ans,
                "correct_answers": q.correct_answers,
                "explanation": q.explanation,
                "is_correct": correct,
            }
        )

    return _tpl(
        request,
        "admin/attempt_detail.html",
        {
            "username": username,
            "is_admin": True,
            "quiz_id": quiz_id,
            "quiz_name": quiz.quiz_name,
            "attempt": attempt,
            "review": review,
        },
    )


@router.get("/admin/upload", response_class=HTMLResponse)
async def admin_upload_form(
    request: Request,
    username: Annotated[str, Depends(get_admin_user)],
):
    """Show the quiz upload form."""
    return _tpl(
        request,
        "admin/upload.html",
        {
            "username": username,
            "is_admin": True,
        },
    )


@router.post("/admin/upload", response_class=HTMLResponse)
async def admin_upload_submit(
    request: Request,
    username: Annotated[str, Depends(get_admin_user)],
    quiz_json: Annotated[str, Form()],
):
    """Handle quiz upload from the admin form."""
    try:
        quiz = Quiz.model_validate_json(quiz_json)
    except Exception as exc:
        return _tpl(
            request,
            "admin/upload.html",
            {
                "username": username,
                "is_admin": True,
                "error": f"Invalid quiz JSON: {exc}",
                "prefill": quiz_json,
            },
            status_code=422,
        )

    if await db.quiz_name_exists(quiz.quiz_name):
        return _tpl(
            request,
            "admin/upload.html",
            {
                "username": username,
                "is_admin": True,
                "error": f"Quiz {quiz.quiz_name!r} already exists",
                "prefill": quiz_json,
            },
            status_code=409,
        )

    quiz_id = await db.insert_quiz(quiz.quiz_name, quiz.model_dump_json())
    logger.info("Admin %r uploaded quiz %r (id=%s)", username, quiz.quiz_name, quiz_id)
    return RedirectResponse(url=f"/admin/quiz/{quiz_id}", status_code=303)


@router.post("/admin/quiz/{quiz_id}/delete", response_class=HTMLResponse)
async def admin_delete_quiz(
    quiz_id: int,
    request: Request,
    username: Annotated[str, Depends(get_admin_user)],
):
    """Delete a quiz and all its attempts."""
    deleted = await db.delete_quiz(quiz_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Quiz not found")
    logger.info("Admin %r deleted quiz id=%s", username, quiz_id)
    return RedirectResponse(url="/admin", status_code=303)


# ---- API routes (admin-only) -----------------------------------------------


@router.post("/api/quizzes", status_code=status.HTTP_201_CREATED)
async def api_upload_quiz(
    quiz: Quiz,
    username: Annotated[str, Depends(get_admin_user)],
):
    """Upload a new quiz via JSON body (admin only)."""
    if await db.quiz_name_exists(quiz.quiz_name):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Quiz {quiz.quiz_name!r} already exists",
        )
    quiz_id = await db.insert_quiz(quiz.quiz_name, quiz.model_dump_json())
    logger.info("Admin %r uploaded quiz %r (id=%s)", username, quiz.quiz_name, quiz_id)
    return {"id": quiz_id, "quiz_name": quiz.quiz_name}


@router.get("/api/quizzes")
async def api_list_quizzes(
    user: Annotated[tuple[str, bool], Depends(get_current_user)],
):
    """Return JSON list of all quizzes."""
    return await db.get_all_quizzes()


@router.get("/api/quizzes/{quiz_id}/stats")
async def api_quiz_stats(
    quiz_id: int,
    username: Annotated[str, Depends(get_admin_user)],
):
    """Return attempts for a quiz (admin only)."""
    row = await db.get_quiz_by_id(quiz_id)
    if not row:
        raise HTTPException(status_code=404, detail="Quiz not found")
    return await db.get_quiz_attempts(quiz_id)


@router.delete("/api/quizzes/{quiz_id}", status_code=status.HTTP_204_NO_CONTENT)
async def api_delete_quiz(
    quiz_id: int,
    username: Annotated[str, Depends(get_admin_user)],
):
    """Delete a quiz (admin only)."""
    deleted = await db.delete_quiz(quiz_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Quiz not found")
    logger.info("Admin %r deleted quiz id=%s via API", username, quiz_id)
