from haystack import Pipeline
from pathlib import Path
from haystack.nodes.prompt import PromptNode, PromptModel
from haystack import Document
import logging
import time
logging.basicConfig(format="%(levelname)s - %(name)s -  %(message)s", level=logging.WARNING)
logging.getLogger("haystack").setLevel(logging.INFO)

pipeline = Pipeline.load_from_yaml(Path("rag_mysql.yaml"))
start=time.time()
PROMPT_TEXT = """Below is an instruction that describes a task, paired with an input that provides further context. Write response that appropriately completes the request.

        ### Instruction:
        Suppose you are a professional computer engineer. Paraphrase the context as a detailed summary to answer the question: {join(documents)}.

        ### Input:
        context: {' - '.join([d.meta['answer'] for d in documents])};

        ### Answer:"""

result = pipeline.run(query="What is artificial intelligence?", params={
    "Prompter": { "prompt_template": PROMPT_TEXT},
    "Retriever": {"top_k": 1},
    "Reranker": {"top_k": 1}
    })
cost = time.time() -start

print(f"Spent time = {cost}")
print(f"result={result['answers'][0].answer.strip()}")
print(f"result={result}")

