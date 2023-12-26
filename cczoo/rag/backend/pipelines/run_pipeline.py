from haystack import Pipeline
from pathlib import Path
from haystack.nodes.prompt import PromptNode, PromptModel
from haystack import Document
import logging
import time
logging.basicConfig(format="%(levelname)s - %(name)s -  %(message)s", level=logging.WARNING)
logging.getLogger("haystack").setLevel(logging.INFO)
#prompt_node = PromptNode("EleutherAI/gpt-j-6B")
#prompt_node = PromptNode()
#result = prompt_node("What is the capital of Germany?")
#result = prompt_node.prompt(prompt_template='question-answering', 
#          documents=[Document("Berlin is the capital of Germany."), Document("Paris is the capital of France.")],
#          query="What is the capital of Germany?")
#print(result)
pipeline = Pipeline.load_from_yaml(Path("rag.yaml"))
start=time.time()
PROMPT_TEXT = """Below is an instruction that describes a task, paired with an input that provides further context. Write response that appropriately completes the request.

        ### Instruction:
        You are this company CEO. Paraphrase the context as a detailed summary.

        ### Input:
        {join(documents)}

        ### Answer:"""
result = pipeline.run(query="Why is Q1 guide revenue down so much vs what said previously?", params={
    "Prompter": { "prompt_template": PROMPT_TEXT},
    "Retriever": {"top_k": 1},
    "Reranker": {"top_k": 1}
    })
cost = time.time() -start

print(f"Spent time = {cost}")
print(f"result={result}")

result = pipeline.run(query="Why is Q1 guide revenue down so much vs what said previously?", params={
    "Prompter": { "prompt_template": PROMPT_TEXT, "stream": True, "return_iterator": True},
    "Retriever": {"top_k": 1},
    "Reranker": {"top_k": 1}
    })
tokens = ""
for token in result["iterator"][0]:
    tokens += token
print(f"answer:{tokens}")

#pipeline = Pipeline.load_from_yaml(Path("rag.yaml"))
#result = pipeline.run(query="How about the financial report of intel in 2022 ?", params={"Retriever": {"top_k": 3}})
#print(f"result={result}")

#pipeline = Pipeline.load_from_yaml(Path("rag_prompt_gpt3.yaml"))
#pipeline.run(query="How about the financial report of intel in 2022 ?", params={"Retriever": {"top_k": 3}})
