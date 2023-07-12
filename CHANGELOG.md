# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [Unreleased]

### Added

- Add option to add note metadata in "frontmatter" style instead of Markdown section
- Started with basic test suite
- Added GitHub actions for running test suite and linting checks

### Changed

- Use `logging` instead of basic `print`, for more library-like behavior
- Use ISO format for created/updated timestamp instead of non-standard custom format
- Migrated to `pyproject.toml`

### Removed

- Dropped support for Python 3.7 or lower

### Fixed

- Fixed indentation issue with nested lists


## [0.4.2] - 2019-11-18

### Added

### Changed

### Removed

### Fixed

- Handle missing `updated` element.


## [0.4.1] - 2019-11-18

### Added

### Changed

### Removed

### Fixed

- Skip the attachment, if xml element for the name is missing (`resource/resource-attributes/file-name`).


## [0.4.0] - 2019-11-16

### Added

- Version pinning for dependencies.

### Changed

### Removed

### Fixed

- Version pinning of dependencies fixes issues with preinstalled too old dependencies.


## [0.3.3, 0.3.4] - 2019-08-30

### Added

### Changed

### Removed

### Fixed

- Handle missing Author without crashing.


## [0.3.2] - 2019-02-10

### Added

### Changed

### Removed

### Fixed

- Code blocks now preserve formatting, as if they were <pre> elements in enex!
- Removing consecutive empty lines works now more robustly.


## [0.3.1] - 2019-02-09

### Added

### Changed

### Removed

### Fixed

- If there are no attachments for note, do not create subdirectory.


## [0.3.0] - 2019-02-09

### Added

- Attachments, including images, are now handled. When `--disk` is selected as output, attachments are stored in note specific subdirectory, and they are referenced on the note in corrent places.

### Changed

### Removed

### Fixed


## [0.2.0] - 2019-02-09

### Added

### Changed

- Output structure on disk has been changed. A new directory level was added based on the input name. This was done in preparation to handle attachments and possible duplicate filenames.

### Removed

### Fixed

- Strong and emphasis text styles should now be preserved.
- Duplicate filenames (identical note title) are now handled correctly.


## [0.1.1] - 2019-02-05

### Added

### Changed

- Subsequent empty lines are compressed to one.

### Removed

### Fixed

- Lists are converted correctly. An empty line is forced before list items.
- Tasks are converted correctly to [GFM Task list items](https://github.github.com/gfm/#task-list-item).
- Tables created within Evernote are converted to [GFM Tables](https://github.github.com/gfm/#table).
