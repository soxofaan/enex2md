from enex2md.cli import app
from pathlib import Path
from click.testing import CliRunner

enex_root = Path(__file__).parent / "enex"


def test_basic_no_args():
    result = CliRunner().invoke(app, args=[])
    assert result.exit_code == 2
    assert isinstance(result.exception, SystemExit)


def test_basic_nonexistent_file():
    args = ["inexistent.enex"]
    result = CliRunner().invoke(app, args=args)
    assert result.exit_code == 1
    assert isinstance(result.exception, FileNotFoundError)


def test_basic_stdout():
    path = (enex_root / "notebook01.enex").absolute()
    args = [str(path)]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0
    assert result.output == (
        "--- New Note ---\n"
        "# The title\n"
        "\n"
        "## Note metadata\n"
        "\n"
        "- Title: The title\n"
        "- Author: John Doe\n"
        "- Created: 2023-07-09T18:42:04+00:00\n"
        "- Updated: 2023-07-09T18:43:22+00:00\n"
        "\n"
        "## Note Content\n"
        "\n"
        "Things to buy:\n"
        "\n"
        "  * apple\n"
        "  * banana\n"
        "  * chocolate\n"
        "--- End Note ---\n"
    )
