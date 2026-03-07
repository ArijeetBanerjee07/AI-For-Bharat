import os
import json
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

def batch_process_markdowns(input_dir="data/markdowns", output_dir="data/chunks"):
    # 1. Ensure the output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # 2. Define the markdown hierarchy
    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
    ]

    markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
    
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1200,
        chunk_overlap=150, 
        separators=["\n\n", "\n", ".", " ", ""]
    )

    # 3. Iterate through all .md files
    for filename in os.listdir(input_dir):
        if filename.endswith(".md"):
            file_path = os.path.join(input_dir, filename)
            
            with open(file_path, 'r', encoding='utf-8') as f:
                markdown_document = f.read()

            # Perform the semantic split
            md_header_splits = markdown_splitter.split_text(markdown_document)

            # Add generic metadata (you can expand this logic if needed)
            for split in md_header_splits:
                split.metadata["source_document"] = filename

            # Perform the secondary character-based split
            final_chunks = text_splitter.split_documents(md_header_splits)

            # 4. Prepare the data for JSON serialization
            chunks_data = []
            for index, chunk in enumerate(final_chunks):
                chunks_data.append({
                    "chunk_id": f"{filename.replace('.md', '')}_chunk_{index}",
                    "content": chunk.page_content,
                    "metadata": chunk.metadata
                })

            # 5. Save the chunks to a JSON file in the output directory
            output_filename = filename.replace(".md", "_chunks.json")
            output_path = os.path.join(output_dir, output_filename)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(chunks_data, f, indent=4, ensure_ascii=False)
            
            print(f"✅ Processed {filename}: Generated {len(final_chunks)} chunks -> Saved to {output_filename}")

if __name__ == "__main__":
    batch_process_markdowns()