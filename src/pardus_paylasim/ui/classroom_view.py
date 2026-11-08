"""
GTK4 Classroom & ETAP Smart Board View Controller and Component.
Manages classroom boards, teacher broadcasts, file distribution, and quizzes.
"""

from collections.abc import Callable
from typing import Any

from pardus_paylasim.discovery.classroom import (
    ROLE_BOARD,
    ROLE_NONE,
    ROLE_TEACHER,
    boards_only,
    broadcast_text,
    summarize_broadcast,
)
from pardus_paylasim.discovery.quiz import (
    Quiz,
    QuizEngine,
    parse_questions_text,
    score_answers_file,
)

ROLE_STUDENT = ROLE_NONE


class ClassroomViewHandler:
    """Controller for Classroom & Smart Board operations."""

    def __init__(self, role: str = ROLE_STUDENT, classroom_name: str = "Pardus Sınıfı"):
        self.role = role
        self.classroom_name = classroom_name
        self.quiz_engine = QuizEngine()

    def set_role(self, role: str) -> None:
        self.role = role

    def get_role_permissions(self) -> dict[str, bool]:
        is_teacher = self.role == ROLE_TEACHER
        is_board = self.role == ROLE_BOARD
        is_student = self.role == ROLE_STUDENT
        return {
            "can_broadcast": is_teacher,
            "can_distribute": is_teacher,
            "can_create_quiz": is_teacher,
            "can_score_quiz": is_teacher,
            "can_answer_quiz": is_student or is_board,
            "is_board": is_board,
        }

    @staticmethod
    def filter_boards(devices: list) -> list:
        return boards_only(devices)

    @staticmethod
    def broadcast_message(
        devices: list,
        text: str,
        timeout: float = 5.0,
        progress_cb: Callable[[int, int], None] | None = None,
    ) -> dict[str, bool]:
        return broadcast_text(devices, text, timeout=timeout, progress_cb=progress_cb)

    @staticmethod
    def summarize_results(results: dict[str, bool]) -> str:
        return summarize_broadcast(results)

    def create_quiz(self, raw_text: str, title: str = "Pardus Sınavı") -> Quiz:
        """Soruları ayrıştırır ve Quiz nesnesi oluşturur."""
        questions_data = parse_questions_text(raw_text)
        return self.quiz_engine.create_quiz(title, questions_data)

    @staticmethod
    def evaluate_quiz_file(path: str) -> dict:
        return score_answers_file(path)


class ClassroomViewComponent:
    """GTK4 Sınıf ve Etkileşimli Tahta Görünüm Bileşeni."""

    def __init__(self, handler: ClassroomViewHandler | None = None):
        self.handler = handler or ClassroomViewHandler()
        self.container: Any = None
        self.selected_target_ips: set[str] = set()

    def update_targets(self, ips: set[str]) -> None:
        self.selected_target_ips = set(ips)

    def is_target_selected(self) -> bool:
        return len(self.selected_target_ips) > 0
