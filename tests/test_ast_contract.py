"""Self-hosting stage 0: the llang-native token/AST data contract."""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from llang import LangError, run_source  # noqa: E402


FUNCTIONS = (
    "make_token", "token_category", "token_text", "token_line", "token_column",
    "token_digest", "make_node", "set_field", "field", "has_field", "node_fields",
    "node_digest", "same_value", "same_token", "same_node", "describe_token",
)


def run(source):
    for function in FUNCTIONS:
        source = re.sub(rf"\bcall {function}\b",
                        f"call {function} from ast_contract", source)
    program = "use the ast_contract module\n" + source
    return run_source(program).output


class AstContractTests(unittest.TestCase):
    def test_token_construction_and_access(self):
        self.assertEqual(run("""
set t to call make_token with category = "WORD", content = "hello", line = 3, column = 7
show call token_category with token = t
show call token_text with token = t
show call token_line with token = t
show call token_column with token = t
"""), ["WORD", "hello", "3", "7"])

    def test_token_digest(self):
        self.assertEqual(run("""
set t to call make_token with category = "WORD", content = "hello", line = 3, column = 7
show call token_digest with token = t
"""), ["[WORD, hello, 3, 7]"])

    def test_describe_token(self):
        self.assertEqual(run("""
set t to call make_token with category = "WORD", content = "hello", line = 3, column = 7
show call describe_token with token = t
"""), ["WORD hello at 3:7"])

    def test_node_construction_and_fields(self):
        self.assertEqual(run("""
set n to call make_node with type = "Binary", line = 1, column = 4
call set_field with node = n, name ="op", value = "ADD"
call set_field with node = n, name ="left", value = (call make_node with type = "Literal", line = 1, column = 4)
show call field with node = n, name ="op"
show call has_field with node = n, name ="op"
show call has_field with node = n, name ="missing"
show call node_digest with node = n
"""), ["ADD", "true", "false", "[left, op, pos, type]"])

    def test_structural_equality(self):
        self.assertEqual(run("""
set a to call make_node with type = "Literal", line = 1, column = 1
set b to call make_node with type = "Literal", line = 1, column = 1
set c to call make_node with type = "Variable", line = 1, column = 1
show call same_node with left = a, right = b
show call same_node with left = a, right = c
"""), ["true", "false"])

    def test_missing_field_fails_loudly(self):
        with self.assertRaises(LangError):
            run('show call field with node = (call make_node with type = "X", line = 1, column = 1), name ="nope"')


if __name__ == "__main__":
    unittest.main()
