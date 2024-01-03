import re
import json

with open('/home/rag_data/data.txt', 'r') as file:
    data = file.read()

sections = re.split(r'\n\n', data)

result = []
for section in sections:
    if section:
        lines = section.split('\n')
        question = lines[0].replace('Question: ', '').strip()
        answer = lines[1].replace('Answer: ', '').strip()

        item = {
            "content": question,
            "meta": {
                "answer": answer
            }
        }
        result.append(item)

with open('/home/rag_data/data.json', 'w') as output_file:
    json.dump(result, output_file, indent=4)

