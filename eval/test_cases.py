from eval.test_cases_data import TEST_CASES_DATA
from schemas.eval import TestCase

TEST_CASES = [TestCase(**tc) for tc in TEST_CASES_DATA]