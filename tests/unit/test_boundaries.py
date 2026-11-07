"""The context boundaries, enforced: a broken import contract fails the test run.

The contracts live in pyproject.toml under [tool.importlinter]. No database needed:
import-linter reads the source without running it.
"""

from pathlib import Path

from importlinter.cli import EXIT_STATUS_SUCCESS, lint_imports

PYPROJECT = Path(__file__).parents[2] / "pyproject.toml"


def test_the_import_contracts_hold():
    assert lint_imports(config_filename=str(PYPROJECT)) == EXIT_STATUS_SUCCESS
