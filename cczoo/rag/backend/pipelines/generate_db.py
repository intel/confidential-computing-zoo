from haystack.document_stores.elasticsearch import ElasticsearchDocumentStore
import json


db_mapping = {"mappings": {
                "properties": {
                    "content":      { "type": "text"  },
                    "questions":    { "type": "text" },
                    "title":        { "type": "text"},
                } }
}

document_store = ElasticsearchDocumentStore(host="localhost", username="", password="",custom_mapping=db_mapping,
                                            index="document")


with open('data.json') as json_file:
    parsed_json = json.load(json_file)

docs = []
for item in parsed_json:
    question = '\n'.join(item['query'])
    answer = '\n'.join(item['sentences'])
    print(question)
    print(answer)
    title = item['title']
    doc = {'content': answer, 'title': title, 'questions': question}
    docs.append(doc)
document_store.write_documents(docs)
