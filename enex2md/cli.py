"""Command Line Interface (CLI) for enex2md project."""

import logging

import click

from enex2md.convert import Converter, FileSystemSink, StdOutSink

# from enex2md import __version__

_log = logging.getLogger(__name__)

@click.command()
@click.option("--disk", is_flag=True, help="output to disk instead of stdout (default)")
@click.option("--front-matter", is_flag=True, help='Put note metadata in a "frontmatter" block.')
@click.option("--output-root", default=FileSystemSink.DEFAULT_OUTPUT_ROOT, help="Output root folder")
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
@click.argument("input_file")
def app(disk, front_matter, output_root, input_file, note_path_template, attachments_path_template):
    """ Run the converter. Requires the input_file (data.enex) to be processed as the first argument. """
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
    # TODO: support converting multiple files, or walking folders
    logging.info(f"Processing input file: {input_file}, using {sink}.")

    converter = Converter(front_matter=front_matter)
    converter.convert(enex=input_file, sink=sink)


if __name__ == '__main__':
    app()
