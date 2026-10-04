import pytest
from scripts.compare_cloudflare_water import request_for,extract
from scripts.water_alarm_benchmark import case


def test_comparison_preserves_prompt_and_budget():
    row=case(0,'valid')
    class Tokenizer:
        def apply_chat_template(self,messages,**kwargs):
            assert messages==row['payload']['messages']
            assert kwargs==dict(tokenize=False,add_generation_prompt=True,enable_thinking=False)
            return 'exact prompt'
    assert request_for(row,Tokenizer())==dict(prompt='exact prompt',raw=True,stream=False,max_tokens=256,temperature=0,seed=42)
    with pytest.raises(ValueError):request_for(case(0,'test'),Tokenizer())


def test_cloudflare_response_extraction_does_not_repair_model_output():
    assert extract({'success':True,'result':{'choices':[{'message':{'content':'invalid json'}}]}})=='invalid json'
    with pytest.raises(ValueError):extract({'success':False,'result':{}})


def test_raw_completion_extracts_exact_text():
    assert extract({'success':True,'result':{'choices':[{'text':'{"actions":[]}'}]}})=='{"actions":[]}'
