"""Sınav (quiz) testleri: motor + format + dosya turu (soket/GTK yok)."""

import json
import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

SAMPLE = """Türkiye'nin başkenti neresidir? | İstanbul | Ankara | İzmir | Bursa | doğru:2
2+2 kaçtır? | 3 | 4 | 5 | doğru:2 | süre:20 | puan:50
# yorum satırı atlanır

Boşluk testi | A | B | doğru:1"""


class TestParseQuestions(unittest.TestCase):
    def test_valid(self):
        from pardus_paylasim.discovery.quiz import parse_questions_text
        qs = parse_questions_text(SAMPLE)
        self.assertEqual(len(qs), 3)
        self.assertEqual(qs[0]["correct_answer"], 1)
        self.assertEqual(qs[1]["time_limit"], 20)
        self.assertEqual(qs[1]["points"], 50)
        self.assertEqual(qs[2]["options"], ["A", "B"])

    def test_missing_correct_rejected(self):
        from pardus_paylasim.discovery.quiz import parse_questions_text
        with self.assertRaises(ValueError):
            parse_questions_text("Soru | A | B")

    def test_too_few_options_rejected(self):
        from pardus_paylasim.discovery.quiz import parse_questions_text
        with self.assertRaises(ValueError):
            parse_questions_text("Soru | A | doğru:1")

    def test_empty_rejected(self):
        from pardus_paylasim.discovery.quiz import parse_questions_text
        with self.assertRaises(ValueError):
            parse_questions_text("   \n# yalnız yorum\n")


class TestEngine(unittest.TestCase):
    def _quiz(self):
        from pardus_paylasim.discovery.quiz import QuizEngine, parse_questions_text
        engine = QuizEngine()
        return engine, engine.create_quiz("Mat", parse_questions_text(SAMPLE))

    def test_create_and_counts(self):
        engine, quiz = self._quiz()
        self.assertEqual(quiz.question_count, 3)
        self.assertFalse(quiz.is_finished)

    def test_submit_scores_with_time_bonus(self):
        from pardus_paylasim.discovery.quiz import QuizState
        engine, quiz = self._quiz()
        quiz.state = QuizState.ACTIVE
        qid = quiz.questions[0].question_id
        fast = engine.submit_answer(quiz.quiz_id, "t1", "Tahta1", qid, 1, 1.0)
        self.assertTrue(fast["is_correct"])
        slow = engine.submit_answer(quiz.quiz_id, "t2", "Tahta2", qid, 1, 29.0)
        self.assertTrue(slow["is_correct"])
        # Hızlı cevap daha çok puan alır.
        self.assertGreater(fast["points_earned"], slow["points_earned"])
        wrong = engine.submit_answer(quiz.quiz_id, "t3", "Tahta3", qid, 0, 2.0)
        self.assertFalse(wrong["is_correct"])
        self.assertEqual(wrong["points_earned"], 0)

    def test_inactive_quiz_rejects(self):
        engine, quiz = self._quiz()
        qid = quiz.questions[0].question_id
        self.assertIsNone(engine.submit_answer(
            quiz.quiz_id, "t1", "T", qid, 1, 1.0))

    def test_leaderboard_order(self):
        from pardus_paylasim.discovery.quiz import QuizState
        engine, quiz = self._quiz()
        quiz.state = QuizState.ACTIVE
        qid = quiz.questions[0].question_id
        engine.submit_answer(quiz.quiz_id, "t1", "A", qid, 0, 1.0)
        engine.submit_answer(quiz.quiz_id, "t2", "B", qid, 1, 1.0)
        lb = engine.leaderboard(quiz.quiz_id)
        self.assertEqual(lb[0]["board_id"], "t2")
        self.assertEqual(lb[0]["rank"], 1)
        self.assertEqual(lb[1]["rank"], 2)


class TestFileRoundtrip(unittest.TestCase):
    def test_quiz_file_and_score_file(self):
        from pardus_paylasim.discovery.quiz import (
            QuizState, answers_to_file, parse_questions_text, quiz_from_file,
            quiz_to_file, score_answers_file,
        )
        with tempfile.TemporaryDirectory() as tmp:
            from pardus_paylasim.discovery.quiz import QuizEngine
            engine = QuizEngine()
            quiz = engine.create_quiz("Fen", parse_questions_text(SAMPLE))
            qp = quiz_to_file(quiz, os.path.join(tmp, "sinav.json"), "Ogretmen")
            q2 = quiz_from_file(qp)
            self.assertEqual(q2.title, "Fen")
            self.assertEqual(q2.question_count, 3)
            # Öğrenci cevapları gömülü dosyaya yazılır (doğruluk burada
            # hesaplanmaz; puanlama score_answers_file içinde yapılır).
            from pardus_paylasim.discovery.quiz import Answer
            answers = []
            for i, q in enumerate(q2.questions):
                # İlk ikisi doğru, sonuncusu bilerek yanlış.
                pick = q.correct_answer if i < 2 else (1 - q.correct_answer)
                answers.append(Answer("tahta1", "Tahta 1", q.question_id,
                                      pick, 2.0))
            ap = answers_to_file(q2, answers, "tahta1", "Tahta 1",
                                 os.path.join(tmp, "cevap.json"))
            res = score_answers_file(ap)
            self.assertEqual(res["board_name"], "Tahta 1")
            self.assertEqual(res["correct"], 2)
            self.assertEqual(res["total"], 3)
            self.assertGreater(res["score"], 0)

    def test_bad_format_rejected(self):
        from pardus_paylasim.discovery.quiz import quiz_from_file, score_answers_file
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "x.json")
            with open(p, "w") as f:
                json.dump({"format": "bilinmeyen"}, f)
            with self.assertRaises(ValueError):
                quiz_from_file(p)
            with self.assertRaises(ValueError):
                score_answers_file(p)


if __name__ == "__main__":
    unittest.main()
