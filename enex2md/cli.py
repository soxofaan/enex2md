"""Command Line Interface (CLI) for enex2md project."""

import logging
from pathlib import Path
from typing import Iterable, Iterator

import click

from enex2md.convert import Converter, EnexParser, FileSystemSink, StdOutSink

_log = logging.getLogger(__name__)


@click.command()
@click.option("--disk", is_flag=True, help="output to disk instead of stdout (default)")
@click.option("--front-matter", is_flag=True, help='Put note metadata in a "frontmatter" block.')
@click.option(
    "--output-root",
    default=FileSystemSink.DEFAULT_OUTPUT_ROOT,
    help="Output root folder",
    type=click.Path(exists=False, file_okay=False, dir_okay=True),
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
@click.argument(
    "enex_sources",
    nargs=-1,
    required=True,
    type=click.Path(exists=True, file_okay=True, dir_okay=True, readable=True, path_type=Path),
)
def app(disk, front_matter, output_root, enex_sources, note_path_template, attachments_path_template):
    logging.basicConfig(level=logging.INFO)
    # TODO: get rid of this non-useful --disk option?
    if disk:
        sink = FileSystemSink(
            root=output_root,
            note_path_template=note_path_template,
            attachments_path_template=attachments_path_template,
        )
    else:
        sink = StdOutSink()
    _log.info(f"Using {sink=}")

    parser = EnexParser()
    converter = Converter(front_matter=front_matter)

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


if __name__ == '__main__':
    app()
