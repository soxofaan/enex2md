# enex2md

[![license](https://img.shields.io/github/license/soxofaan/enex2md.svg?style=flat)](https://github.com/soxofaan/enex2md/blob/master/LICENSE)
[![Unit tests](https://github.com/soxofaan/enex2md/actions/workflows/unittest.yml/badge.svg?branch=main)](https://github.com/soxofaan/enex2md/actions/workflows/unittest.yml)


Enex2md is a Python based command-line utility to convert Evernote export files (`*.enex`) to [GitHub Flavored Markdown](https://github.github.com/gfm/).


> **Note**
> This is a friendly fork of [@janik6n's original enex2md tool](https://github.com/janik6n/enex2md) (which is now in archive mode).
> At the moment I'm just interested in massaging it to support my own needs:
> migrating as cleanly as possible from Evernote to Obsidian.
> I'll probably break backward compatibility with the original project at some point.


## Features

In addition to the note content itself, the note metadata is included in the resulting Markdown. The ENEX-bundle may contain one or more notes.

Within the note content, the following features are supported:

- [x] Strong and emphasis text styles.
- [x] Ordered (i.e. numbered) and unordered lists
- [x] Tables created within Evernote are converted to [GFM Tables](https://github.github.com/gfm/#table)
- [x] Tasks are converted to [GFM Task list items](https://github.github.com/gfm/#task-list-item)
- [x] Images and other attachments
- [x] Code blocks
- [x] Subsequent empty lines are compressed to one.

The HTML in ENEX files is *somewhat interesting*, thus some *magic is used to massage the data to functioning feature-rich Markdown*. The Magic Book used here has not yet been fully written, so there might be some unfortunate side effects.

See [Changelog](https://github.com/soxofaan/enex2md/blob/master/CHANGELOG.md) for more details.



## Development/Installation

> **Note**
> As always, it is strongly recommended to workt in some kind of virtual environment

Clone the [repository](https://github.com/soxofaan/enex2md) to your local machine, and install the project in your virtual env:

```shell
pip install -e .[dev]
```

## Usage

Convert a given ENEX file:

```shell
enex2md notebook.enex
```

The output is written to `STDOUT` by default. If you want to write to disk instead, add a flag `--disk` to the command. This option will create a directory based on run time timestamp, and place individual files under that.

*Please note, that on STDOUT output option attachments (including images) are not processed!*
