#!/usr/bin/env python3
"""
Validate machine-readable launch path terminology.

The TOML file is a small machine-readable subset of
docs/rules/skill_launch_paths_definitions.md. It must not become a second
implementation of changed-line policy.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from tests.forge.subagent.skill_launch_terms import REPO_ROOT, load_terms

POLICY_TEST = REPO_ROOT / 'tests/forge/subagent/test_changed_lines_policy.py'


def _docstring_constant_ids(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    docstring_owners = (
        ast.Module,
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
    )
    for node in ast.walk(tree):
        if not isinstance(node, docstring_owners):
            continue
        if not node.body:
            continue
        first = node.body[0]
        if not isinstance(first, ast.Expr):
            continue
        if isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
            ids.add(id(first.value))
    return ids


def _string_literals_excluding_docstrings(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding='utf-8'))
    docstring_ids = _docstring_constant_ids(tree)
    literals: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant):
            continue
        if not isinstance(node.value, str):
            continue
        if id(node) in docstring_ids:
            continue
        literals.append(node.value)
    return literals


class TestSkillLaunchTerms(unittest.TestCase):
    def setUp(self) -> None:
        self.terms_doc = load_terms()

    def test_source_doc_exists(self) -> None:
        source_doc = self.terms_doc.get('metadata', {}).get('source_doc')
        self.assertIsInstance(source_doc, str)
        self.assertTrue(
            (REPO_ROOT / source_doc).is_file(),
            f'metadata.source_doc does not exist: {source_doc}',
        )

    def test_launch_context_terms_are_non_empty_strings(self) -> None:
        terms = self.terms_doc.get('launch_context', {}).get('terms')
        self.assertIsInstance(terms, list)
        self.assertGreater(len(terms), 0)
        for term in terms:
            with self.subTest(term=term):
                self.assertIsInstance(term, str)
                self.assertNotEqual(term.strip(), '')

    def test_launch_context_terms_appear_in_source_doc(self) -> None:
        source_doc = self.terms_doc['metadata']['source_doc']
        source_text = (REPO_ROOT / source_doc).read_text(encoding='utf-8')
        for term in self.terms_doc['launch_context']['terms']:
            with self.subTest(term=term):
                self.assertIn(term, source_text)

    def test_launch_context_terms_are_not_duplicated_in_changed_line_gate(self) -> None:
        literals = _string_literals_excluding_docstrings(POLICY_TEST)
        for term in self.terms_doc['launch_context']['terms']:
            with self.subTest(term=term):
                self.assertNotIn(term, literals)


if __name__ == '__main__':
    unittest.main()
