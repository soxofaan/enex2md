import textwrap
from pathlib import Path
from enex2md.convert import Converter

enex_root = Path(__file__).parent / "enex"


def test_basic(tmp_path, monkeypatch):
    path = (enex_root / "notebook01.enex").absolute()
    monkeypatch.chdir(tmp_path)
    converter = Converter(enex_file=str(path), write_to_disk=True)
    converter.convert()

    generated = list(tmp_path.glob("**/*.md"))
    assert len(generated) == 1
    md = generated[0].read_text()
    assert md == textwrap.dedent(
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
    converter = Converter(enex_file=str(path), write_to_disk=True, front_matter=True)
    converter.convert()

    generated = list(tmp_path.glob("**/*.md"))
    assert len(generated) == 1
    md = generated[0].read_text()
    assert md == textwrap.dedent(
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
    converter = Converter(enex_file=str(path), write_to_disk=True)
    converter.convert()

    generated = list(tmp_path.glob("**/*.md"))
    assert len(generated) == 1
    md = generated[0].read_text()
    assert md == textwrap.dedent(
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
