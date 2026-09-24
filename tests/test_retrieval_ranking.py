import json
from services.supervisor.app.retrieval_ranking import bm25, fuse_rankings, prompt_records, ranked
from services.supervisor.app import plant_knowledge as knowledge


def test_exact_sensor_tag_ranks_relevant_document():
    docs=[r for r in knowledge.load_pack()['records'] if r['domain']=='water']
    scores=bm25(docs,'chlorine_ct_mg_min_l contact time')
    assert docs[ranked(scores)[0]]['id']=='water.disinfection'


def test_rank_fusion_ignores_incompatible_raw_score_scales():
    assert fuse_rankings([1,0],[1,2],size=3)[1] > fuse_rankings([1,0],[1,2],size=3)[0]


def test_no_matching_keyword_returns_no_results():
    docs=knowledge.load_pack()['records']
    assert ranked(bm25(docs,'unrelated pineapple recipe'))==[]


def test_compact_prompt_excludes_scoring_and_source_metadata():
    record=knowledge.load_pack()['records'][0]
    full={'authority':'context_only','scope':'synthetic_simulator_only','records':[record]}
    compact=prompt_records(full)
    assert len(json.dumps(compact)) < len(json.dumps(full))
    assert compact['records'][0]['text']==record['text']
    assert set(compact['records'][0])=={'id','title','text'}
