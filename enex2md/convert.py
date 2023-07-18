import base64
import dataclasses
import datetime
import hashlib
import itertools
import logging
import re
import xml.etree.ElementTree
from pathlib import Path
from typing import Callable, Iterable, Iterator, List, Optional, Union

import html2text
from bs4 import BeautifulSoup

_log = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class ParsedAttachment:
    file_name: str
    data: bytes
    md5_hash: str
    mime_type: str
    width: Optional[int] = None
    height: Optional[int] = None


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


class EnexParser:
    """Evernote Export (XML) file parser"""

    def __init__(self, chunk_size: int = 1024 * 1024, handle_attachments: bool = True):
        self.chunk_size = chunk_size
        self.handle_attachments = handle_attachments

    def extract_note_elements(self, path: Union[str, Path]) -> Iterator[xml.etree.ElementTree.Element]:
        """Extract notes from given ENEX (XML) file as XML Elements"""
        # Inspired by https://github.com/dogsheep/evernote-to-sqlite
        parser = xml.etree.ElementTree.XMLPullParser(["start", "end"])
        root = None
        # TODO: show progress of reading the XML file chunks.
        with Path(path).open("r", encoding="utf-8") as f:
            while True:
                chunk = f.read(self.chunk_size)
                if not chunk:
                    break
                parser.feed(chunk)
                for event, el in parser.read_events():
                    if event == "start" and root is None:
                        root = el
                    if event == "end" and el.tag == "note":
                        yield el
                    root.clear()

    def _get_value(
        self, element: xml.etree.ElementTree.Element, path: str, convertor: Optional[Callable] = None, default=None
    ):
        """Get value from XML Element"""
        value = element.find(path)
        if value is None:
            return default
        value = value.text
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
        data = re.sub(r"\s+", "", element.find("data").text)
        data = base64.b64decode(data)
        return ParsedAttachment(
            file_name=self._get_value(element, "resource-attributes/file-name"),
            data=data,
            md5_hash=hashlib.md5(data).hexdigest(),
            mime_type=self._get_value(element, "mime"),
            width=self._get_value(element, "width", convertor=int),
            height=self._get_value(element, "height", convertor=int),
        )

    def parse_note_element(self, element: xml.etree.ElementTree.Element) -> ParsedNote:
        """Parse a note XML element."""
        if self.handle_attachments:
            attachments = [self.parse_attachment_element(e) for e in element.iterfind("resource")]
        else:
            attachments = None
        return ParsedNote(
            title=(self._get_value(element, "title")),
            content=(self._get_value(element, "content")),
            tags=[e.text for e in element.iterfind("tag")],
            created=(self._get_value(element, "created", convertor=self._datetime_parse)),
            updated=(self._get_value(element, "updated", convertor=self._datetime_parse)),
            author=(self._get_value(element, "note-attributes/author")),
            source_url=(self._get_value(element, "note-attributes/source-url")),
            attachments=attachments,
        )

    def extract_notes(self, enex_path: Union[str, Path]) -> Iterator[ParsedNote]:
        """Extract all notes from given ENEX file."""
        # TODO: progress bar or counter of extracted notes?
        for element in self.extract_note_elements(enex_path):
            yield self.parse_note_element(element)


class Sink:
    """Target to write markdown to"""

    handle_attachments = True

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


class FileSystemSink(Sink):
    """Write Markdown files"""

    def __init__(self, root: Union[str, Path]):
        # TODO: option to empty root first? Or fail when root is not empty?
        # TODO: option to avoid overwriting existing files?
        self.root = Path(root)

    @classmethod
    def legacy_root_from_enex(cls, enex_path: Union[str, Path]) -> "FileSystemSink":
        """
        Legacy mode: create output folder automatically from ENEX filename and timestamp
        """
        # TODO: eliminate this legacy approach
        enex_path = Path(enex_path)
        subfolder_name = _make_safe_name(enex_path.stem)
        root = Path("output") / datetime.datetime.now().strftime("%Y%m%d_%H%M%S") / subfolder_name
        root.mkdir(parents=True, exist_ok=True)
        return cls(root=root)

    def _note_path(self, note: ParsedNote) -> Path:
        # TODO: smarter output files (e.g avoid conflicts, add timestamp/id, ...)
        return self.root / (_make_safe_name(note.title) + ".md")

    def store_attachment(self, note: ParsedNote, attachment: ParsedAttachment) -> Optional[Path]:
        note_path = self._note_path(note)
        path = self.root / (_make_safe_name(note.title) + "_attachments") / attachment.file_name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(attachment.data)
        return path.relative_to(note_path.parent)

    def store_note(self, note: ParsedNote, lines: Iterable[str]):
        path = self._note_path(note)
        with path.open("w", encoding="utf-8") as f:
            for line in lines:
                f.write(line + "\n")


def _make_safe_name(input_string: str, counter=0) -> str:
    better = input_string.replace(" ", "_")
    better = "".join([c for c in better if re.match(r"\w", c)])
    # For handling duplicates: If counter > 0, append to file/folder name.
    if counter > 0:
        better = f"{better}_{counter}"
    return better


class Converter:
    """Convertor for ENEX note to Markdown format"""

    def __init__(self, front_matter: bool = False):
        self.front_matter = front_matter

    def convert(self, enex: Union[str, Path], sink: Sink):
        parser = EnexParser()
        for note in parser.extract_notes(enex):
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

        if note.attachments:
            for attachment in note.attachments:
                attachment_ref = sink.store_attachment(note=note, attachment=attachment)
                content = content.replace(
                    f"ATCHMT:{attachment.md5_hash}",
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

    def _handle_codeblocks(self, text: str) -> str:
        """ We would need to be able to recognise these (linebreaks added for brevity), and transform them to <pre> elements.
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
        soup = BeautifulSoup(text, 'html.parser')

        for block in soup.find_all(style=re.compile(r'.*-en-codeblock:true.*')):
            # Get the data, and set it in pre-element line by line.
            code = 'code-begin-code-begin-code-begin\n'
            for nugget in block.select('div'):
                code += f"{nugget.text}\n"
            code += 'code-end-code-end-code-end'

            # Fix the duoblequotes
            code = code.replace('“', '"')
            code = code.replace('”', '"')

            new_block = soup.new_tag('pre')
            new_block.string = code
            block.replace_with(new_block)

        return str(soup)

    def _handle_attachments(self, text: str) -> str:
        """ Note content may have attachments, such as images.
        <div><en-media hash="..." type="application/pdf" style="cursor:pointer;" /></div>
        <div><en-media hash="..." type="image/png" /><br /></div>
        <div><en-media hash="..." type="image/jpeg" /></div>
        """
        parts = re.split(r'(<en-media.*?/>)', text)
        new_parts = []
        for part in parts:
            if part.startswith('<en-media'):
                match = re.match(r'<en-media hash="(?P<md5_hash>.*?)".*? />', part)
                if match:
                    part = f"<div>ATCHMT:{match.group('md5_hash')}</div>"
            new_parts.append(part)
        text = ''.join(new_parts)
        return text

    def _handle_tables(self, text: str) -> str:
        """ Split by tables. Within the blocks containing tables, remove divs. """

        parts = re.split(r'(<table.*?</table>)', text)

        new_parts = []
        for part in parts:
            if part.startswith('<table'):
                part = part.replace('<div>', '')
                part = part.replace('</div>', '')
            new_parts.append(part)

        text = ''.join(new_parts)

        return text

    def _handle_strongs_emphases(self, text: str) -> str:
        """ Make these work.
        <span style="font-weight: bold;">This text is bold.</span>
        <span style="font-style: italic;">This text is italic.</span>
        <span style="font-style: italic; font-weight: bold;">This text is bold and italic.</span>

        <div>
        <span style="font-style: italic; font-weight: bold;"><br /></span>
        </div>
        <div>This text is normal. <i><b>This text is bold and italic.</b></i> This text is normal again.</div>
        """
        parts = re.split(r'(<span.*?</span>)', text)

        new_parts = []
        for part in parts:
            match = re.match(r'<span style=(?P<formatting>.*?)>(?P<content>.*?)</span>', part)
            if match:
                if match.group('content') == '<br />':
                    part = '<br />'
                else:
                    if 'font-style: italic;' in match.group('formatting') and 'font-weight: bold;' in match.group('formatting'):
                        # part = f"<i><b>{match.group('content')}</b></i>"
                        part = f"<span>***{match.group('content')}***</span>"
                    elif 'font-weight: bold;' in match.group('formatting'):
                        # part = f"<b>{match.group('content')}</b>"
                        part = f"<span>**{match.group('content')}**</span>"
                    elif 'font-style: italic;' in match.group('formatting'):
                        # part = f"<i>{match.group('content')}</i>"
                        part = f"<span>*{match.group('content')}*</span>"
            new_parts.append(part)

        text = ''.join(new_parts)

        return text

    def _handle_tasks(self, text: str) -> str:
        text = text.replace('<en-todo checked="true"/>', '<en-todo checked="true"/>[x] ')
        text = text.replace('<en-todo checked="false"/>', '<en-todo checked="false"/>[ ] ')
        text = text.replace('<en-todo checked="true" />', '<en-todo checked="true"/>[x] ')
        text = text.replace('<en-todo checked="false" />', '<en-todo checked="false"/>[ ] ')
        return text

    def _handle_lists(self, text: str) -> str:
        text = re.sub(r'<ul>', '<br /><ul>', text)
        text = re.sub(r'<ol>', '<br /><ol>', text)
        return text

    def _post_processor_code_newlines(self, text: str) -> str:
        new_lines = []
        for line in text.split('\n'):
            # The html2text conversion generates whitespace from enex. Let's remove the redundant.
            line = line.rstrip()

            if line == '**' or line == ' **':
                line = ''

            if line.startswith("    ") and not line.lstrip()[:1] == "*":
                line = line[4:]

            if line == 'code-begin-code-begin-code-begin' or line == 'code-end-code-end-code-end':
                new_lines.append('```')
            else:
                new_lines.append(line)

        text = '\n'.join(new_lines)

        # Merge multiple empty lines to one.
        text = re.sub(r'\n{3,}', '\n\n', text).strip()

        return text

    def _format_header(self, note: ParsedNote) -> Iterator[str]:
        metadata = {
            "title": note.title,
        }
        if note.author:
            metadata["author"] = note.author
        if note.source_url:
            metadata["source_url"] = note.source_url
        # TODO: option to format time in local time (instead of UTC)
        if note.created:
            metadata["created"] = note.created.isoformat()
        if note.updated:
            metadata["updated"] = note.updated.isoformat()

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
            # TODO: drop this old metadata style?
            yield "## Note metadata"
            yield ""
            yield from (f"- {k.title()}: {v}" for k, v in metadata.items())
            yield ""
            yield "## Note Content"
            yield ""
