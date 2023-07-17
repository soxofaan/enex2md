import base64
import dataclasses
import datetime
import hashlib
import os
import re
import logging
from typing import List, Dict, Union, Optional, Iterator, Callable
from pathlib import Path
import xml.etree.ElementTree

from bs4 import BeautifulSoup
from dateutil.parser import parse as dateutil_parse
import html2text

# TODO: possible to eliminate dependency on lxml?
from lxml import etree


_log = logging.getLogger(__name__)


# Type annotation aliases
Note = Dict[str, Union[str, datetime.datetime]]
Attachment = Dict[str, Union[str, bytes]]


class Sink:
    """Target to write markdown to"""

    handle_attachments = True

    def store_attachment(self, note: Note, attachment: Attachment) -> Optional[Path]:
        raise NotImplementedError

    def store_note(self, note: Note, lines: List[str]):
        raise NotImplementedError


class StdOutSink(Sink):
    """Dump to stdout"""

    handle_attachments = False

    def store_note(self, note: Note, lines: List[str]):
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

    def _note_path(self, note: Note) -> Path:
        # TODO: smarter output files (e.g avoid conflicts, add timestamp/id, ...)
        return self.root / (_make_safe_name(note["title"]) + ".md")

    def store_attachment(self, note: Note, attachment: Attachment) -> Optional[Path]:
        note_path = self._note_path(note)
        path = self.root / (_make_safe_name(note["title"]) + "_attachments") / attachment["filename"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(attachment["data"])
        return path.relative_to(note_path.parent)

    def store_note(self, note: Note, lines: List[str]):
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


@dataclasses.dataclass(frozen=True)
class ParsedAttachment:
    file_name: str
    data: bytes
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
        """Parse datetime formet used in ENEX"""
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
        for element in self.extract_note_elements(enex_path):
            yield self.parse_note_element(element)


class Converter:
    def __init__(self, enex_file: Union[str, Path], sink: Sink, front_matter: bool = False):
        # TODO: eliminate `enex_file` from this constructor
        self.enex_file = enex_file
        self.front_matter = front_matter
        self.sink = sink

    def convert(self):
        if not os.path.exists(self.enex_file):
            raise FileNotFoundError(f'The given input file "{self.enex_file}" does not exist.')

        tree = etree.parse(self.enex_file)
        notes = self._parse_notes(tree)
        for note in notes:
            self._export_note(note)

    def _parse_notes(self, xml_tree) -> List[Note]:
        note_count = 0
        notes = []
        raw_notes = xml_tree.xpath('//note')
        # TODO: move for loop outside of parsing function
        for note in raw_notes:
            note_count += 1
            # TODO: use dataclass instead of generic dict
            keys = {}
            keys['title'] = note.xpath('title')[0].text
            keys["created"] = dateutil_parse(note.xpath("created")[0].text)
            if note.xpath("updated"):
                keys["updated"] = dateutil_parse(note.xpath("updated")[0].text)
            if note.xpath('note-attributes/author'):
                keys['author'] = note.xpath('note-attributes/author')[0].text
            if note.xpath('note-attributes/source-url'):
                keys['source_url'] = note.xpath('note-attributes/source-url')[0].text
            keys['tags'] = [tag.text for tag in note.xpath('tag')]
            keys['tags_string'] = ", ".join(tag for tag in keys['tags'])

            ''' Content is HTML, and requires little bit of magic. '''

            text_maker = html2text.HTML2Text()
            text_maker.single_line_break = True
            text_maker.inline_links = True
            text_maker.use_automatic_links = False
            text_maker.body_width = 0
            text_maker.emphasis_mark = '*'

            content_pre = note.xpath('content')[0].text

            # Preprosessors:
            if self.sink.handle_attachments:
                content_pre = self._handle_attachments(content_pre)
            content_pre = self._handle_lists(content_pre)
            content_pre = self._handle_tasks(content_pre)
            content_pre = self._handle_strongs_emphases(content_pre)
            content_pre = self._handle_tables(content_pre)
            content_pre = self._handle_codeblocks(content_pre)

            # Convert html > text
            content_text = text_maker.handle(content_pre)

            # Postprocessors:
            content_post = self._post_processor_code_newlines(content_text)

            keys['content'] = content_post

            # Attachment data
            if self.sink.handle_attachments:
                keys['attachments'] = []
                raw_resources = note.xpath('resource')
                for resource in raw_resources:
                    attachment = {}
                    try:
                        attachment['filename'] = resource.xpath('resource-attributes/file-name')[0].text
                    except IndexError:
                        _log.warning(f"Skipping attachment on note with title \"{keys['title']}\" because the name xml element is missing (resource/resource-attributes/file-name).")
                        continue

                    # Base64 encoded data has new lines! Because why not!
                    clean_data = re.sub(r'\n', '', resource.xpath('data')[0].text).strip()
                    attachment["data"] = base64.b64decode(clean_data)
                    attachment['mime_type'] = resource.xpath('mime')[0].text
                    keys['attachments'].append(attachment)

            # TODO: yield instead of append
            notes.append(keys)

        _log.info(f"Processed {note_count} note(s).")
        return notes

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

    def _format_note(self, note: Note) -> List[str]:
        metadata = {
            k: note[k]
            for k in ["title", "author", "source_url"]
            if k in note and note[k]
        }
        # TODO: option to format time in local time (instead of UTC)
        metadata.update(
            (k, note[k].isoformat()) for k in ["created", "updated"] if k in note and note[k]
        )
        if note.get("tags"):
            metadata["tags"] = ", ".join(note["tags"])

        note_content = []
        if self.front_matter:
            note_content.append("---")
            note_content.extend(f"{k}: {v}" for k, v in metadata.items())
            note_content.append("---")
            note_content.append("")
            note_content.append("")

        note_content.append(f"# {note['title']}")
        note_content.append("")
        if not self.front_matter:
            note_content.append("## Note metadata")
            note_content.append("")
            note_content.extend(f"- {k.title()}: {v}" for k, v in metadata.items())
            note_content.append("")
            note_content.append("## Note Content")
            note_content.append("")

        note_content.append(note['content'])

        return note_content

    def _export_note(self, note: Note):
        # First: store attachments and fix references
        for attachment in note.get("attachments", []):
            attachment_ref = self.sink.store_attachment(note=note, attachment=attachment)

            # Fix attachment reference to note content
            md5_hash = hashlib.md5(attachment["data"]).hexdigest()
            note["content"] = note["content"].replace(
                f"ATCHMT:{md5_hash}", f"\n![{attachment['filename']}]({attachment_ref})"
            )

        # Store note itself
        self.sink.store_note(note=note, lines=self._format_note(note))
