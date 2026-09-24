"""Small-corpus BM25 and reciprocal rank fusion; no additional model dependency."""
from collections import Counter
import json
import math
import re

STOP = set('a an the and or for from to of in on with is are be as by this that it only simulator synthetic water grid nuclear normal day operation dispatch value unit quality good none null'.split())


def terms(text):
    # Keep exact plant tags, and also index their component words.
    words = re.findall(r'[a-z][a-z0-9_]+', text.lower())
    return [term for word in words for term in ([word]+word.split('_') if '_' in word else [word])
            if term not in STOP and len(term)>1]


def document_text(record):
    return '\n'.join([f"Synthetic {record['domain']} plant. {record['title']}.",
        'Process: '+ '; '.join(record['relationships']),
        'Relevant sensors: '+ ', '.join(record['sensors']), record['text']])


def search_text(query):
    data = json.loads(query)
    return ' '.join(str(data.get(key) or '') for key in
                    ['scenario', 'active_alarms', 'out_of_range', 'bad_quality', 'question'])


def bm25(documents, query, k1=1.2, b=0.75):
    counts = [Counter(terms(document_text(d))) for d in documents]
    if not counts:
        return []
    lengths = [sum(c.values()) for c in counts]
    average = sum(lengths)/len(lengths) or 1
    scores = [0.]*len(documents)
    for term in set(terms(query)):
        frequency = sum(term in c for c in counts)
        idf = math.log(1+(len(counts)-frequency+0.5)/(frequency+0.5))
        for i, counts_i in enumerate(counts):
            tf = counts_i[term]
            scores[i] += idf*tf*(k1+1)/(tf+k1*(1-b+b*lengths[i]/average))
    return scores


def fuse_rankings(*rankings, size, k=60):
    scores = [0.]*size
    for ranking in rankings:
        for rank, index in enumerate(ranking, 1):
            scores[index] += 1/(k+rank)
    return scores


def ranked(scores):
    return sorted((i for i, score in enumerate(scores) if score > 0), key=lambda i:(-scores[i],i))


def select_records(documents, scores, query, limit=2, budget=2400):
    signals = json.loads(query)
    exact = set(signals.get('out_of_range', [])) | set(signals.get('bad_quality', []))
    order = sorted(ranked(scores), key=lambda i: (-len(exact & set(documents[i]['sensors'])), -scores[i], documents[i]['id']))
    selected, seen = [], []
    for i in order:
        record = documents[i]
        words = set(terms(record['text']))
        if any(len(words & prior)/max(1,len(words | prior)) > .8 for prior in seen):
            continue
        candidate = {**record, 'score':round(scores[i],6)}
        if len(json.dumps(selected+[candidate],separators=(',',':'),ensure_ascii=True).encode()) > budget:
            continue
        selected.append(candidate); seen.append(words)
        if len(selected) >= limit:
            break
    return selected


def prompt_records(retrieval):
    # Full source/provenance metadata remains in the separate audit record.
    return {'authority':retrieval['authority'], 'scope':retrieval['scope'],
            'records':[{'id':r['id'],'title':r['title'],'text':r['text']} for r in retrieval['records']]}
