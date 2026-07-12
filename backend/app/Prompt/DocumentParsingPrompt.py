from langchain_core.prompts import PromptTemplate

# Image caption prompt template
image_caption_prompt = PromptTemplate(
    input_variables=["image_description"],
    template="""
You are creating metadata for a Retrieval-Augmented Generation (RAG) system.

Analyze the following image and generate a detailed description that will maximize semantic search quality.

Your description should include:
- The type of image (photo, diagram, chart, graph, flowchart, screenshot, logo, etc.)
- All visible objects and entities
- Important labels, titles, headings, legends, axes, and annotations
- Relationships between objects
- Any numbers, measurements, dates, percentages, or statistics
- Any text appearing in the image (OCR)
- The overall purpose or meaning of the image
- Important keywords and technical terminology

Write as one detailed paragraph.
Do not mention image quality or colors unless they are important.

Image:
data:image/png;base64,{image_description}
"""
)

# Table caption prompt template
table_caption_prompt = PromptTemplate(
    input_variables=["table_description"],
    template="""
You are creating metadata for a Retrieval-Augmented Generation (RAG) system.

Analyze the following table and produce a retrieval-friendly description.

Include:
- What the table represents
- Column names
- Row categories
- Key values and trends
- Highest and lowest values
- Important comparisons
- Units, dates, percentages, currencies if present
- Important keywords
- A concise summary of the information

Return one detailed paragraph suitable for semantic embedding.

Table:
{table_description}
"""
)
