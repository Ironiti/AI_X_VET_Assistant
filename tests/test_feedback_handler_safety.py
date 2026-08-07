import ast
from pathlib import Path
import unittest


SOURCE_PATH = Path(__file__).resolve().parents[1] / "bot" / "handlers" / "feedback.py"
TREE = ast.parse(SOURCE_PATH.read_text(encoding="utf-8"))


def function(name):
    return next(
        node for node in TREE.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name
    )


def contains_return(node):
    return any(isinstance(child, ast.Return) for child in ast.walk(node))


class FeedbackHandlerSafetyTests(unittest.TestCase):
    def test_draft_and_smtp_failures_return_before_success_path(self):
        for name in (
            "process_callback_message",
            "process_feedback_message",
            "process_results_request",
        ):
            with self.subTest(handler=name):
                handler = function(name)
                draft_failure = next(
                    child for child in handler.body
                    if isinstance(child, ast.If)
                    and "draft is None" in ast.unparse(child.test)
                )
                self.assertTrue(contains_return(draft_failure))

                smtp_failure = next(
                    child for child in handler.body
                    if isinstance(child, ast.If)
                    and "email_sent" in ast.unparse(child.test)
                )
                self.assertTrue(contains_return(smtp_failure))
                self.assertTrue(any(
                    isinstance(child, ast.Await)
                    and "draft_sending=False" in ast.unparse(child)
                    for child in ast.walk(smtp_failure)
                ))

                success_clear = [
                    child.lineno for child in ast.walk(handler)
                    if isinstance(child, ast.Await)
                    and "state.clear" in ast.unparse(child)
                    and child.lineno > smtp_failure.end_lineno
                ]
                self.assertTrue(success_clear)

    def test_feedback_is_persisted_only_after_email_success_check(self):
        for name in ("process_feedback_message", "process_results_request"):
            with self.subTest(handler=name):
                handler = function(name)
                smtp_failure = next(
                    child for child in handler.body
                    if isinstance(child, ast.If) and "email_sent" in ast.unparse(child.test)
                )
                db_write = next(
                    child for child in ast.walk(handler)
                    if isinstance(child, ast.Await) and "db.add_feedback" in ast.unparse(child)
                )
                self.assertGreater(db_write.lineno, smtp_failure.end_lineno)


if __name__ == "__main__":
    unittest.main()
