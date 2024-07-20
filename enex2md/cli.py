"""Command Line Interface (CLI) for enex2md project."""

import logging
from pathlib import Path
from typing import Iterable, Iterator

import click

from enex2md.convert import TIMEZONE, Converter, EnexParser, FileSystemSink, StdOutSink

_log = logging.getLogger(__name__)


@click.command()
@click.option("--front-matter", is_flag=True, help='Put note metadata in a "frontmatter" block.')
@click.option(
    "--output-root",
    default=FileSystemSink.DEFAULT_OUTPUT_ROOT,
    help="Output root folder",
    type=click.Path(exists=False, file_okay=False, dir_okay=True, allow_dash=True),
)
@click.option(
    "--note-path-template",
    help="Path template for output notes.",
    default=FileSystemSink.DEFAULT_NOTE_PATH_TEMPLATE,
)
@click.option(
    "--attachments-path-template",
    help="Path template for attachment folder.",
    default=FileSystemSink.DEFAULT_ATTACHMENTS_PATH_TEMPLATE,
)
@click.option(
    "--allow-spaces-in-filenames",
    is_flag=True,
    default=False,
    help="Allow spaces in output file names.",
)
@click.option(
    "--unsafe-replacer",
    default="_",
    help="Replace character for unsafe characters in file names.",
    type=click.Choice(["", "_", "-"]),
)
@click.option(
    "--root-condition",
    default=FileSystemSink.ROOT_CONDITION.LEAVE_AS_IS,
    help="Condition the root folder should be in: must be empty, or it doesn't matter?",
    type=click.Choice([FileSystemSink.ROOT_CONDITION.LEAVE_AS_IS, FileSystemSink.ROOT_CONDITION.REQUIRE_EMPTY]),
)
@click.option(
    "--on-existing-file",
    help="what to do when a target file already exists: e.g. fail with exception, bump filename with an autoincrement counter until a new file name is found, ...",
    default=FileSystemSink.ON_EXISTING_FILE.BUMP,
    type=click.Choice(
        [
            FileSystemSink.ON_EXISTING_FILE.BUMP,
            FileSystemSink.ON_EXISTING_FILE.FAIL,
            FileSystemSink.ON_EXISTING_FILE.OVERWRITE,
            FileSystemSink.ON_EXISTING_FILE.WARN,
        ]
    ),
)
@click.option(
    "--timezone",
    help="What timezone to work in when formatting dates",
    default=TIMEZONE.UTC,
    type=click.Choice([TIMEZONE.UTC, TIMEZONE.LOCAL]),
)
@click.argument(
    "enex_sources",
    nargs=-1,
    required=True,
    type=click.Path(exists=True, file_okay=True, dir_okay=True, readable=True, path_type=Path),
)
def app(
    front_matter,
    output_root,
    enex_sources,
    note_path_template,
    attachments_path_template,
    allow_spaces_in_filenames,
    unsafe_replacer,
    root_condition,
    on_existing_file,
    timezone,
):
    logging.basicConfig(level=logging.INFO)

    if output_root == "-":
        sink = StdOutSink()
    else:
        sink = FileSystemSink(
            root=output_root,
            note_path_template=note_path_template,
            attachments_path_template=attachments_path_template,
            allow_spaces_in_filenames=allow_spaces_in_filenames,
            unsafe_replacer=unsafe_replacer,
            root_condition=root_condition,
            on_existing_file=on_existing_file,
            timezone=timezone,
        )
    _log.info(f"Using {sink=}")

    parser = EnexParser()
    converter = Converter(front_matter=front_matter, timezone=timezone)

    for enex_path in collect_enex_paths(enex_sources):
        _log.info(f"Processing input file {enex_path}.")
        converter.convert(enex=enex_path, sink=sink, parser=parser)

    _log.info(f"Stats: {parser.stats=} {converter.stats=} {sink.stats=}")


def collect_enex_paths(enex_sources: Iterable[Path]) -> Iterator[Path]:
    for enex_source in enex_sources:
        if enex_source.is_file():
            yield enex_source
        elif enex_source.is_dir():
            for p in enex_source.glob("*.enex"):
                if p.is_file():
                    yield p
        else:
            raise ValueError(enex_source)


if __name__ == "__main__":
    app()
