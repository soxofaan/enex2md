import base64
import collections
import dataclasses
import datetime
import hashlib
import itertools
import logging
import os.path
import re
import xml.etree.ElementTree
from pathlib import Path
from typing import Callable, Dict, Iterable, Iterator, List, Optional, Set, Union

import html2text
from bs4 import BeautifulSoup

_log = logging.getLogger(__name__)

# Type annotation aliasses
EnexPath = Union[str, Path]


@dataclasses.dataclass(frozen=True)
class ParsedAttachment:
    file_name: str
    data: bytes
    md5_hash: str
    mime_type: str
    width: Optional[int] = None
    height: Optional[int] = None

    def __repr__(self):
        return f"{type(self).__name__}({self.file_name!r})"


@dataclasses.dataclass
class ParsedNote:
    title: str
    content: str
    tags: List[str]
    created: datetime.datetime
    updated: Optional[datetime.datetime] = None
    author: Optional[str] = None
    source_url: Optional[str] = None
    attachments: Optional[List[ParsedAttachment]] = None
    source_enex: Optional[Path] = None

    def __repr__(self):
        return f"{type(self).__name__}({self.title!r})"


class EnexParser:
    """Evernote Export (XML) file parser"""

    def __init__(self, chunk_size: int = 1024 * 1024, handle_attachments: bool = True):
        self.chunk_size = chunk_size
        self.handle_attachments = handle_attachments
        self.stats: Dict[str, int] = collections.Counter()

    def extract_note_elements(self, path: EnexPath) -> Iterator[xml.etree.ElementTree.Element]:
        """Extract notes from given ENEX (XML) file as XML Elements"""
        # Inspired by https://github.com/dogsheep/evernote-to-sqlite
        parser = xml.etree.ElementTree.XMLPullParser(["start", "end"])
        root = None
        bytes_read = 0
        note_count = 0
        _log.info(f"Start parsing {path}")
        with Path(path).open("r", encoding="utf-8") as f:
            try:
                while True:
                    chunk = f.read(self.chunk_size)
                    if not chunk:
                        break
                    bytes_read += len(chunk)
                    self.stats["bytes read"] += len(chunk)
                    parser.feed(chunk)
                    for event, el in parser.read_events():
                        if event == "start" and root is None:
                            root = el
                        if event == "end" and el.tag == "note":
                            note_count += 1
                            yield el
                        if root:
                            root.clear()
            finally:
                _log.info(f"Stop parsing {path}, bytes read: {bytes_read} bytes, notes prodiced: {note_count}.")

    def _get_value(
        self, element: xml.etree.ElementTree.Element, path: str, convertor: Optional[Callable] = None, default=None
    ) -> Union[None, str, int, float, datetime.datetime]:
        """Get value from XML Element"""
        el = element.find(path)
        if el is None:
            return default
        value = el.text
        if convertor:
            value = convertor(value)
        return value

    def _datetime_parse(self, s: str) -> datetime.datetime:
        """Parse datetime format used in ENEX"""
        d = datetime.datetime.strptime(s, "%Y%m%dT%H%M%SZ")
        return d.replace(tzinfo=datetime.timezone.utc)

    def parse_attachment_element(self, element: xml.etree.ElementTree.Element) -> ParsedAttachment:
        """Parse an attachment (resource) XML element."""
        # Parse data (base64 with newlines)
        data_element = element.find("data")
        assert data_element is not None and data_element.text
        data = base64.b64decode(re.sub(r"\s+", "", data_element.text))
        file_name = self._get_value(element, "resource-attributes/file-name")
        mime_type = self._get_value(element, "mime")
        if not file_name:
            file_name = "untitled"
            if mime_type:
                m = re.match(r"^\w+/(\w+)", mime_type)
                if m:
                    file_name += "." + m.group(1)
        self.stats["attachments parsed"] += 1
        return ParsedAttachment(
            file_name=file_name,
            data=data,
            md5_hash=hashlib.md5(data).hexdigest(),
            mime_type=mime_type,
            width=self._get_value(element, "width", convertor=int),
            height=self._get_value(element, "height", convertor=int),
        )

    def parse_note_element(
        self, element: xml.etree.ElementTree.Element, source_enex: Optional[EnexPath] = None
    ) -> ParsedNote:
        """Parse a note XML element."""
        if self.handle_attachments:
            attachments = [self.parse_attachment_element(e) for e in element.iterfind("resource")]
        else:
            attachments = None
        self.stats["notes parsed"] += 1
        return ParsedNote(
            title=(self._get_value(element, "title")),
            content=(self._get_value(element, "content")),
            tags=[e.text for e in element.iterfind("tag") if e.text],
            created=(self._get_value(element, "created", convertor=self._datetime_parse)),
            updated=(self._get_value(element, "updated", convertor=self._datetime_parse)),
            author=(self._get_value(element, "note-attributes/author")),
            source_url=(self._get_value(element, "note-attributes/source-url")),
            attachments=attachments,
            source_enex=Path(source_enex) if source_enex else None,
        )

    def extract_notes(self, enex_path: EnexPath) -> Iterator[ParsedNote]:
        """Extract all notes from given ENEX file."""
        for element in self.extract_note_elements(enex_path):
            yield self.parse_note_element(element, source_enex=enex_path)


class Sink:
    """Target to write markdown to"""

    handle_attachments = True

    def __init__(self):
        self.stats: Dict[str, int] = collections.Counter()

    def store_attachment(self, note: ParsedNote, attachment: ParsedAttachment) -> Optional[Path]:
        raise NotImplementedError

    def store_note(self, note: ParsedNote, lines: Iterable[str]):
        raise NotImplementedError


class StdOutSink(Sink):
    """Dump to stdout"""

    handle_attachments = False

    def store_note(self, note: ParsedNote, lines: Iterable[str]):
        print("--- New Note ---")
        for line in lines:
            print(line)
        print("--- End Note ---")


class TIMEZONE:
    UTC = "utc"
    LOCAL = "local"


def as_timezone(d: datetime.datetime, timezone: str) -> datetime.datetime:
    if timezone == TIMEZONE.LOCAL:
        return d.astimezone(tz=None)
    elif timezone == TIMEZONE.UTC:
        return d.astimezone(tz=datetime.timezone.utc)
    else:
        raise ValueError(timezone)


class FileSystemSink(Sink):
    """Write Markdown files"""

    DEFAULT_OUTPUT_ROOT = "output"
    DEFAULT_NOTE_PATH_TEMPLATE = "{now:%Y%m%d_%H%M%S}/{enex}/{title}.md"
    DEFAULT_ATTACHMENTS_PATH_TEMPLATE = "{now:%Y%m%d_%H%M%S}/{enex}/{title}_attachments/"

    class ROOT_CONDITION:
        LEAVE_AS_IS = "leave-as-is"
        REQUIRE_EMPTY = "require-empty"
        # TODO: auto clear option?

    class ON_EXISTING_FILE:
        BUMP = "bump"
        FAIL = "fail"
        OVERWRITE = "overwrite"
        WARN = "warn"

    def __init__(
        self,
        root: Optional[Union[str, Path]] = None,
        note_path_template: Optional[str] = None,
        attachments_path_template: Optional[str] = None,
        allow_spaces_in_filenames: bool = False,
        unsafe_replacer: str = "_",
        max_filename_length: int = 128,
        root_condition: str = ROOT_CONDITION.LEAVE_AS_IS,
        on_existing_file: str = ON_EXISTING_FILE.BUMP,
        timezone: str = TIMEZONE.UTC,
    ):
        """

        :param root: root folder for note and attachment output
        :param note_path_template: template for path of target Markdown files
        :param attachments_path_template: path template for folder to store attachments to
        :param allow_spaces_in_filenames: allow spaces when deriving file name from note title
        :param unsafe_replacer: replacement character for unsafe strings when deriving file name from note title
        :param max_filename_length: maximum length of note title based file name part
        :param root_condition: condition the root folder should be in: e.g. empty if it exists
        :param on_existing_file: what to do when a target file already exists: e.g. fail with exception,
            bump filename with an autoincrement counter until a new file name is found, ...
        """
        super().__init__()
        self.root = Path(root or self.DEFAULT_OUTPUT_ROOT)

        self.now = datetime.datetime.now(tz=datetime.timezone.utc)

        if note_path_template is None:
            note_path_template = self.DEFAULT_NOTE_PATH_TEMPLATE
            attachments_path_template = self.DEFAULT_ATTACHMENTS_PATH_TEMPLATE
        elif attachments_path_template is None:
            # Best effort guess based on note_path_template
            attachments_path_template = re.sub(r"(?:\.md)?$", "_attachments", note_path_template, count=1)

        _log.info(f"Using {note_path_template=!r} and {attachments_path_template=!r}")
        self.note_path_template = note_path_template
        self.attachments_path_template = attachments_path_template
        self.allow_spaces_in_filenames = allow_spaces_in_filenames
        self.unsafe_regex = re.compile("[^0-9a-zA-Z _-]+" if self.allow_spaces_in_filenames else "[^0-9a-zA-Z_-]+")
        self.unsafe_replacer = unsafe_replacer
        self.max_filename_length = max_filename_length

        self.root_condition = root_condition
        self._check_root_condition()
        self.written_files: Set[Path] = set()
        self.on_existing_file = on_existing_file

        self.timezone = timezone

    def _check_root_condition(self):
        if self.root.exists():
            assert self.root.is_dir(), f"Must be a folder: {self.root}"
            item_count = sum(1 for _ in self.root.iterdir())
            if self.root_condition == self.ROOT_CONDITION.LEAVE_AS_IS:
                pass
            elif self.root_condition == self.ROOT_CONDITION.REQUIRE_EMPTY:
                assert item_count == 0, f"Must be an empty folder but found {item_count} items: {self.root}"
            else:
                raise ValueError(self.root_condition)

    def _safe_name(self, text: str) -> str:
        """Strip unsafe characters from a string to produce a filename-safe string"""
        safe = self.unsafe_regex.sub(self.unsafe_replacer, text)
        safe = safe.strip(self.unsafe_replacer)
        return safe[: self.max_filename_length]

    def _build_path(self, template: str, note: ParsedNote, handle_existing: bool = True) -> Path:
        path = self.root / template.format(
            now=as_timezone(self.now, timezone=self.timezone),
            enex=self._safe_name(note.source_enex.stem) if note.source_enex else "enex",
            created=as_timezone(note.created, timezone=self.timezone),
            title=self._safe_name(note.title),
        )
        path = self._bump_while(path, condition=lambda p: p in self.written_files)

        if handle_existing and path.exists() and path.is_file():
            if self.on_existing_file == self.ON_EXISTING_FILE.BUMP:
                path = self._bump_while(path, condition=lambda p: p.exists())
            elif self.on_existing_file == self.ON_EXISTING_FILE.FAIL:
                raise FileExistsError(f"Already exists: {path}")
            elif self.on_existing_file == self.ON_EXISTING_FILE.OVERWRITE:
                pass
            elif self.on_existing_file == self.ON_EXISTING_FILE.WARN:
                _log.warning(f"Overwriting existing file {path}")
            else:
                raise ValueError(self.on_existing_file)

        return path

    def _bump_while(self, path: Path, condition) -> Path:
        """Bump a trailing counter in path while certain condition is true."""
        base_path = path
        counter = 1
        while condition(path):
            path = base_path.with_name(f"{base_path.stem}_{counter}{base_path.suffix}")
            counter += 1
        return path

    def store_attachment(self, note: ParsedNote, attachment: ParsedAttachment) -> Path:
        attachment_path = (
            self._build_path(template=self.attachments_path_template, note=note, handle_existing=False)
            / attachment.file_name
        )
        attachment_path = self._bump_while(attachment_path, condition=lambda p: p in self.written_files)

        _log.info(f"Writing attachment {attachment} of note {note} to {attachment_path}")
        attachment_path.parent.mkdir(parents=True, exist_ok=True)
        self.written_files.add(attachment_path)
        attachment_path.write_bytes(attachment.data)
        self.stats["attachments written"] += 1

        # Figure out path relative to note path.
        # Pathlib's `Path.relative_to` only support "walking up" starting in Python 3.12,
        # so we use old-school `os.path.relpath` here instead.
        note_path = self._build_path(template=self.note_path_template, note=note)
        return Path(os.path.relpath(attachment_path, start=note_path.parent))

    def store_note(self, note: ParsedNote, lines: Iterable[str]):
        path = self._build_path(template=self.note_path_template, note=note)
        _log.info(f"Writing converted note {note} to {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.written_files.add(path)
        with path.open("w", encoding="utf-8") as f:
            for line in lines:
                f.write(line + "\n")
        self.stats["notes written"] += 1


class Converter:
    """Convertor for ENEX note to Markdown format"""

    def __init__(self, front_matter: bool = False, timezone: str = TIMEZONE.UTC):
        self.front_matter = front_matter
        self.timezone = timezone
        self.stats: Dict[str, int] = collections.Counter()

    def convert(self, enex: EnexPath, sink: Sink, parser: Optional[EnexParser] = None):
        parser = parser or EnexParser()
        for note in parser.extract_notes(enex):
            _log.info(f"Converting {note.title!r}")
            self.export_note(note, sink)

    def export_note(self, note: ParsedNote, sink: Sink):
        content = note.content

        # Preprocessors:
        if sink.handle_attachments:
            content = self._handle_attachments(content)
        content = self._handle_lists(content)
        content = self._handle_tasks(content)
        content = self._handle_strongs_emphases(content)
        content = self._handle_tables(content)
        content = self._handle_codeblocks(content)

        # Content is HTML, and requires little bit of magic.
        # TODO: create this in __init__?
        text_maker = html2text.HTML2Text()
        text_maker.single_line_break = True
        text_maker.inline_links = True
        text_maker.use_automatic_links = False
        text_maker.body_width = 0
        text_maker.emphasis_mark = "*"

        # Convert html > text
        content = text_maker.handle(content)

        # Postprocessors:
        content = self._post_processor_code_newlines(content)

        if sink.handle_attachments and note.attachments:
            for attachment in note.attachments:
                attachment_ref = sink.store_attachment(note=note, attachment=attachment)
                # TODO Poor man's URL encoding here (just spaces). Need for additional encoding?
                attachment_ref = str(attachment_ref).replace(" ", "%20")
                content = content.replace(
                    f"![](enex2md-attachment:{attachment.md5_hash})",
                    f"\n![{attachment.file_name}]({attachment_ref})",
                )

        # Store note itself
        sink.store_note(
            note=note,
            lines=itertools.chain(
                self._format_header(note),
                [content],
            ),
        )

        self.stats["notes exported"] += 1

    def _handle_codeblocks(self, text: str) -> str:
        """We would need to be able to recognise these (linebreaks added for brevity), and transform them to <pre> elements.
        <div style="box-sizing: border-box; padding: 8px; font-family: Monaco, Menlo, Consolas, &quot;Courier New&quot;, monospace; font-size: 12px; color: rgb(51, 51, 51); border-top-left-radius: 4px; border-top-right-radius: 4px; border-bottom-right-radius: 4px; border-bottom-left-radius: 4px; background-color: rgb(251, 250, 248); border: 1px solid rgba(0, 0, 0, 0.14902);-en-codeblock:true;">
        <div>import this</div>
        <div><br /></div>
        <div>my_data = this.create_object()</div>
        <div><br /></div>
        <div># One line comment.</div>
        <div><br /></div>
        <div>“”” A block comment</div>
        <div>    containing two lines.</div>
        <div>“”"</div>
        <div><br /></div>
        <div>print(my data)</div>
        </div>
        """
        soup = BeautifulSoup(text, "html.parser")

        for block in soup.find_all(style=re.compile(r".*-en-codeblock:true.*")):
            # Get the data, and set it in pre-element line by line.
            code = "code-begin-code-begin-code-begin\n"
            for nugget in block.select("div"):
                code += f"{nugget.text}\n"
            code += "code-end-code-end-code-end"

            # Fix the duoblequotes
            code = code.replace("“", '"')
            code = code.replace("”", '"')

            new_block = soup.new_tag("pre")
            new_block.string = code
            block.replace_with(new_block)

        return str(soup)

    def _handle_attachments(self, text: str) -> str:
        """
        Note content may have attachments, such as images, e.g.:

            <en-media hash="..." type="application/pdf" style="cursor:pointer;" />
            <en-media hash="..." type="image/png" />
            <en-media hash="..." type="image/jpeg" />
        """

        def replace_attachment(match):
            h = re.search('hash="([0-9a-fA-F]+)"', match.group(1))
            if h:
                return f"<div>![](enex2md-attachment:{h.group(1)})</div>"
            else:
                _log.warning("Failed to find <en-media> hash")
                return match.group(0)

        text = re.sub(
            r"<en-media ([^>]*)(/>|>\s*</en-media.*?>)",
            replace_attachment,
            text,
        )
        return text

    def _handle_tables(self, text: str) -> str:
        """Split by tables. Within the blocks containing tables, remove divs."""

        parts = re.split(r"(<table.*?</table>)", text)

        new_parts = []
        for part in parts:
            if part.startswith("<table"):
                part = part.replace("<div>", "")
                part = part.replace("</div>", "")
            new_parts.append(part)

        text = "".join(new_parts)

        return text

    def _handle_strongs_emphases(self, text: str) -> str:
        """Make these work.
        <span style="font-weight: bold;">This text is bold.</span>
        <span style="font-style: italic;">This text is italic.</span>
        <span style="font-style: italic; font-weight: bold;">This text is bold and italic.</span>

        <div>
        <span style="font-style: italic; font-weight: bold;"><br /></span>
        </div>
        <div>This text is normal. <i><b>This text is bold and italic.</b></i> This text is normal again.</div>
        """
        parts = re.split(r"(<span.*?</span>)", text)

        new_parts = []
        for part in parts:
            match = re.match(r"<span style=(?P<formatting>.*?)>(?P<content>.*?)</span>", part)
            if match:
                if match.group("content") == "<br />":
                    part = "<br />"
                else:
                    if "font-style: italic;" in match.group("formatting") and "font-weight: bold;" in match.group(
                        "formatting"
                    ):
                        # part = f"<i><b>{match.group('content')}</b></i>"
                        part = f"<span>***{match.group('content')}***</span>"
                    elif "font-weight: bold;" in match.group("formatting"):
                        # part = f"<b>{match.group('content')}</b>"
                        part = f"<span>**{match.group('content')}**</span>"
                    elif "font-style: italic;" in match.group("formatting"):
                        # part = f"<i>{match.group('content')}</i>"
                        part = f"<span>*{match.group('content')}*</span>"
            new_parts.append(part)

        text = "".join(new_parts)

        return text

    def _handle_tasks(self, text: str) -> str:
        text = text.replace('<en-todo checked="true"/>', '<en-todo checked="true"/>[x] ')
        text = text.replace('<en-todo checked="false"/>', '<en-todo checked="false"/>[ ] ')
        text = text.replace('<en-todo checked="true" />', '<en-todo checked="true"/>[x] ')
        text = text.replace('<en-todo checked="false" />', '<en-todo checked="false"/>[ ] ')
        return text

    def _handle_lists(self, text: str) -> str:
        text = re.sub(r"<ul>", "<br /><ul>", text)
        text = re.sub(r"<ol>", "<br /><ol>", text)
        return text

    def _post_processor_code_newlines(self, text: str) -> str:
        new_lines = []
        for line in text.split("\n"):
            # The html2text conversion generates whitespace from enex. Let's remove the redundant.
            line = line.rstrip()

            if line == "**" or line == " **":
                line = ""

            if line.startswith("    ") and not line.lstrip()[:1] == "*":
                line = line[4:]

            if line == "code-begin-code-begin-code-begin" or line == "code-end-code-end-code-end":
                new_lines.append("```")
            else:
                new_lines.append(line)

        text = "\n".join(new_lines)

        # Merge multiple empty lines to one.
        text = re.sub(r"\n{3,}", "\n\n", text).strip()

        return text

    def _format_header(self, note: ParsedNote) -> Iterator[str]:
        metadata = {
            "title": note.title,
        }
        if note.author:
            metadata["author"] = note.author
        if note.source_url:
            metadata["source_url"] = note.source_url
        if note.created:
            metadata["created"] = as_timezone(note.created, timezone=self.timezone).isoformat()
        if note.updated:
            metadata["updated"] = as_timezone(note.updated, timezone=self.timezone).isoformat()

        if note.tags:
            metadata["tags"] = ", ".join(note.tags)

        if self.front_matter:
            yield "---"
            yield from (f"{k}: {v}" for k, v in metadata.items())
            yield "---"
            yield ""
            yield ""

        yield f"# {note.title}"
        yield ""
        if not self.front_matter:
            yield "## Note metadata"
            yield ""
            yield from (f"- {k.title()}: {v}" for k, v in metadata.items())
            yield ""
            yield "## Note Content"
            yield ""
