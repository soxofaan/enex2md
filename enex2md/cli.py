"""Command Line Interface (CLI) for enex2md project."""

# import os
import sys
import logging

import click

from enex2md.convert import Converter
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
        output_option = 'DISK'
    else:
        output_option = 'STDOUT'
    logging.info(f"Processing input file: {input_file}, writing output to {output_option}.")
    # print(__version__)

    converter = Converter(input_file, disk, front_matter=front_matter)
    converter.convert()


if __name__ == '__main__':
    app()
