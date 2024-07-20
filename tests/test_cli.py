import textwrap
from pathlib import Path
from typing import List, Tuple, Union

import pytest
from click.testing import CliRunner

from enex2md.cli import app
from enex2md.convert import TIMEZONE

enex_root = Path(__file__).parent / "enex"


def _list_all_files(root, with_size: bool = False) -> List[Union[Path, Tuple[Path, int]]]:
    files = (p for p in root.glob("**/*") if p.is_file())
    if with_size:
        return sorted((p.relative_to(root), p.stat().st_size) for p in files)
    else:
        return sorted(p.relative_to(root) for p in files)


class TestCli:
    @pytest.fixture(autouse=True)
    def chdir_tmp_path(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

    def test_basic_no_args(self):
        result = CliRunner().invoke(app, args=[])
        assert result.exit_code == 2
        assert isinstance(result.exception, SystemExit)

    def test_basic_nonexistent_file(self):
        args = ["inexistent.enex"]
        result = CliRunner().invoke(app, args=args)
        assert result.exit_code == 2
        assert isinstance(result.exception, SystemExit)
        assert "Error: Invalid value for 'ENEX_SOURCES...': Path 'inexistent.enex' does not exist." in result.stdout

    def test_basic_stdout(self):
        path = (enex_root / "notebook01.enex").absolute()
        args = [str(path), "--output-root", "-"]
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

    def test_basic(self, tmp_path):
        path = (enex_root / "notebook01.enex").absolute()
        args = [str(path)]
        result = CliRunner().invoke(app, args)
        assert result.exit_code == 0
        assert result.output == ""

        generated_files = _list_all_files(tmp_path)
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

    def test_custom_paths(self, tmp_path):
        path = (enex_root / "notebook03.enex").absolute()
        args = [
            "--output-root",
            "dump",
            "--note-path-template",
            "{enex}/{created:%Y}/{created:%Y%m%d}-{title}.md",
            "--attachments-path-template",
            "{enex}/_resources/{created:%Y}/{created:%Y%m%d}-{title}",
            str(path),
        ]
        result = CliRunner().invoke(app, args)
        assert result.exit_code == 0
        assert result.output == ""

        generated_files = _list_all_files(tmp_path)
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

    def test_multiple_enex_paths(self, tmp_path):
        args = [
            "--output-root",
            "dump",
            "--note-path-template",
            "{enex}/{created:%Y}/{created:%Y%m%d}-{title}.md",
            "--attachments-path-template",
            "{enex}/_resources/{created:%Y}/{created:%Y%m%d}-{title}",
            str((enex_root / "notebook01.enex").absolute()),
            str((enex_root / "notebook02.enex").absolute()),
            str((enex_root / "notebook03.enex").absolute()),
        ]
        result = CliRunner().invoke(app, args)
        assert result.exit_code == 0
        assert result.output == ""

        generated_files = _list_all_files(tmp_path)
        assert generated_files == [
            Path("dump/notebook01/2023/20230709-The_title.md"),
            Path("dump/notebook02/2023/20230709-Nested_lists.md"),
            Path("dump/notebook03/2023/20230712-Fa_fa_fa.md"),
            Path("dump/notebook03/_resources/2023/20230712-Fa_fa_fa/rckrll.png"),
        ]

    def test_enex_folder(self, tmp_path):
        args = [
            "--output-root",
            "dump",
            "--note-path-template",
            "{enex}/{created:%Y}/{created:%Y%m%d}-{title}.md",
            "--attachments-path-template",
            "{enex}/_resources/{created:%Y}/{created:%Y%m%d}-{title}",
            str(enex_root),
        ]
        result = CliRunner().invoke(app, args)
        assert result.exit_code == 0
        assert result.output == ""

        generated_files = _list_all_files(tmp_path)
        assert generated_files == [
            Path("dump/notebook01/2023/20230709-The_title.md"),
            Path("dump/notebook02/2023/20230709-Nested_lists.md"),
            Path("dump/notebook03/2023/20230712-Fa_fa_fa.md"),
            Path("dump/notebook03/_resources/2023/20230712-Fa_fa_fa/rckrll.png"),
            Path("dump/notebook03-2/2023/20230712-Fa_fa_fa.md"),
            Path("dump/notebook03-2/_resources/2023/20230712-Fa_fa_fa/rckrll.png"),
            Path("dump/notebook03-3/2023/20230712-Fa_fa_fa.md"),
            Path("dump/notebook03-3/_resources/2023/20230712-Fa_fa_fa/untitled.png"),
            Path("dump/notebook04/2023/20230717-Hello_world.md"),
            Path("dump/notebook04/2023/20230717-Some_tasks.md"),
            Path("dump/notebook05/2023/20230722-Same_name.md"),
            Path("dump/notebook05/2023/20230722-Same_name_1.md"),
            Path("dump/notebook05/2023/20230722-Same_name_2.md"),
            Path("dump/notebook06/2023/20230712-Fa_fa_fa.md"),
            Path("dump/notebook06/_resources/2023/20230712-Fa_fa_fa/rckrll.png"),
            Path("dump/notebook06/_resources/2023/20230712-Fa_fa_fa/rckrlltoo.png"),
        ]

    @pytest.mark.parametrize(
        ["timezone", "expected_path", "expected_metadata"],
        [
            (
                TIMEZONE.UTC,
                "20230709/184204-The_title.md",
                "- Created: 2023-07-09T18:42:04+00:00\n- Updated: 2023-07-09T18:43:22+00:00",
            ),
            (
                TIMEZONE.LOCAL,
                "20230709/214204-The_title.md",
                "- Created: 2023-07-09T21:42:04+03:00\n- Updated: 2023-07-09T21:43:22+03:00",
            ),
        ],
    )
    def test_timezone(self, tmp_path, timezone, expected_path, expected_metadata):
        path = (enex_root / "notebook01.enex").absolute()
        args = [
            "--output-root",
            str(tmp_path),
            "--note-path-template",
            "{created:%Y%m%d}/{created:%H%M%S}-{title}.md",
            "--timezone",
            timezone,
            str(path),
        ]
        result = CliRunner().invoke(app, args)
        assert result.exit_code == 0
        assert result.output == ""

        generated_files = _list_all_files(tmp_path)
        assert generated_files == [Path(expected_path)]
        assert expected_metadata in generated_files[0].read_text()
