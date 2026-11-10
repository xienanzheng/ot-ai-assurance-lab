import pytest
from training.mlx_experiment import tokenize_example, choose_checkpoint, summarize, write_new, verify_binding

class Tokenizer:
    def encode(self, text, add_special_tokens=False): return [ord(x) for x in text]
    def apply_chat_template(self, messages, **kwargs):
        assert kwargs['enable_thinking'] is False
        prefix=[1,2,3]
        return prefix if kwargs.get('add_generation_prompt') else prefix+[ord(messages[-1]['content']),9]


def test_template_and_mask():
    r=tokenize_example(Tokenizer(), [{'role':'user','content':'x'}], 'A')
    assert r=={'prompt_tokens':[1,2,3], 'full_tokens':[1,2,3,65,9], 'prompt_length':3}


def test_rejections():
    with pytest.raises(ValueError):tokenize_example(Tokenizer(), [], 'Z')
    with pytest.raises(ValueError):tokenize_example(Tokenizer(), [], 'A',4)
    class Bad(Tokenizer):
        def encode(self,*a,**k):return [4,5]
    with pytest.raises(ValueError):tokenize_example(Bad(), [], 'A')
    class Prefix(Tokenizer):
        def apply_chat_template(self,messages,**kw):return [0] if kw.get('add_generation_prompt') else [1,65]
    with pytest.raises(ValueError):tokenize_example(Prefix(), [], 'A')


def test_collision_and_binding(tmp_path):
    p=tmp_path/'x';write_new(p,{'x':1})
    with pytest.raises(FileExistsError):write_new(p,{})
    with pytest.raises(ValueError):verify_binding({'a':1},{'a':2})


def test_selection_validation_only():
    rows=[{'step':128,'split':'validation','summary':{'protection_misses':0,'supported_correct':20,'decision_correct':30}}, {'step':64,'split':'validation','summary':{'protection_misses':0,'supported_correct':20,'decision_correct':30}}]
    assert choose_checkpoint(rows)['step']==64
    rows[0]['split']='test'
    with pytest.raises(ValueError):choose_checkpoint(rows)


def test_failures_retained_and_degenerate_readiness():
    rows=[{'expected_status':s,'decision_correct':False,'supported_reason':False,'protection_miss':s=='escalate','latency_seconds':1,'error':'unavailable'} for s in ('hold','adjust','escalate')]
    r=summarize(rows)
    assert r['count']==3 and r['classes']['hold']['count']==1 and r['unavailable']==3
    from training.mlx_experiment import readiness
    assert not readiness(r,r)['ready']


@pytest.mark.parametrize('always', ['hold','escalate'])
def test_complete_degenerate_policy_fails_quality_gates(always):
    from training.mlx_experiment import readiness
    # Thirty complete cases allow +4 improvement; no unavailable gate masks quality.
    rows=[dict(expected_status=status,decision_correct=status==always,
               supported_reason=status==always,protection_miss=False,
               latency_seconds=1,error=None)
          for status in ('hold','adjust','escalate') for _ in range(10)]
    base=[dict(row,decision_correct=False,supported_reason=False) for row in rows]
    result=readiness(summarize(rows),summarize(base))
    assert result['checks']['complete'] and result['checks']['improvement']
    assert result['checks']['no_protection_misses']
    assert result['checks']['median_seconds'] and result['checks']['p95_seconds']
    assert not result['checks']['status_target']
    assert not result['checks']['supported_reason']
    assert result['checks']['holds'] == (always=='hold')
    assert not result['ready']


def test_only_label_loss_positions():
    from training.mlx_experiment import training_item
    t=tokenize_example(Tokenizer(), [], 'A')
    tokens,position=training_item(t)
    assert tokens==[1,2,3,65] and position==3
    assert tokens[position]==65 and tokens[position-1]==3


def test_unknown_completion_boundary():
    class Boundary(Tokenizer):
        def apply_chat_template(self,messages,**kw):
            return [1,2] if kw.get('add_generation_prompt') else [1,2,99,65]
    with pytest.raises(ValueError):tokenize_example(Boundary(), [], 'A')


def test_prepare_freezes_loader_and_drift(tmp_path,monkeypatch):
    import training.mlx_experiment as e
    monkeypatch.setattr(e.importlib.metadata,'version',lambda name:'cpu-fixture')
    model=tmp_path/e.PIN;monkeypatch.setattr(e,'PINNED_MODEL',model);model.mkdir();(model/'tokenizer.json').write_text('{}')
    root=tmp_path/'new-experiment'
    e.run_stage('prepare',root,model)
    assert len(e.read(root/'test-frozen.json'))==96
    assert set(p.name for p in (root/'loader').iterdir())=={'train.jsonl','valid.jsonl'}
    e.checked_binding(root,model)
    with pytest.raises(FileExistsError):e.run_stage('prepare',root,model)
    frozen=root/'test-frozen.json';frozen.write_text(frozen.read_text()+' ')
    with pytest.raises(ValueError):e.checked_binding(root,model)


def test_test_requires_selection_and_rejects_drift(tmp_path,monkeypatch):
    import training.mlx_experiment as e
    monkeypatch.setattr(e.importlib.metadata,'version',lambda name:'cpu-fixture')
    model=tmp_path/e.PIN;monkeypatch.setattr(e,'PINNED_MODEL',model);model.mkdir();(model/'config.json').write_text('{}')
    root=tmp_path/'new-experiment';e.run_stage('prepare',root,model)
    calls=[];monkeypatch.setattr(e,'evaluate',lambda *a,**k:calls.append(a))
    with pytest.raises(FileNotFoundError):e.run_stage('test',root,model)
    e.write_new(root/'selection.json',{'binding':e.fingerprint(e.checked_binding(root,model))})
    (model/'config.json').write_text('{"changed":true}')
    with pytest.raises(ValueError):e.run_stage('test',root,model)
    assert calls==[]


def test_selection_priorities():
    from training.mlx_experiment import choose_checkpoint
    def row(step,miss,support,decision):return dict(step=step,split='validation',summary=dict(protection_misses=miss,supported_correct=support,decision_correct=decision))
    assert choose_checkpoint([row(64,1,48,48),row(128,0,1,1)])['step']==128
    assert choose_checkpoint([row(64,0,20,40),row(128,0,21,30)])['step']==128
    assert choose_checkpoint([row(64,0,20,30),row(128,0,20,31)])['step']==128


def test_source_drift(tmp_path,monkeypatch):
    import training.mlx_experiment as e
    monkeypatch.setattr(e.importlib.metadata,'version',lambda name:'cpu-fixture')
    model=tmp_path/e.PIN;monkeypatch.setattr(e,'PINNED_MODEL',model);model.mkdir()
    root=tmp_path/'new-experiment';e.run_stage('prepare',root,model)
    monkeypatch.setattr(e,'source_hashes',lambda:{'modified.py':'new-hash'})
    with pytest.raises(ValueError):e.checked_binding(root,model)


@pytest.mark.parametrize('mutation',['config','completion'])
def test_adapter_config_drift_rejected_before_validation(tmp_path,monkeypatch,mutation):
    import training.mlx_experiment as e
    root=tmp_path;adapters=root/'adapters';adapters.mkdir()
    config=adapters/'adapter_config.json';e.write_new(config,{'lora_parameters':{'scale':20}})
    checkpoints={}
    for step in (64,128):
        p=adapters/f'{step:07d}_adapters.safetensors';p.write_bytes(b'weights');checkpoints[str(step)]=e.sha(p)
    current={'fixture':'binding'}
    e.write_new(root/'training.complete.json',{'checkpoints':checkpoints,'binding':e.fingerprint(current),'adapter_config_sha256':e.sha(config)})
    monkeypatch.setattr(e,'checked_binding',lambda *a:current)
    calls=[];monkeypatch.setattr(e,'evaluate',lambda *a,**k:calls.append(a))
    if mutation=='config':config.write_text('{"lora_parameters":{"scale":40}}')
    else:
        p=root/'training.complete.json';record=e.read(p);record['binding']='changed';p.write_text(__import__('json').dumps(record))
    with pytest.raises(ValueError):e.run_stage('validate',root,tmp_path/'model')
    assert not calls and not (root/'checkpoint-64').exists()


def report_fixture(root,e):
    current={'fixture':'binding'};bound=e.fingerprint(current)
    e.write_new(root/'selection.json',{'step':64,'binding':bound})
    selection_hash=e.sha(root/'selection.json')
    e.write_new(root/'test.started.json',{'selection_sha256':selection_hash,'binding':bound})
    cases=[{'id':'test-0000'},{'id':'test-0001'}];e.write_new(root/'test-frozen.json',cases)
    rows=[dict(id=c['id'],expected_status='hold',decision_correct=True,supported_reason=True,protection_miss=False,latency_seconds=1,error=None) for c in cases]
    hashes={}
    for name in ('base','selected'):
        p=root/f'{name}-test.json'
        e.write_new(p,dict(name=name,split='test',binding=bound,rows=rows,summary=e.summarize(rows)))
        hashes[p.name]=e.sha(p)
    e.write_new(root/'test.complete.json',{'selection_sha256':selection_hash,'binding':bound,'results':hashes})
    return current


@pytest.mark.parametrize('mutation',['selection','summary','order','count','identity','binding','completion','hash'])
def test_report_rejects_provenance_drift(tmp_path,monkeypatch,mutation):
    import training.mlx_experiment as e
    current=report_fixture(tmp_path,e);monkeypatch.setattr(e,'checked_binding',lambda *a:current)
    if mutation=='selection':
        p=tmp_path/'selection.json';r=e.read(p);r['step']=128;p.write_text(__import__('json').dumps(r))
    elif mutation=='completion':
        p=tmp_path/'test.complete.json';r=e.read(p);r['binding']='changed';p.write_text(__import__('json').dumps(r))
    else:
        p=tmp_path/'selected-test.json';r=e.read(p)
        if mutation=='summary':r['summary']['decision_correct']=999
        if mutation=='order':r['rows'].reverse()
        if mutation=='count':r['rows'].pop()
        if mutation=='identity':r['name']='base'
        if mutation=='hash':r['load_seconds']=999
        if mutation=='binding':r['binding']='changed'
        p.write_text(__import__('json').dumps(r))
        # Rebind file hash to exercise semantic checks independently of content hash.
        if mutation!='hash':
            complete=tmp_path/'test.complete.json';record=e.read(complete);record['results'][p.name]=e.sha(p);complete.write_text(__import__('json').dumps(record))
    with pytest.raises(ValueError):e.run_stage('report',tmp_path,tmp_path/'model')
    assert not (tmp_path/'summary.json').exists()


def test_report_validates_and_recomputes(tmp_path,monkeypatch):
    import training.mlx_experiment as e
    current=report_fixture(tmp_path,e);monkeypatch.setattr(e,'checked_binding',lambda *a:current)
    e.run_stage('report',tmp_path,tmp_path/'model')
    assert e.read(tmp_path/'summary.json')['candidate']['count']==2


def stub_evaluation(root, monkeypatch, failure, failure_phase='forward'):
    """Install CPU-only modules; never import MLX or load model weights."""
    import sys
    from types import ModuleType, SimpleNamespace
    import training.mlx_experiment as e
    calls={'loads':0,'forwards':0}
    class Values:
        def __getitem__(self,key):return self
        def tolist(self):return [1.0]
    class Model:
        def parameters(self):return []
        def __call__(self,tokens):
            calls['forwards']+=1
            if calls['forwards']==2 and failure_phase=='forward':raise failure
            return Values()
    def load(*args,**kwargs):
        calls['loads']+=1
        return Model(),Tokenizer()
    mlx=ModuleType('mlx');core=ModuleType('mlx.core');lm=ModuleType('mlx_lm')
    core.array=lambda value:value;core.eval=lambda *args:None;core.take=lambda *args:Values()
    mlx.core=core;lm.load=load
    for name,module in [('mlx',mlx),('mlx.core',core),('mlx_lm',lm)]:monkeypatch.setitem(sys.modules,name,module)
    monkeypatch.setattr(e,'checked_binding',lambda *args:{'fixture':'cpu'})
    monkeypatch.setattr(e,'make_options',lambda context:{'A':{}})
    monkeypatch.setattr(e,'messages_for',lambda context:[])
    def decode(*args):
        if failure_phase=='decode':raise failure
        return SimpleNamespace(model_dump=lambda:{})
    monkeypatch.setattr(e,'decode_choice',decode)
    monkeypatch.setattr(e,'score',lambda *args:dict(decision_correct=True,supported_reason=True,protection_miss=False))
    e.write_new(root/'test-frozen.json',[dict(id=f'case-{i}',context={},options={'A':{}},messages=[],label='A',
        expected=dict(status='hold',reason_code='in_band',protection_required=False)) for i in range(3)])
    return e,calls


@pytest.mark.parametrize('failure', [MemoryError('simulated resource exhaustion'),
    RuntimeError('[metal::malloc] Resource limit (simulated) exceeded'),
    RuntimeError('Metal command buffer execution failed')])
def test_resource_failure_flushes_row_and_aborts_test_stage(tmp_path,monkeypatch,failure):
    e,calls=stub_evaluation(tmp_path,monkeypatch,failure)
    adapter=tmp_path/'checkpoint-64';adapter.mkdir();(adapter/'config').write_text('fixture')
    e.write_new(tmp_path/'selection.json',dict(step=64,binding=e.fingerprint({'fixture':'cpu'}),validation={},
        adapter={'config':e.sha(adapter/'config')}))
    with pytest.raises(type(failure),match=__import__('re').escape(str(failure))):
        e.run_stage('test',tmp_path,tmp_path/'model')
    assert calls=={'loads':1,'forwards':2} # Warm-up, failed case; no selected load.
    rows=[__import__('json').loads(line) for line in (tmp_path/'base-test.rows.jsonl').read_text().splitlines()]
    assert len(rows)==1 and rows[0]['id']=='case-0' and rows[0]['error']=='unavailable'
    assert type(failure).__name__ in rows[0]['detail']
    assert (tmp_path/'test.started.json').exists() and (tmp_path/'base-test.started.json').exists()
    for name in ('base-test.json','selected-test.started.json','test.complete.json'):
        assert not (tmp_path/name).exists()
    evidence=e.read(tmp_path/'base-test.failed.json')
    assert evidence['attempted']==1 and evidence['total']==3 and evidence['unattempted']==2
    with pytest.raises(FileExistsError):e.run_stage('test',tmp_path,tmp_path/'model')
    assert calls=={'loads':1,'forwards':2}


@pytest.mark.parametrize('failure,phase',[(ValueError('Nonfinite choice logits'),'forward'),
    (RuntimeError('invalid individual output'),'decode')])
def test_case_output_errors_remain_recordable(tmp_path,monkeypatch,failure,phase):
    e,calls=stub_evaluation(tmp_path,monkeypatch,failure,phase)
    result=e.evaluate(tmp_path,tmp_path/'model','test','base')
    assert calls=={'loads':1,'forwards':4}
    assert len(result['rows'])==3 and result['rows'][0]['error']=='unavailable'
    assert (tmp_path/'base-test.json').exists() and not (tmp_path/'base-test.failed.json').exists()


def test_backend_failure_prevents_later_checkpoint_and_selection(tmp_path,monkeypatch):
    e,calls=stub_evaluation(tmp_path,monkeypatch,RuntimeError('[metal::malloc] Resource limit (simulated) exceeded'))
    # Reuse the same CPU cases as validation; no historical artifacts are touched.
    (tmp_path/'test-frozen.json').rename(tmp_path/'validation-frozen.json')
    monkeypatch.setattr(e,'verify_training_completion',lambda *args:{})
    checkpoints=[]
    def checkpoint(root,step,current):
        checkpoints.append(step)
        return root/f'checkpoint-{step}'
    monkeypatch.setattr(e,'checkpoint_dir',checkpoint)
    with pytest.raises(RuntimeError,match='Resource limit'):
        e.run_stage('validate',tmp_path,tmp_path/'model')
    assert calls=={'loads':1,'forwards':2} and checkpoints==[64]
    assert (tmp_path/'validation.started.json').exists()
    assert (tmp_path/'step-64-validation.rows.jsonl').exists()
    assert not (tmp_path/'step-64-validation.json').exists()
    assert not (tmp_path/'selection.json').exists()
