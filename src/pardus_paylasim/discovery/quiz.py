"""Sınıf sınavları: soru dağıtımı + cevap toplama + puanlama (P2P).

neural-system `applications/quiz_engine.py` taşınmasıdır (yalnız stdlib).
Farklar: merkezi hub YOKTUR — sınav JSON dosyayla dağıtılır (çoklu
gönderim), cevaplar JSON dosyayla öğretmene döner; puanlama öğretmende
yerel yapılır. Zaman bonusu ve liderlik tablosu korunur.
"""

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

QUIZ_FORMAT = "pardus-quiz-v1"
ANSWERS_FORMAT = "pardus-answers-v1"


class QuizState(Enum):
    CREATED = "created"
    ACTIVE = "active"
    FINISHED = "finished"
    CANCELLED = "cancelled"


@dataclass
class Question:
    question_id: str
    text: str
    options: List[str]
    correct_answer: int  # 0-3 indeks
    time_limit: int = 30
    points: int = 100

    def to_dict(self) -> dict:
        return {
            "question_id": self.question_id,
            "text": self.text,
            "options": self.options,
            "correct_answer": self.correct_answer,
            "time_limit": self.time_limit,
            "points": self.points,
        }

    @staticmethod
    def from_dict(d: dict) -> "Question":
        return Question(
            question_id=str(d.get("question_id", uuid.uuid4().hex[:8])),
            text=str(d.get("text", "")),
            options=[str(o) for o in d.get("options", [])],
            correct_answer=int(d.get("correct_answer", 0)),
            time_limit=int(d.get("time_limit", 30)),
            points=int(d.get("points", 100)),
        )


@dataclass
class Answer:
    board_id: str
    board_name: str
    question_id: str
    answer_index: int
    time_taken: float
    is_correct: bool = False
    points_earned: int = 0

    def to_dict(self) -> dict:
        return {
            "board_id": self.board_id,
            "board_name": self.board_name,
            "question_id": self.question_id,
            "answer_index": self.answer_index,
            "time_taken": self.time_taken,
            "is_correct": self.is_correct,
            "points_earned": self.points_earned,
        }


@dataclass
class Quiz:
    quiz_id: str
    title: str
    questions: List[Question]
    target_boards: List[str] = field(default_factory=list)
    state: QuizState = QuizState.CREATED
    current_question_index: int = 0
    created_at: float = 0.0
    started_at: float = 0.0
    finished_at: float = 0.0
    answers: List[Answer] = field(default_factory=list)
    scores: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = time.time()

    @property
    def current_question(self) -> Optional[Question]:
        if 0 <= self.current_question_index < len(self.questions):
            return self.questions[self.current_question_index]
        return None

    @property
    def question_count(self) -> int:
        return len(self.questions)

    @property
    def is_finished(self) -> bool:
        return self.current_question_index >= len(self.questions)


class QuizEngine:
    """Sınav yaşam döngüsü (oluştur → yanıtla → puanla)."""

    def __init__(self):
        self.quizzes: Dict[str, Quiz] = {}

    def create_quiz(self, title: str, questions_data: list,
                    target_boards: Optional[list] = None) -> Quiz:
        quiz_id = f"quiz_{int(time.time())}"
        questions = []
        for i, q in enumerate(questions_data):
            questions.append(Question(
                question_id=f"{quiz_id}_q{i + 1}",
                text=q.get("text", ""),
                options=list(q.get("options", [])),
                correct_answer=int(q.get("correct_answer", 0)),
                time_limit=int(q.get("time_limit", 30)),
                points=int(q.get("points", 100)),
            ))
        quiz = Quiz(quiz_id=quiz_id, title=title, questions=questions,
                    target_boards=list(target_boards or []))
        self.quizzes[quiz_id] = quiz
        return quiz

    def submit_answer(self, quiz_id: str, board_id: str, board_name: str,
                      question_id: str, answer_index: int,
                      time_taken: float) -> Optional[dict]:
        quiz = self.quizzes.get(quiz_id)
        if not quiz or quiz.state != QuizState.ACTIVE:
            return None
        question = next((q for q in quiz.questions
                         if q.question_id == question_id), None)
        if question is None:
            return None
        is_correct = answer_index == question.correct_answer
        points = 0
        if is_correct:
            time_bonus = max(0.0, 1 - (time_taken / max(1, question.time_limit)))
            points = int(question.points * (0.7 + 0.3 * time_bonus))
        answer = Answer(board_id, board_name, question_id, answer_index,
                        time_taken, is_correct, points)
        quiz.answers.append(answer)
        entry = quiz.scores.setdefault(
            board_id, {"name": board_name, "score": 0, "correct": 0, "total": 0})
        entry["score"] += points
        entry["total"] += 1
        if is_correct:
            entry["correct"] += 1
        return {"is_correct": is_correct, "points_earned": points,
                "correct_answer": question.correct_answer,
                "scores": quiz.scores}

    def get_scores(self, quiz_id: str) -> dict:
        quiz = self.quizzes.get(quiz_id)
        return dict(quiz.scores) if quiz else {}

    def leaderboard(self, quiz_id: str) -> list:
        quiz = self.quizzes.get(quiz_id)
        if not quiz:
            return []
        rows = []
        for board_id, s in quiz.scores.items():
            rows.append({
                "board_id": board_id, "name": s["name"], "score": s["score"],
                "correct": s["correct"], "total": s["total"],
                "accuracy": round(s["correct"] / max(1, s["total"]) * 100, 1),
            })
        rows.sort(key=lambda r: r["score"], reverse=True)
        for i, r in enumerate(rows):
            r["rank"] = i + 1
        return rows


def parse_questions_text(text: str) -> List[dict]:
    """Basit soru formatını ayrıştırır. Satır başına soru::

        Soru metni | A | B | C | D | doğru:2 | süre:30 | puan:100

    - En az: metin + 2 şık. Şık sayısı 2-6 arası kabul edilir.
    - `doğru:N` zorunlu (1-tabanlı); süre/puan opsiyonel.
    - `#` ile başlayan satırlar ve boş satırlar atlanır.

    Hatalı satırda ValueError (satır numaralı).
    """
    out = []
    for lineno, raw in enumerate((text or "").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 4:
            raise ValueError(f"Satır {lineno}: en az soru + 2 şık gerekli.")
        text_part = parts[0]
        options: List[str] = []
        correct = None
        time_limit = 30
        points = 100
        for part in parts[1:]:
            low = part.lower()
            if low.startswith("doğru:") or low.startswith("dogru:"):
                try:
                    correct = int(part.split(":", 1)[1].strip())
                except ValueError:
                    correct = None
            elif low.startswith("süre:") or low.startswith("sure:"):
                try:
                    time_limit = max(5, int(part.split(":", 1)[1].strip()))
                except ValueError:
                    pass
            elif low.startswith("puan:"):
                try:
                    points = max(1, int(part.split(":", 1)[1].strip()))
                except ValueError:
                    pass
            else:
                options.append(part)
        if not text_part:
            raise ValueError(f"Satır {lineno}: soru metni boş.")
        if not 2 <= len(options) <= 6:
            raise ValueError(f"Satır {lineno}: 2-6 şık gerekli.")
        if correct is None or not 1 <= correct <= len(options):
            raise ValueError(f"Satır {lineno}: geçerli `doğru:N` gerekli.")
        out.append({"text": text_part, "options": options,
                    "correct_answer": correct - 1, "time_limit": time_limit,
                    "points": points})
    if not out:
        raise ValueError("Hiç soru bulunamadı.")
    return out


def quiz_to_file(quiz: Quiz, path: str, created_by: str = "") -> str:
    doc = {"format": QUIZ_FORMAT, "quiz_id": quiz.quiz_id,
           "title": quiz.title, "created_by": created_by,
           "created_at": quiz.created_at,
           "questions": [q.to_dict() for q in quiz.questions]}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    return path


def quiz_from_file(path: str) -> Quiz:
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    if doc.get("format") != QUIZ_FORMAT:
        raise ValueError("Desteklenmeyen sınav dosyası.")
    engine = QuizEngine()
    quiz = engine.create_quiz(doc.get("title", "Sınav"),
                              [{"text": q["text"], "options": q["options"],
                                "correct_answer": q.get("correct_answer", 0),
                                "time_limit": q.get("time_limit", 30),
                                "points": q.get("points", 100)}
                               for q in doc.get("questions", [])])
    quiz.quiz_id = doc.get("quiz_id", quiz.quiz_id)
    engine.quizzes[quiz.quiz_id] = quiz
    return quiz


def answers_to_file(quiz: Quiz, answers: List[Answer], board_id: str,
                    board_name: str, path: str) -> str:
    """Cevap dosyası soruları GÖMER (puanlama tek dosyayla yapılır)."""
    doc = {"format": ANSWERS_FORMAT, "quiz_id": quiz.quiz_id,
           "quiz_title": quiz.title, "board_id": board_id,
           "board_name": board_name,
           "questions": [q.to_dict() for q in quiz.questions],
           "answers": [a.to_dict() for a in answers]}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    return path


def score_answers_file(path: str) -> dict:
    """Cevap dosyasını puanlar: {board_name, correct, total, score, rows}."""
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    if doc.get("format") != ANSWERS_FORMAT:
        raise ValueError("Desteklenmeyen cevap dosyası.")
    engine = QuizEngine()
    quiz = engine.create_quiz(
        doc.get("quiz_title", "Sınav"),
        [{"text": q["text"], "options": q["options"],
          "correct_answer": q.get("correct_answer", 0),
          "time_limit": q.get("time_limit", 30),
          "points": q.get("points", 100)} for q in doc.get("questions", [])])
    quiz.quiz_id = doc.get("quiz_id", quiz.quiz_id)
    engine.quizzes[quiz.quiz_id] = quiz
    quiz.state = QuizState.ACTIVE
    board_id = doc.get("board_id", "?")
    board_name = doc.get("board_name", "?")
    rows = []
    for a in doc.get("answers", []):
        res = engine.submit_answer(
            quiz.quiz_id, board_id, board_name, a.get("question_id", ""),
            int(a.get("answer_index", -1)), float(a.get("time_taken", 0)))
        rows.append({"question_id": a.get("question_id", ""),
                     "is_correct": bool(res and res["is_correct"]),
                     "points": res["points_earned"] if res else 0})
    entry = engine.get_scores(quiz.quiz_id).get(board_id, {})
    return {"board_name": board_name, "correct": entry.get("correct", 0),
            "total": entry.get("total", 0), "score": entry.get("score", 0),
            "rows": rows}
