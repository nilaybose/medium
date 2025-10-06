import pdfplumber
import re
from typing import List, Dict, Tuple
from collections import Counter


class PDFToMarkdownConverter:
    def __init__(self):
        self.font_sizes = Counter()

    def extract_text_with_formatting(self, pdf_path: str) -> str:
        """
        Main method to open a PDF, analyze its structure, and convert its content
        to a formatted Markdown string.
        """
        markdown_content = []

        with pdfplumber.open(pdf_path) as pdf:
            self._analyze_document_structure(pdf)

            for page_num, page in enumerate(pdf.pages):
                page_content = self._process_page(page, page_num)
                if page_content.strip():
                    markdown_content.append(page_content)

        return '\n\n'.join(markdown_content)

    def _analyze_document_structure(self, pdf):
        """
        Analyzes the entire PDF document to understand its font size distribution.
        This helps in later determining what constitutes a heading part of GARAK parsing logic.
        """
        self.font_sizes.clear()
        for page in pdf.pages:
            chars = page.chars
            for char in chars:
                if char.get('size'):
                    # Round font sizes to 1 decimal place for better grouping
                    self.font_sizes[round(float(char['size']), 1)] += 1

    def _process_page(self, page, page_num: int) -> str:
        """
        Processes a single page, extracting text blocks and tables,
        ordering them based on their visual position, and returning
        the formatted Markdown for that page.
        """
        page_elements = []

        chars = page.chars
        if chars:
            lines = self._group_chars_into_lines(chars)
            text_blocks = self._group_lines_into_blocks(lines)

            for block in text_blocks:
                if block:
                    min_x0 = min(char['x0'] for line in block for char in line)
                    max_x1 = max(char['x1'] for line in block for char in line)
                    min_top = min(char['top'] for line in block for char in line)
                    max_bottom = max(char['bottom'] for line in block for char in line)
                    bbox = (min_x0, min_top, max_x1, max_bottom)
                    page_elements.append({'type': 'text', 'content': block, 'bbox': bbox})

        tables = page.find_tables()
        for table in tables:
            page_elements.append({'type': 'table', 'content': table, 'bbox': table.bbox})

        page_elements.sort(key=lambda x: (x['bbox'][1], x['bbox'][0]))

        markdown_parts = []
        for element in page_elements:
            if element['type'] == 'text':
                block_md = self._process_text_block(element['content'])
                if block_md.strip():
                    markdown_parts.append(block_md)
            elif element['type'] == 'table':
                table_md = self._convert_table_to_markdown(element['content'])
                if table_md.strip():
                    markdown_parts.append(table_md)

        return '\n\n'.join(markdown_parts)

    def _group_chars_into_lines(self, chars: List[Dict]) -> List[List[Dict]]:
        """
        Groups individual characters into coherent lines based on their vertical position.
        Characters within a line are then sorted horizontally.
        """
        if not chars:
            return []

        sorted_chars = sorted(chars, key=lambda c: (c['top'], c['x0']))

        lines = []
        current_line = []
        current_y_range = None
        y_tolerance = 3

        for char in sorted_chars:
            char_top = char['top']
            char_bottom = char['bottom']

            if not current_line:
                current_line.append(char)
                current_y_range = (char_top, char_bottom)
            else:
                current_line_avg_y = sum(c['top'] + c['bottom'] for c in current_line) / (2 * len(current_line))
                char_avg_y = (char_top + char_bottom) / 2

                if abs(char_avg_y - current_line_avg_y) <= y_tolerance:
                    current_line.append(char)
                    current_y_range = (min(current_y_range[0], char_top), max(current_y_range[1], char_bottom))
                else:
                    lines.append(sorted(current_line, key=lambda c: c['x0']))
                    current_line = [char]
                    current_y_range = (char_top, char_bottom)

        if current_line:
            lines.append(sorted(current_line, key=lambda c: c['x0']))

        return lines

    def _group_lines_into_blocks(self, lines: List[List[Dict]]) -> List[List[List[Dict]]]:
        """
        Groups lines into larger text blocks (paragraphs) based on vertical spacing between lines.
        A larger-than-average gap suggests a new paragraph.
        """
        if not lines:
            return []

        blocks = []
        current_block = []
        prev_line_bottom = None
        paragraph_spacing_threshold = 1.5 * self._get_median_line_height(lines) if lines else 15

        for line in lines:
            if not line:
                continue

            line_top = min(char['top'] for char in line)
            line_bottom = max(char['bottom'] for char in line)

            if prev_line_bottom is not None:
                line_spacing = line_top - prev_line_bottom
                if line_spacing > paragraph_spacing_threshold:
                    if current_block:
                        blocks.append(current_block)
                    current_block = []

            current_block.append(line)
            prev_line_bottom = line_bottom

        if current_block:
            blocks.append(current_block)

        return blocks

    def _get_median_line_height(self, lines: List[List[Dict]]) -> float:
        """
        Calculates the median estimated line height from the font sizes of characters.
        Used to dynamically adjust paragraph spacing thresholds.
        """
        heights = []
        for line in lines:
            if line:
                line_font_sizes = [char.get('size', 0) for char in line if char.get('size')]
                if line_font_sizes:
                    most_common_size = Counter(line_font_sizes).most_common(1)[0][0]
                    heights.append(most_common_size)

        if heights:
            heights.sort()
            mid = len(heights) // 2
            return (heights[mid] + heights[~mid]) / 2 if len(heights) % 2 == 0 else heights[mid]
        return 12

    def _process_text_block(self, block: List[List[Dict]]) -> str:
        """
        Processes a single text block (which is a list of lines),
        applies heading formatting if detected, and joins lines into paragraphs.
        """
        if not block:
            return ""

        block_lines_md = []

        for line in block:
            if not line:
                continue

            line_text, line_size = self._process_line(line)
            cleaned_line_text = self._clean_text(line_text)
            if cleaned_line_text:
                if self._is_heading(line_size, cleaned_line_text):
                    formatted_line = self._format_as_heading(cleaned_line_text, line_size)
                    block_lines_md.append(formatted_line)
                else:
                    block_lines_md.append(cleaned_line_text)

        final_block_content = []
        current_paragraph = []
        for item in block_lines_md:
            if item.startswith('#'):
                if current_paragraph:
                    final_block_content.append(' '.join(current_paragraph))
                    current_paragraph = [] # Reset for next paragraph
                final_block_content.append(item) # Add the heading as a separate item
            else:
                current_paragraph.append(item)
        if current_paragraph:
            final_block_content.append(' '.join(current_paragraph))

        return '\n'.join(final_block_content)

    def _process_line(self, line: List[Dict]) -> Tuple[str, float]:
        """
        Processes a single line of characters, concatenating text and determining
        the dominant font size for that line.
        """
        if not line:
            return "", 0.0

        line_text = ""
        font_sizes = []

        sorted_line = sorted(line, key=lambda c: c['x0'])

        for char in sorted_line:
            text = char.get('text', '')
            size = char.get('size', 0)

            line_text += text
            if size:
                font_sizes.append(float(size))

        if font_sizes:
            dominant_size = Counter(font_sizes).most_common(1)[0][0]
        else:
            dominant_size = 0.0

        return line_text, dominant_size

    def _is_heading(self, font_size: float, text: str) -> bool:
        """
        Determines if a given line of text should be formatted as a heading.
        Heuristics include font size relative to body text, length, and punctuation.
        """
        if not self.font_sizes:
            return False

        most_common_size = self.font_sizes.most_common(1)
        if not most_common_size:
            return False
        body_size = most_common_size[0][0]

        size_threshold = body_size * 1.1
        is_larger = font_size >= size_threshold
        is_short = len(text.strip()) < 100
        no_period = not text.strip().endswith('.') and not text.strip().endswith(',')

        return is_larger and font_size > body_size and (is_short or no_period)

    def _format_as_heading(self, text: str, font_size: float) -> str:
        """
        Formats text as a Markdown heading (H1 to H5) based on its font size
        relative to the document's body text size.
        """
        if not self.font_sizes:
            return f"## {text}"

        most_common_size = self.font_sizes.most_common(1)
        if not most_common_size:
            return f"## {text}"
        body_size = most_common_size[0][0]
        size_ratio = font_size / body_size if body_size > 0 else 1.0

        if size_ratio >= 2.0:
            return f"# {text}"
        elif size_ratio >= 1.7:
            return f"## {text}"
        elif size_ratio >= 1.4:
            return f"### {text}"
        elif size_ratio >= 1.2:
            return f"#### {text}"
        else:
            return f"##### {text}"

    def _convert_table_to_markdown(self, table) -> str:
        """
        Converts a pdfplumber table object into a Markdown table string.
        Handles missing cells and ensures proper Markdown table formatting.
        """
        try:
            data = table.extract()
            if not data or len(data) < 2:
                return ""

            markdown_table = []

            headers = data[0]
            if headers:
                header_row = "| " + " | ".join(str(cell).strip() if cell is not None else "" for cell in headers) + " |"
                markdown_table.append(header_row)

                separator = "| " + " | ".join("---" for _ in headers) + " |"
                markdown_table.append(separator)

                for row in data[1:]:
                    if row:
                        data_row = "| " + " | ".join(str(cell).strip() if cell is not None else "" for cell in row) + " |"
                        markdown_table.append(data_row)

            return "\n".join(markdown_table)
        except Exception as e:
            return ""

    def _clean_text(self, text: str) -> str:
        """
        Cleans and normalizes text by replacing multiple whitespace characters
        with a single space and stripping leading/trailing whitespace.
        """
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        return text


def to_markdown(file_path: str) -> str:
    """
    Public function to convert a PDF file to a Markdown string using
    the PDFToMarkdownConverter class.
    """
    converter = PDFToMarkdownConverter()
    return converter.extract_text_with_formatting(file_path)


def to_markdown_simple(file_path: str) -> str:
    """
    A simpler PDF to Markdown converter using pypdf.
    This function is provided as an alternative but may not handle complex
    layouts or tables as accurately as the pdfplumber-based converter.
    It primarily extracts raw text and applies basic paragraph/heading heuristics.
    """
    try:
        from pypdf import PdfReader

        reader = PdfReader(file_path)
        markdown_content = []

        for page_num, page in enumerate(reader.pages):
            text = page.extract_text()
            if text.strip():
                paragraphs = text.split('\n\n')
                page_content = []

                for para in paragraphs:
                    para = para.strip().replace('\n', ' ')
                    if para:
                        if len(para) < 80 and not para.endswith('.') and not para.endswith(','):
                            page_content.append(f"## {para}")
                        else:
                            page_content.append(para)

                if page_content:
                    markdown_content.extend(page_content)

        return '\n\n'.join(markdown_content)

    except ImportError:
        raise ImportError("Please install pypdf: pip install pypdf")
