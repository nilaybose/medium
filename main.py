from embedding.garakPDFparser import to_markdown
import langextract as lx
import pymupdf4llm as pdf_parser
import re
import uuid
from chroma_client import insert_data, search_data

def load_pdf_with_garakPDFparser(pdf_path):
    """
    Loads a PDF file using garakPDFparser and returns its content.
    """
    try:
        doc = to_markdown(pdf_path)
        return doc
    except Exception as e:
        return f"Error loading PDF: {e}"

class DocNode:
    def __init__(self, content: str, index: int, filename: str, metadata: dict = None, chunk: str = None):
        self.uid = str(uuid.uuid4())
        self.content = content
        self.index = index
        self.filename = filename
        self.metadata = {"window": content, "filename" : filename, "fileindex": index}
        self.chunk = chunk # New field for the chunk content

    def __repr__(self):
        return f"DocNode(uid='{self.uid}', index={self.index}, filename='{self.filename}', metadata={self.metadata}, content='{self.content[:50]}...', chunk='{self.chunk[:50] if self.chunk else ''}...')"

def split_markdown_by_heading(markdown_content: str, filename: str) -> list[DocNode]:
    """
    Splits markdown content into a list of documents based on the highest level heading present.
    Each document includes the identified heading and all content until the next
    heading of the same or higher level, or the end of the content.
    Then, further splits these documents into new DocNodes, each containing two sentences.
    """
    # Dynamically determine the highest level heading (lowest number of #)
    min_heading_level = 7 # Markdown supports up to 6 levels, 7 as initial max

    # Find all heading lines
    heading_matches = re.findall(r'^(#+)\s.*', markdown_content, re.MULTILINE)
    if heading_matches:
        for match in heading_matches:
            level = len(match)
            if level < min_heading_level:
                min_heading_level = level

    # If no headings are found, treat the entire content as a single document
    if min_heading_level == 7:
        base_doc_nodes = []
        if markdown_content.strip():
            base_doc_nodes.append(DocNode(content=markdown_content.strip(), index=0, filename=filename))
    else:
        # Now, find only the headings that match the min_heading_level
        target_heading_pattern = r'^' + r'#' * min_heading_level + r'\s.*'
        target_heading_matches = list(re.finditer(target_heading_pattern, markdown_content, re.MULTILINE))

        base_doc_nodes = []
        current_base_doc_index = 0
        # Handle content before the first target heading, only if there are target headings
        if target_heading_matches:
            first_heading_start = target_heading_matches[0].start()
            initial_content = markdown_content[:first_heading_start].strip()
            if initial_content:
                base_doc_nodes.append(DocNode(content=initial_content, index=current_base_doc_index, filename=filename))
                current_base_doc_index += 1

            # Iterate through the target headings to create documents
            for i in range(len(target_heading_matches)):
                start_index = target_heading_matches[i].start()
                
                # Determine the end index for the current document
                if i + 1 < len(target_heading_matches):
                    end_index = target_heading_matches[i+1].start()
                else:
                    end_index = len(markdown_content) # Last document goes to the end of the content

                document_content = markdown_content[start_index:end_index].strip()
                if document_content:
                    base_doc_nodes.append(DocNode(content=document_content, index=current_base_doc_index, filename=filename))
                    current_base_doc_index += 1   
        else:
            # If min_heading_level was updated but no target headings were found (unlikely but for safety)
            # or if min_heading_level was 7 and this path is reached (should be handled by the first if)
            # treat the entire content as a single document if it's not empty
            if markdown_content.strip():
                base_doc_nodes.append(DocNode(content=markdown_content.strip(), index=0, filename=filename))
        
    return base_doc_nodes

def chunk_for_embedding(doc_nodes: list[DocNode]) -> list[DocNode]:
    """
    Takes a list of DocNode objects and returns new DocNode objects
    with the 'chunk' field set to the first line of the node's content.
    """
    chunked_doc_nodes = []
    for doc_node in doc_nodes:
        lines = split_text_into_chunks(doc_node.content,2);
        for line in lines:
            # Create a new DocNode instance with the chunk field populated
            chunked_doc_nodes.append(DocNode(
                content=doc_node.content,
                index=doc_node.index,
                filename=doc_node.filename,
                metadata=doc_node.metadata,
                chunk=line
            ))
    return chunked_doc_nodes

def split_text_into_lines(text: str) -> list[str]:
    return text.splitlines()

def split_text_into_chunks(text: str, chunk_size: int) -> list[str]:
    if chunk_size < 1:
        raise ValueError("Chunk size must be 1 or greater.")
        
    lines = split_text_into_lines(text)
    
    chunks = []
    num_lines = len(lines)
    
    for i in range(0, num_lines, chunk_size):
        line_slice = lines[i:i + chunk_size]
        
        chunk_content = " ".join(line_slice)
        
        if chunk_content:
            chunks.append(chunk_content)
            
    return chunks

if __name__ == "__main__":
    # pdf_file = "Plans_857_857Brochure.pdf"
    # print(f"Loading PDF: {pdf_file}")
    # content = load_pdf_with_garakPDFparser(pdf_file)

    # if content and not content.startswith("Error"):
    #     documents = split_markdown_by_heading(content, pdf_file)
    #     documents = chunk_for_embedding(documents)
    #     print("\n--- Split Documents ---")
    #     for i, doc_node in enumerate(documents):
    #          insert_data("specs", doc_node)
    #     print(f"\nTotal number of documents: {len(documents)}")
    search_data("specs")

  

    # result = lx.extract(
    # text_or_documents=content,
    # prompt_description="list the annuity options as json",
    # examples=[],
    # model_id="gemini-2.5-flash",
    # api_key="AIzaSyB7rF0pm-loKZuozgD8T2gi82Rwu0_UOlc"
    # )
