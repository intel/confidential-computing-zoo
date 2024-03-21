from haystack.document_stores import FAISSDocumentStore
from haystack.nodes.retriever.dense import DensePassageRetriever
import os
import json
import sys

def gen_docstore_faiss():
    if os.path.isfile('/home/rag_data/faiss-index-so.faiss'):
        return
    else:
        ip_addr = sys.argv[1]
        username = sys.argv[2]
        password = sys.argv[3]
        sql_url = f"mysql://{username}:{password}@{ip_addr}/rag"
        document_store = FAISSDocumentStore(sql_url=sql_url,
                                            faiss_index_factory_str="HNSW",
                                            return_embedding=True,
                                            index='faiss')

        # write into document store
        print('write into documentstore...')
        with open('/home/rag_data/data.json', 'r') as file:
            docs = json.load(file)
        document_store.write_documents(docs, index='faiss')

        retriever = DensePassageRetriever(document_store=document_store,
                                            query_embedding_model="/home/rag_data/dpr-question_encoder-single-nq-base",
                                            passage_embedding_model="/home/rag_data/dpr-ctx_encoder-single-nq-base",
                                            max_seq_len_query=64,
                                            max_seq_len_passage=256,
                                            batch_size=16,
                                            use_gpu=True,
                                            embed_title=True,
                                            use_fast_tokenizers=True)
        document_store.update_embeddings(retriever, index='faiss')
        document_store.save('/home/rag_data/faiss-index-so.faiss')

if __name__ == "__main__":
    gen_docstore_faiss()

