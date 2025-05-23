import logging
import os
from pathlib import Path
import re

import torch
from lxml import etree

from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
# from langchain.vectorstores import Chroma
from langchain_community.vectorstores import Chroma
# from langchain.embeddings import HuggingFaceEmbeddings # deprecated
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.prompts import PromptTemplate
from langchain.chains import RetrievalQA
# from langchain_groq import ChatGroq
from IPython.display import Markdown, display

logger = logging.Logger(__file__)
logger.setLevel(logging.DEBUG)

# -*- coding: utf-8 -*-
"""RevLit_Part2_RAG_LLM.ipynb

* author @Shabnam Barbhuiya and ...

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1RteHNh-ZROSSxja7tYRaKVCwT5wWOeVP

**Before using this Colab, please save a copy to your own Google Drive:
Click on “File” > “Save a copy in Drive”**

# **AI Assisted Literature Review Part II RAG/LLM**
# *A. Download Research Papers of interest*
# *B. Demo:Pre-process the downloaded file*   
# *C. Demo:Query your newly created RAG/LLM*


# This Colab notebook processes scientific papers, extracts metadata, creates a searchable vector database, and enables interactive question-answering using the Retrieval-Augmented Generation (RAG) approach with Groq's LLM. You can easily query the system for answers based on the processed documents.

### **WORKFLOW:**
* Install necessary libraries.
* Set Groq API Key
* Download research paper using [pygetpapers](https://github.com/petermr/pygetpapers)
* Parse XML Files to Markdown and Extract Metadata
* Create Vector Database
* Execute pipeline for Processing and Retrieval
* Query your newly created RAG/LLM

### **Step 1: Install dependencies**
* **pymupdf4llm:** Lightweight PDF processing for LLMs
* **langchain:** Framework for developing LLM-powered applications
* **chromadb:** Vector store for storing and querying embeddings
* **sentence-transformers:** For embedding sentences using transformer models
"""

# Install dependencies
# !pip install pygetpapers
# !pip install lxml
# !pip install langchain chromadb sentence-transformers
# !pip install -U langchain-community langchain-groq

"""### **Step 2: Set Groq API Key**
Groq’s LPU (Language Processing Unit) hardware enables real-time, low-latency responses from LLMs—ideal for interactive applications.

**Instructions:**
* Go to https://console.groq.com/

* Create an account if you don’t have one

* Generate your API token

* Copy and paste it when prompted below
"""

#  Set API Key
# import os, getpass
# os.environ["GROQ_API_KEY"] = getpass.getpass("🔐 Enter your Groq API Key: ")

"""### **Step 3: Download Research Papers**
Use *pygetpapers* to fetch research articles related to the keyword.
"""

# previous Download papers from EuropePMC saved it test/resources
# !pygetpapers --query '"phytochemical"' --xml --limit 15 --output /content/data_phyto --save_query

"""### **Step 4: Parse XML Files to Markdown and Extract Metadata**
Convert scientific articles (downloaded in XML format) into clean Markdown format and extract essential metadata like title, authors, and DOI.
"""
# constants
TITLE = "title"
AUTHORS = "authors"
DOI = "doi"
HTTPS_DOI_ORG = "https://doi.org/"
FULLTEXT_XML = "**/fulltext.xml"
CONTENT_DB = "content/db"
SCIENTIFIC_RAG_XML = "scientific_rag_xml"
META_LLAMA_3_8B = "meta-llama/Meta-Llama-3-8B"
STUFF = "stuff"
NAME = 'name'
GIVEN_NAMES = 'given-names'
SURNAME = 'surname'
FILENAME = "filename"

temp_dir = Path(Path(__file__).parent.parent, "temp")
if not temp_dir.exists():
    os.mkdir(temp_dir)


#  Parse XMLs to Markdown and extract metadata

def sanitize_filename(name):
    return re.sub(r'[/:"*?<>|\s]+', "_", name)


def parse_xml_to_markdown_with_metadata(xml_path):
    try:
        with open(xml_path, 'rb') as f:
            tree = etree.parse(f)

        metadata = {
            TITLE: "",
            AUTHORS: [],
            DOI: "",
        }

        # Extract title
        title_elem = tree.find(".//article-title")
        if title_elem is not None:
            full_title = title_elem.xpath("string()")  # ✅ gets entire text including inside nested tags
            metadata[TITLE] = full_title.strip()

        # Extract DOI
        doi_elem = tree.find(".//article-id[@pub-id-type='doi']")
        if doi_elem is not None and doi_elem.text:
            metadata[DOI] = HTTPS_DOI_ORG + doi_elem.text.strip()

        # Extract authors
        authors = []
        for contrib in tree.findall(".//contrib[@contrib-type='author']"):
            name = contrib.find(NAME)
            if name is not None:
                given = name.findtext(GIVEN_NAMES, default='')
                surname = name.findtext(SURNAME, default='')
                full_name = f"{given} {surname}".strip()
                if full_name:
                    authors.append(full_name)

        metadata[AUTHORS] = ", ".join(authors)

        # Extract body content
        sections = tree.xpath('//body//sec')
        text_parts = []

        for sec in sections:
            title = sec.findtext(TITLE)
            if title:
                text_parts.append(f"### {title.strip()}")
            paragraphs = sec.findall('p')
            for p in paragraphs:
                if p.text and p.text.strip():
                    text_parts.append(p.text.strip())

        markdown_text = "\n\n".join(text_parts)
        return markdown_text, metadata

    except Exception as e:
        print(f" Error parsing {xml_path.name}: {e}")
        return None  # Safe fallback to prevent unpacking error


def process_scientific_xmls(data_directory, output_directory):
    data_path = Path(data_directory)
    assert data_path.exists(), f"pdf input dir {data_path} must exist"
    output_path = Path(output_directory)
    output_path.mkdir(parents=True, exist_ok=True)

    metadata_records = []

    xml_files = list(data_path.glob(FULLTEXT_XML))
    for xml_file in xml_files:
        print(f" Processing {xml_file.name} ...")

        #  Skip empty XML files
        if xml_file.stat().st_size == 0:
            print(f" Skipped: {xml_file.name} (Empty file)")
            continue

        #  Safe call and unpack
        result = parse_xml_to_markdown_with_metadata(xml_file)
        if result is None:
            continue
        raw_text, metadata = result

        #  Save Markdown
        sanitized_name = sanitize_filename(xml_file.parent.name)
        final_filename = output_path / f"{sanitized_name}_final.md"

        if raw_text.strip():
            final_filename.write_text(raw_text, encoding="utf-8")
            print(f" Saved: {final_filename.name}")
            metadata[FILENAME] = final_filename.name
            metadata_records.append((final_filename, metadata))
        else:
            print(f" Skipped: {xml_file.name} (No extractable content)")

    return metadata_records


"""### **Step 5:Create Vector Database**
Process documents to store them as vectors, enabling question-answering with a retrieval system.
"""


#  Load and Chunk Documents with Metadata

def load_markdown_documents_with_metadata(metadata_records):
    documents = []
    for md_path, metadata in metadata_records:
        text = md_path.read_text(encoding="utf-8")
        if not text.strip():
            continue
        doc = Document(page_content=text, metadata=metadata)
        documents.append(doc)
    return documents


def hybrid_chunking(documents, threshold=3000):
    chunks = []
    for doc in documents:
        if len(doc.page_content.strip()) <= threshold:
            chunks.append(doc)
        else:
            splitter = RecursiveCharacterTextSplitter(chunk_size=1800, chunk_overlap=300)
            split_docs = splitter.split_documents([doc])
            for chunk in split_docs:
                chunk.metadata.update(doc.metadata)
            chunks.extend(split_docs)
    return chunks


def create_vector_database(chunks):
    embeddings = HuggingFaceEmbeddings(model_name="all-mpnet-base-v2")
    persist_dir = str(Path(temp_dir, CONTENT_DB))
    vector_db = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name=SCIENTIFIC_RAG_XML,
        persist_directory=persist_dir
    )
    return vector_db


def create_retrieval_chain(vector_db):
    # llm = ChatGroq(
    #     model="llama3-70b-8192",
    #     temperature=0.2,
    #     max_tokens=512,
    #     api_key=os.environ.get("GROQ_API_KEY")
    # )

    from transformers import pipeline

    llm_pipeline = pipeline(
        "text-generation",
        model=META_LLAMA_3_8B,
        device=0 if torch.cuda.is_available() else -1
    )

    def generate(prompt):
        return llm_pipeline(
            prompt,
            max_new_tokens=512,
            temperature=0.2)[0]["generated_text"]

    prompt_template = PromptTemplate.from_template(
        '''You are a very good research paper assistant. Use this context to provide 
        the following questions. You can use your knowledge if asked general bio and 
        chemistry related questions.

Context:
{context}

Question: {question}

Answer:'''
    )
    qa_chain = RetrievalQA.from_chain_type(
        llm=llm_pipeline,
        chain_type=STUFF,
        retriever=vector_db.as_retriever(search_kwargs={"k": 3}),
        return_source_documents=True,
        chain_type_kwargs={"prompt": prompt_template}
    )
    return qa_chain


"""### **Step 6: Execute pipeline for Processing and Retrieval**
Runs the entire pipeline from downloading scientific papers to processing them, creating a vector database, and setting up the question-answering system.
"""


# ✅ Execute Full Pipeline
# pdf_dir = "/content/data_phyto"
def main():
    pdf_dir = Path(Path(__file__).parent.parent, "test", "resources", "phytochemical")
    os.makedirs(pdf_dir, exist_ok=True)
    # markdown_dir = "/content/markdowns"
    markdown_dir = Path(Path(__file__).parent.parent, "temp", "markdowns")
    os.makedirs(markdown_dir, exist_ok=True)
    assert markdown_dir.exists(), f"markdown dir {markdown_dir} must exist"
    logger.info(f"input pdfs {pdf_dir}, output: {markdown_dir}")

    metadata_records = process_scientific_xmls(str(pdf_dir), str(markdown_dir))
    logger.info(f"found {len(metadata_records)} metadata_records")
    docs = load_markdown_documents_with_metadata(metadata_records)
    chunks = hybrid_chunking(docs)
    logger.info(f"created {len(chunks)} chunks")
    vector_db = create_vector_database(chunks)
    qa_chain = create_retrieval_chain(vector_db)
    logger.debug(" RAG System Ready.")

    """### **Step 7: Query your newly created RAG/LLM**
    Allow users to ask scientific questions and get answers based on the documents stored in the vector database
    ---
    ### Examples of the questions to be ask
    * What species are mentioned in this paper?
    * What are the key findings of the study {PAPER TITLE}?
    * What species are mentioned in this paper?
    * What compounds were isolated from the plant?
    * What experimental techniques were used in this paper {PAPER TITLE}?
    """

    #  Ask Questions
    while True:
        query = input("🧠 Ask a scientific question (or type 'quit'): ").strip()
        if query.lower() == "quit":
            break

        result = qa_chain.invoke(query)
        answer = result.get("result", "")

        # Display answer with wrapped formatting
        display(Markdown(f"###  Answer:\n\n{answer}"))

        # Format sources as clickable markdown links
        # Format sources with safe markdown titles
        source_lines = []
        for doc in result['source_documents']:
            title = doc.metadata.get(TITLE, "Untitled")
            title = re.sub(r"[()]", "", title)  # Remove parentheses that break markdown
            doi = doc.metadata.get("doi", "")
            source_lines.append(f"- [{title}]({doi})" if doi else f"- {title}")

        display(Markdown("** Sources:**\n" + "\n".join(source_lines)))

    """### In this Colab notebook, we built a scientific RAG (Retrieval-Augmented Generation) pipeline that extracts information from XML-formatted research papers focused on biodiversity, wildlife, phytochemicals, and conservation. We parsed these XMLs into structured Markdown, embedded them using all-mpnet-base-v2, and connected them to a powerful LLM (LLaMA3-70B via Groq). The assistant can now accurately answer questions about scientific names, compounds, study locations, methodologies, and research findings — all grounded in real literature.
    
    ###**References:**
    - Garg A, Smith-Unna R D and Murray-Rust P, (pygetpapers:
    A   Python   library   for   automated   retrieval   of   scientific
    literature,Journal  of  Open  Source  Software,7(75)(2022)4451. https://doi.org/10.21105/joss.04451
    
    - [groqcloud](https://groq.com/groqcloud/)
    """


if __name__ == "__main__":
    main()
