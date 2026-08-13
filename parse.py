import json
d = json.load(open('z24.json', encoding='utf-8'))
for w in d.get('results', []):
    print(w['cited_by_count'], '|', w['year'], '|', w['title'][:95])
