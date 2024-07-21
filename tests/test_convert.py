import datetime
import textwrap
from pathlib import Path
from typing import List, Tuple, Union

import pytest

from enex2md.convert import TIMEZONE, Converter, EnexParser, FileSystemSink, ParsedNote

enex_root = Path(__file__).parent / "enex"


class TestEnexParser:
    def test_extract_elements(self):
        parser = EnexParser()
        path = (enex_root / "notebook01.enex").absolute()
        elements = parser.extract_note_elements(path)
        first = next(elements)
        assert list(elements) == []
        assert first.tag == "note"
        assert first.find("title").text == "The title"
        assert first.find("note-attributes/author").text == "John Doe"
        assert "banana" in first.find("content").text

    def test_extract_notes(self):
        parser = EnexParser()
        path = (enex_root / "notebook04.enex").absolute()
        notes = parser.extract_notes(path)
        first = next(notes)
        second = next(notes)
        assert list(notes) == []

        assert first.title == "Some tasks"
        assert "Some things to do" in first.content
        assert first.created == datetime.datetime(2023, 7, 17, 19, 16, 38, tzinfo=datetime.timezone.utc)
        assert first.updated == datetime.datetime(2023, 7, 17, 19, 19, 26, tzinfo=datetime.timezone.utc)
        assert first.author == "John Doe"
        assert first.source_url is None
        assert first.attachments == []

        assert second.title == "Hello world"
        assert "Hello world in Python" in second.content
        assert second.created == datetime.datetime(2023, 7, 17, 19, 14, 28, tzinfo=datetime.timezone.utc)
        assert second.updated == datetime.datetime(2023, 7, 17, 19, 19, 43, tzinfo=datetime.timezone.utc)
        assert second.author == "John Doe"
        assert second.source_url is None
        assert second.attachments == []

    def test_extract_notes_with_attachments(self):
        parser = EnexParser()
        path = (enex_root / "notebook03.enex").absolute()
        notes = parser.extract_notes(path)
        first = next(notes)
        assert list(notes) == []

        assert first.title == "Fa fa fa"
        assert "lo lo lo" in first.content
        assert first.author == "John Doe"
        assert len(first.attachments) == 1
        attachment = first.attachments[0]
        assert attachment.file_name == "rckrll.png"
        assert attachment.mime_type == "image/png"
        assert attachment.width == 64
        assert attachment.height == 32


def _list_all_files(root, with_size: bool = False) -> List[Union[Path, Tuple[Path, int]]]:
    files = (p for p in root.glob("**/*") if p.is_file())
    if with_size:
        return sorted((p.relative_to(root), p.stat().st_size) for p in files)
    else:
        return sorted(p.relative_to(root) for p in files)


class TestFileSystemSink:
    @pytest.fixture(autouse=True)
    def chdir_tmp_path(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

    @pytest.fixture
    def note(self) -> ParsedNote:
        return ParsedNote(
            title="Hello world",
            content="Hello, world!",
            tags=[],
            created=datetime.datetime(2023, 7, 24, 12, 34, 56, tzinfo=datetime.timezone.utc),
        )

    @pytest.mark.parametrize(
        ["allow_spaces_in_filenames", "unsafe_replacer", "expected"],
        [
            (False, "", "2023/Thetitleofthethisnote123.md"),
            (True, "", "2023/The title of thethis note 123.md"),
            (False, "-", "2023/The-title-of-the-this-note-123.md"),
            (False, "_", "2023/The_title_of_the_this_note_123.md"),
            (True, "_", "2023/The title_ _of the_this note_ 123.md"),
        ],
    )
    def test_safe_name_handling(self, tmp_path, allow_spaces_in_filenames, unsafe_replacer, expected):
        sink = FileSystemSink(
            root=tmp_path,
            note_path_template="{created:%Y}/{title}.md",
            allow_spaces_in_filenames=allow_spaces_in_filenames,
            unsafe_replacer=unsafe_replacer,
        )
        note = ParsedNote(
            title="The title, (of the/this note)! 123?",
            content="foobar",
            tags=[],
            created=datetime.datetime(2023, 7, 24, 12, 34, 56),
        )

        sink.store_note(note, lines=["foobar"])
        assert _list_all_files(tmp_path) == [Path(expected)]

    def test_filename_max_length(self, tmp_path):
        sink = FileSystemSink(
            root=tmp_path,
            note_path_template="{created:%Y}/{created:%Y-%m-%d}-{title}.md",
            max_filename_length=16,
        )
        note = ParsedNote(
            title="The title, (of the/this note)! 123?",
            content="foobar",
            tags=[],
            created=datetime.datetime(2023, 7, 24, 12, 34, 56),
        )

        sink.store_note(note, lines=["foobar"])
        assert _list_all_files(tmp_path) == [Path("2023/2023-07-24-The_title_of_the.md")]

    def test_root_condition_require_empty(self, tmp_path):
        # Does not exist (yet)
        _ = FileSystemSink(root=tmp_path / "foo", root_condition=FileSystemSink.ROOT_CONDITION.REQUIRE_EMPTY)

        # Exist, but  empty
        (tmp_path / "foo").mkdir()
        _ = FileSystemSink(root=tmp_path / "foo", root_condition=FileSystemSink.ROOT_CONDITION.REQUIRE_EMPTY)

        # Not empty
        (tmp_path / "foo" / "hello.txt").touch()
        with pytest.raises(AssertionError, match="Must be an empty folder but found 1 item"):
            _ = FileSystemSink(root=tmp_path / "foo", root_condition=FileSystemSink.ROOT_CONDITION.REQUIRE_EMPTY)

    def test_on_existing_file_bump(self, tmp_path, note):
        (tmp_path / "Hello_world.md").touch()
        (tmp_path / "Hello_world_1.md").touch()
        assert _list_all_files(tmp_path) == [
            Path("Hello_world.md"),
            Path("Hello_world_1.md"),
        ]

        sink = FileSystemSink(
            root=tmp_path,
            note_path_template="{title}.md",
            on_existing_file=FileSystemSink.ON_EXISTING_FILE.BUMP,
        )
        sink.store_note(note, lines=note.content.split())
        assert _list_all_files(tmp_path) == [
            Path("Hello_world.md"),
            Path("Hello_world_1.md"),
            Path("Hello_world_2.md"),
        ]

    def test_on_existing_file_fail(self, tmp_path, note):
        (tmp_path / "Hello_world.md").touch()
        (tmp_path / "Hello_world_1.md").touch()

        sink = FileSystemSink(
            root=tmp_path,
            note_path_template="{title}.md",
            on_existing_file=FileSystemSink.ON_EXISTING_FILE.FAIL,
        )
        with pytest.raises(FileExistsError, match=r"Already exists.*Hello_world\.md"):
            sink.store_note(note, lines=note.content.split())

    def test_on_existing_file_overwrite(self, tmp_path, note):
        (tmp_path / "Hello_world.md").touch()
        (tmp_path / "Hello_world_1.md").touch()
        assert _list_all_files(tmp_path) == [
            Path("Hello_world.md"),
            Path("Hello_world_1.md"),
        ]

        sink = FileSystemSink(
            root=tmp_path,
            note_path_template="{title}.md",
            on_existing_file=FileSystemSink.ON_EXISTING_FILE.OVERWRITE,
        )
        sink.store_note(note, lines=note.content.split())
        assert _list_all_files(tmp_path, with_size=True) == [
            (Path("Hello_world.md"), pytest.approx(14, abs=5)),
            (Path("Hello_world_1.md"), 0),
        ]

    def test_on_existing_file_warn(self, tmp_path, note, caplog):
        (tmp_path / "Hello_world.md").touch()
        (tmp_path / "Hello_world_1.md").touch()
        assert _list_all_files(tmp_path) == [
            Path("Hello_world.md"),
            Path("Hello_world_1.md"),
        ]

        sink = FileSystemSink(
            root=tmp_path,
            note_path_template="{title}.md",
            on_existing_file=FileSystemSink.ON_EXISTING_FILE.WARN,
        )

        assert caplog.text == ""

        sink.store_note(note, lines=note.content.split())
        assert _list_all_files(tmp_path, with_size=True) == [
            (Path("Hello_world.md"), pytest.approx(14, abs=5)),
            (Path("Hello_world_1.md"), 0),
        ]

        assert "Overwriting existing file" in caplog.text

    @pytest.mark.parametrize(
        ["timezone", "expected"],
        [
            (TIMEZONE.UTC, "20230724/123456-Hello_world.md"),
            (TIMEZONE.LOCAL, "20230724/153456-Hello_world.md"),
        ],
    )
    def test_timezone(self, tmp_path, note, timezone, expected):
        sink = FileSystemSink(
            root=tmp_path,
            note_path_template="{created:%Y%m%d}/{created:%H%M%S}-{title}.md",
            timezone=timezone,
        )
        sink.store_note(note, lines=note.content.split())
        assert _list_all_files(tmp_path) == [
            Path(expected),
        ]


class TestConverter:
    @pytest.fixture(autouse=True)
    def chdir_tmp_path(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

    def test_basic(self, tmp_path):
        path = (enex_root / "notebook01.enex").absolute()
        converter = Converter()
        converter.convert(enex=path, sink=FileSystemSink())

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

    def test_frontmatter(self, tmp_path):
        path = (enex_root / "notebook01.enex").absolute()
        converter = Converter(front_matter=True)
        converter.convert(enex=path, sink=FileSystemSink())

        generated_files = _list_all_files(tmp_path)
        assert len(generated_files) == 1
        md_path = generated_files[0]
        assert md_path.name == "The_title.md"
        md_content = md_path.read_text()
        assert md_content == textwrap.dedent(
            """\
            ---
            title: The title
            author: John Doe
            created: 2023-07-09T18:42:04+00:00
            updated: 2023-07-09T18:43:22+00:00
            ---


            # The title

            Things to buy:
              * apple
              * banana
              * chocolate
            """
        )

    def test_add_origin(self, tmp_path):
        path = (enex_root / "notebook01.enex").absolute()
        converter = Converter(front_matter=True, add_origin=True)
        converter.convert(enex=path, sink=FileSystemSink())

        generated_files = _list_all_files(tmp_path)
        assert len(generated_files) == 1
        md_path = generated_files[0]
        assert md_path.name == "The_title.md"
        md_content = md_path.read_text()
        expected = textwrap.dedent(
            """\
            ---
            title: The title
            author: John Doe
            created: 2023-07-09T18:42:04+00:00
            updated: 2023-07-09T18:43:22+00:00
            origin: Evernote notebook 'notebook01'
            ---
            """
        )
        assert md_content.startswith(expected)

    def test_nested_lists(self, tmp_path):
        path = (enex_root / "notebook02.enex").absolute()
        converter = Converter()
        converter.convert(enex=path, sink=FileSystemSink())

        generated_files = _list_all_files(tmp_path)
        assert len(generated_files) == 1
        md_path = generated_files[0]
        assert md_path.name == "Nested_lists.md"
        md_content = md_path.read_text()
        assert md_content == textwrap.dedent(
            """\
            # Nested lists

            ## Note metadata

            - Title: Nested lists
            - Author: John Doe
            - Created: 2023-07-09T20:46:28+00:00
            - Updated: 2023-07-09T20:47:19+00:00

            ## Note Content

            Let's nest some lists:
              * apple
                * red
                * green
                  * classic!
                * yellow
              * banana
                * yellow
                  * brown-black: avoid!
              * chocolate:
                * white
                * brown
                * black
            """
        )

    @pytest.mark.parametrize(
        ["enex", "expected_filename"],
        [
            ("notebook03.enex", "rckrll.png"),
            ("notebook03-2.enex", "rckrll.png"),
            ("notebook03-3.enex", "untitled.png"),
        ],
    )
    def test_attachment_default_paths(self, tmp_path, enex, expected_filename):
        path = (enex_root / enex).absolute()
        converter = Converter()
        converter.convert(enex=path, sink=FileSystemSink())

        generated_files = _list_all_files(tmp_path)
        assert len(generated_files) == 2
        (md_path,) = [p for p in generated_files if p.suffix == ".md"]
        (png_path,) = [p for p in generated_files if p.suffix == ".png"]
        assert md_path.name == "Fa_fa_fa.md"
        md_content = md_path.read_text()
        assert md_content == textwrap.dedent(
            f"""\
            # Fa fa fa

            ## Note metadata

            - Title: Fa fa fa
            - Author: John Doe
            - Created: 2023-07-12T20:16:08+00:00
            - Updated: 2023-07-12T20:18:38+00:00

            ## Note Content

            lo lo lo

            ![{expected_filename}](Fa_fa_fa_attachments/{expected_filename})
            la la la
            """
        )
        assert png_path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    def test_multiple_attachments(self, tmp_path):
        path = (enex_root / "notebook06.enex").absolute()
        converter = Converter()
        converter.convert(enex=path, sink=FileSystemSink())

        generated_files = _list_all_files(tmp_path)
        assert len(generated_files) == 3
        (md_path,) = [p for p in generated_files if p.suffix == ".md"]
        png_paths = [p for p in generated_files if p.suffix == ".png"]
        assert md_path.name == "Fa_fa_fa.md"

        assert set(p.name for p in tmp_path.glob("output/*/notebook06/*")) == {
            "Fa_fa_fa.md",
            "Fa_fa_fa_attachments",
        }

        md_content = md_path.read_text()
        assert md_content == textwrap.dedent(
            """\
            # Fa fa fa

            ## Note metadata

            - Title: Fa fa fa
            - Author: John Doe
            - Created: 2023-07-12T20:16:08+00:00
            - Updated: 2023-07-12T20:18:38+00:00

            ## Note Content

            lo lo lo

            ![rckrll.png](Fa_fa_fa_attachments/rckrll.png)
            la la la

            ![rckrlltoo.png](Fa_fa_fa_attachments/rckrlltoo.png)
            bye
            """
        )
        for png_path in png_paths:
            assert png_path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    def test_attachment_collision(self, tmp_path):
        converter = Converter()
        sink = FileSystemSink(
            root=tmp_path,
            note_path_template="{title}.md",
            attachments_path_template="attachments",
        )
        converter.convert(enex=(enex_root / "notebook03.enex").absolute(), sink=sink)
        converter.convert(enex=(enex_root / "notebook03-2.enex").absolute(), sink=sink)

        generated_files = _list_all_files(tmp_path)
        assert generated_files == [
            Path("Fa_fa_fa.md"),
            Path("Fa_fa_fa_1.md"),
            Path("attachments/rckrll.png"),
            Path("attachments/rckrll_1.png"),
        ]

    def test_attachment_space_encoding(self, tmp_path):
        converter = Converter()
        sink = FileSystemSink(
            root=tmp_path,
            note_path_template="{title}.md",
            attachments_path_template="{title} attachments",
            allow_spaces_in_filenames=True,
        )
        converter.convert(enex=(enex_root / "notebook03.enex").absolute(), sink=sink)

        generated_files = _list_all_files(tmp_path)
        assert generated_files == [
            Path("Fa fa fa attachments/rckrll.png"),
            Path("Fa fa fa.md"),
        ]
        md_content = Path("Fa fa fa.md").read_text().split("\n")
        assert "![rckrll.png](Fa%20fa%20fa%20attachments/rckrll.png)" in md_content

    def test_custom_paths_basic(self, tmp_path):
        path = (enex_root / "notebook01.enex").absolute()
        converter = Converter()
        converter.convert(
            enex=path,
            sink=FileSystemSink(
                root=tmp_path / "go" / "here",
                note_path_template="{enex}/{created:%Y}/{created:%Y%m%d}-{title}.md",
            ),
        )

        generated_files = _list_all_files(tmp_path)
        assert generated_files == [
            Path("go/here/notebook01/2023/20230709-The_title.md"),
        ]
        md_path = generated_files[0]
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

    def test_custom_paths_auto_attachments(self, tmp_path):
        path = (enex_root / "notebook03.enex").absolute()
        converter = Converter()
        converter.convert(
            enex=path,
            sink=FileSystemSink(
                root="dump",
                note_path_template="{enex}/{created:%Y}/{created:%Y%m%d}-{title}.md",
            ),
        )

        generated_files = _list_all_files(tmp_path)
        assert generated_files == [
            Path("dump/notebook03/2023/20230712-Fa_fa_fa.md"),
            Path("dump/notebook03/2023/20230712-Fa_fa_fa_attachments/rckrll.png"),
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

            ![rckrll.png](20230712-Fa_fa_fa_attachments/rckrll.png)
            la la la
            """
        )
        assert generated_files[1].read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    def test_custom_paths(self, tmp_path):
        path = (enex_root / "notebook03.enex").absolute()
        converter = Converter()
        converter.convert(
            enex=path,
            sink=FileSystemSink(
                root="dump",
                note_path_template="{enex}/{created:%Y}/{created:%Y%m%d}-{title}.md",
                attachments_path_template="{enex}/_resources/{created:%Y}/{created:%Y%m%d}-{title}",
            ),
        )

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

    def test_same_title(self, tmp_path):
        path = (enex_root / "notebook05.enex").absolute()
        converter = Converter()
        converter.convert(enex=path, sink=FileSystemSink(note_path_template="{enex}/{created:%Y%m}/{title}.md"))

        generated_files = _list_all_files(tmp_path)
        assert generated_files == [
            Path("output/notebook05/202307/Same_name.md"),
            Path("output/notebook05/202307/Same_name_1.md"),
            Path("output/notebook05/202307/Same_name_2.md"),
        ]

    def test_same_title_preexisting_files(self, tmp_path):
        (tmp_path / "Same_name.md").touch()
        (tmp_path / "Same_name_1.md").touch()
        (tmp_path / "Same_name_3.md").touch()
        path = (enex_root / "notebook05.enex").absolute()
        converter = Converter()
        converter.convert(enex=path, sink=FileSystemSink(root=tmp_path, note_path_template="{title}.md"))

        assert _list_all_files(tmp_path, with_size=True) == [
            (Path("Same_name.md"), 0),
            (Path("Same_name_1.md"), 0),
            (Path("Same_name_2.md"), pytest.approx(210, abs=20)),
            (Path("Same_name_3.md"), 0),
            (Path("Same_name_4.md"), pytest.approx(210, abs=20)),
            (Path("Same_name_5.md"), pytest.approx(210, abs=20)),
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
        converter = Converter(timezone=timezone)
        sink = FileSystemSink(
            root=tmp_path,
            note_path_template="{created:%Y%m%d}/{created:%H%M%S}-{title}.md",
            timezone=timezone,
        )
        converter.convert(enex=path, sink=sink)

        generated_files = _list_all_files(tmp_path)

        assert generated_files == [Path(expected_path)]
        assert expected_metadata in generated_files[0].read_text()

    def test_enex_unnumbered(self, tmp_path):
        converter = Converter()
        sink = FileSystemSink(
            root=tmp_path,
            note_path_template="{enex_unnumbered}/{title}.md",
            attachments_path_template="{enex_unnumbered}/attachments",
        )
        converter.convert(enex=(enex_root / "notebook03.enex").absolute(), sink=sink)
        converter.convert(enex=(enex_root / "notebook03-3.enex").absolute(), sink=sink)

        generated_files = _list_all_files(tmp_path)
        assert generated_files == [
            Path("notebook03/Fa_fa_fa.md"),
            Path("notebook03/Fa_fa_fa_1.md"),
            Path("notebook03/attachments/rckrll.png"),
            Path("notebook03/attachments/untitled.png"),
        ]

    def test_nested_list_handling(self, tmp_path):
        note = ParsedNote(
            title="test",
            content=textwrap.dedent("""
                <div>Operation modes</div>
                <div>
                <ul>
                <li>CSS + HTML files<br/></li>
                <li style="list-style: none">
                <ul>
                <li>match selectors</li>
                <li>report unused</li>
                </ul>
                </li>
                <li>CSS + source files</li>
                <li style="list-style: none">
                <ul>
                <li>extract ids and classes</li>
                <li style="list-style: none">
                <ul>
                <li>better: do grep on strings only</li>
                </ul>
                </li>
                <li>resolve unused ids</li>
                </ul>
                </li>
                <li>CSS files + HTML files + source files</li>
                <li style="list-style: none">
                <ul>
                <li>phase 1</li>
                <li>report selectors</li>
                <li style="list-style: none">
                <ul>
                <li>unused</li>
                <li><br/></li>
                </ul>
                </li>
                </ul>
                </li>
                </ul>
            """),
            tags=[],
            created=datetime.datetime(2024, 7, 21),
        )
        converter = Converter()
        sink = FileSystemSink(
            root=tmp_path,
            note_path_template="{title}.md",
        )
        converter.export_note(note, sink=sink)

        md = (tmp_path / "test.md").read_text()
        md = md.partition("Operation modes")[-1]
        expected = textwrap.dedent("""
          * CSS + HTML files
            * match selectors
            * report unused
          * CSS + source files
            * extract ids and classes
              * better: do grep on strings only
            * resolve unused ids
          * CSS files + HTML files + source files
            * phase 1
            * report selectors
              * unused
        """)
        expected = textwrap.indent(expected, prefix="  ")
        assert md == expected

    def test_ol_list_handling(self, tmp_path):
        note = ParsedNote(
            title="test",
            content=textwrap.dedent("""
                <div><br/></div>
                <ol>
                <li><div>Apple</div></li>
                <li><div>Banana</div></li>
                <li><div><br/></div></li>
                </ol>
            """),
            tags=[],
            created=datetime.datetime(2024, 7, 21),
        )
        converter = Converter()
        sink = FileSystemSink(
            root=tmp_path,
            note_path_template="{title}.md",
        )
        converter.export_note(note, sink=sink)

        md = (tmp_path / "test.md").read_text()
        expected = "\n  1. Apple\n  2. Banana\n"
        assert expected in md

    def test_trailing_list_item(self, tmp_path):
        note = ParsedNote(
            title="test",
            content=textwrap.dedent("""
                <ul>
                <li><div>Overtones</div></li>
                <li><div>Chromatics</div></li>
                <li><div><br/></div></li>
                </ul>
                <div>bye</div>
            """),
            tags=[],
            created=datetime.datetime(2024, 7, 21),
        )
        converter = Converter()
        sink = FileSystemSink(
            root=tmp_path,
            note_path_template="{title}.md",
        )
        converter.export_note(note, sink=sink)

        md = (tmp_path / "test.md").read_text()
        expected = "\n  * Overtones\n  * Chromatics\n\nbye\n"
        assert md.endswith(expected)
