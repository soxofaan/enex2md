import textwrap
from pathlib import Path

from click.testing import CliRunner

from enex2md.cli import app

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


def test_default_disk_legacy(tmp_path, monkeypatch):
    path = (enex_root / "notebook01.enex").absolute()
    args = ["--disk", str(path)]
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0
    assert result.output == ""

    generated_files = [p.relative_to(tmp_path) for p in tmp_path.glob("**/*") if p.is_file()]
    assert len(generated_files) == 1
    md_path = generated_files[0]
    assert md_path.name == "The_title.md"
    md_content = md_path.read_text()
    assert md_content == textwrap.dedent(
        """\
        # The title

        ## Note metadata

        - Title: The title
        - Author: John Doe
        - Created: 2023-07-09T18:42:04+00:00
        - Updated: 2023-07-09T18:43:22+00:00

        ## Note Content

        Things to buy:

          * apple
          * banana
          * chocolate
        """
    )


def test_custom_paths(tmp_path, monkeypatch):
    path = (enex_root / "notebook03.enex").absolute()
    args = [
        "--disk",
        str(path),
        "--output-root",
        "dump",
        "--note-path-template",
        "{enex}/{created:%Y}/{created:%Y%m%d}-{title}.md",
        "--attachments-path-template",
        "{enex}/_resources/{created:%Y}/{created:%Y%m%d}-{title}",
    ]
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0
    assert result.output == ""

    generated_files = sorted(p.relative_to(tmp_path) for p in tmp_path.glob("**/*") if p.is_file())
    assert generated_files == [
        Path("dump/notebook03/2023/20230712-Fa_fa_fa.md"),
        Path("dump/notebook03/_resources/2023/20230712-Fa_fa_fa/rckrll.png"),
    ]
    assert generated_files[0].read_text() == textwrap.dedent(
        """\
        # Fa fa fa

        ## Note metadata

        - Title: Fa fa fa
        - Author: John Doe
        - Created: 2023-07-12T20:16:08+00:00
        - Updated: 2023-07-12T20:18:38+00:00

        ## Note Content

        lo lo lo

        ![rckrll.png](../_resources/2023/20230712-Fa_fa_fa/rckrll.png)
        la la la
        """
    )
    assert generated_files[1].read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
