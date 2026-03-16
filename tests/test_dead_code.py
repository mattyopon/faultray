"""Dead code detection tests."""
import ast
import os
from pathlib import Path


def _get_all_defined_names(src_dir):
    """Find all function/class names defined in source."""
    defined = {}
    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for f in files:
            if f.endswith('.py') and not f.startswith('__'):
                path = os.path.join(root, f)
                with open(path) as fh:
                    try:
                        tree = ast.parse(fh.read())
                    except SyntaxError:
                        continue
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if not node.name.startswith('_'):
                            defined[node.name] = path
                    elif isinstance(node, ast.ClassDef):
                        defined[node.name] = path
    return defined


def _get_all_references(src_dir, test_dir):
    """Find all names referenced in source and tests."""
    referenced = set()
    for search_dir in [src_dir, test_dir]:
        for root, dirs, files in os.walk(search_dir):
            dirs[:] = [d for d in dirs if d != '__pycache__']
            for f in files:
                if f.endswith('.py'):
                    path = os.path.join(root, f)
                    with open(path) as fh:
                        content = fh.read()
                    try:
                        tree = ast.parse(content)
                    except SyntaxError:
                        continue
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Name):
                            referenced.add(node.id)
                        elif isinstance(node, ast.Attribute):
                            referenced.add(node.attr)
    return referenced


def _get_string_references(src_dir, test_dir):
    """Find all string literals that might reference names (decorators, __all__, etc.)."""
    refs = set()
    for search_dir in [src_dir, test_dir]:
        for root, dirs, files in os.walk(search_dir):
            dirs[:] = [d for d in dirs if d != '__pycache__']
            for f in files:
                if f.endswith('.py'):
                    path = os.path.join(root, f)
                    with open(path) as fh:
                        content = fh.read()
                    try:
                        tree = ast.parse(content)
                    except SyntaxError:
                        continue
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Constant) and isinstance(node.value, str):
                            # Capture identifiers embedded in strings
                            refs.add(node.value)
    return refs


def test_no_significant_dead_code():
    """Public functions/classes should be referenced somewhere.

    This test is informational — it flags potentially unreferenced code
    but allows a generous margin for false positives (framework-called
    route handlers, Protocol implementations, Pydantic validators, etc.).
    """
    defined = _get_all_defined_names("src/faultray")
    referenced = _get_all_references("src/faultray", "tests")
    string_refs = _get_string_references("src/faultray", "tests")
    all_refs = referenced | string_refs

    dead = []
    for name, path in sorted(defined.items()):
        if name not in all_refs:
            dead.append(f"{name} in {path}")

    # Large codebases with FastAPI route handlers, Pydantic models, and
    # framework-invoked callbacks will have many false positives.  The
    # threshold is intentionally generous; a spike above it signals a
    # real accumulation problem.
    assert len(dead) < 300, (
        f"Found {len(dead)} potentially dead code items "
        f"(threshold 300):\n" + "\n".join(dead[:30])
    )
