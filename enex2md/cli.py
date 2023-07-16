"""Command Line Interface (CLI) for enex2md project."""

import logging

import click

from enex2md.convert import Converter, StdOutSink, FileSystemSink
# from enex2md import __version__

_log = logging.getLogger(__name__)

@click.command()
@click.option('--disk', is_flag=True, help='output to disk instead of stdout (default)')
@click.option('--front-matter', is_flag=True, help='Put note metadata in a "frontmatter" block.')
@click.argument('input_file')
def app(disk, front_matter, input_file):
    """ Run the converter. Requires the input_file (data.enex) to be processed as the first argument. """
    logging.basicConfig(level=logging.INFO)
    if disk:
        sink = FileSystemSink.legacy_root_from_enex(input_file)
    else:
        sink = StdOutSink()
    logging.info(f"Processing input file: {input_file}, using {sink}.")

    converter = Converter(enex_file=input_file, sink=sink, front_matter=front_matter)
    converter.convert()


if __name__ == '__main__':
    app()
