import textwrap
from pathlib import Path
from enex2md.convert import Converter, FileSystemSink, EnexParser
import datetime


enex_root = Path(__file__).parent / "enex"


def test_basic(tmp_path, monkeypatch):
    path = (enex_root / "notebook01.enex").absolute()
    monkeypatch.chdir(tmp_path)
    converter = Converter(enex_file=str(path), sink=FileSystemSink.legacy_root_from_enex(path))
    converter.convert()

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


def test_frontmatter(tmp_path, monkeypatch):
    path = (enex_root / "notebook01.enex").absolute()
    monkeypatch.chdir(tmp_path)
    converter = Converter(enex_file=str(path), sink=FileSystemSink.legacy_root_from_enex(path), front_matter=True)
    converter.convert()

    generated_files = [p.relative_to(tmp_path) for p in tmp_path.glob("**/*") if p.is_file()]
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


def test_nested_lists(tmp_path, monkeypatch):
    path = (enex_root / "notebook02.enex").absolute()
    monkeypatch.chdir(tmp_path)
    converter = Converter(enex_file=str(path), sink=FileSystemSink.legacy_root_from_enex(path))
    converter.convert()

    generated_files = [p.relative_to(tmp_path) for p in tmp_path.glob("**/*") if p.is_file()]
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


def test_attachment(tmp_path, monkeypatch):
    path = (enex_root / "notebook03.enex").absolute()
    monkeypatch.chdir(tmp_path)
    converter = Converter(enex_file=str(path), sink=FileSystemSink.legacy_root_from_enex(path))
    converter.convert()

    generated_files = [p.relative_to(tmp_path) for p in tmp_path.glob("**/*") if p.is_file()]
    assert len(generated_files) == 2
    (md_path,) = [p for p in generated_files if p.suffix == ".md"]
    (png_path,) = [p for p in generated_files if p.suffix == ".png"]
    assert md_path.name == "Fa_fa_fa.md"
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
        """
    )
    assert png_path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


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
