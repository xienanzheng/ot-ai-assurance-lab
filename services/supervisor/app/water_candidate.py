"""Approval-bound, local-only water candidate inference. Never submits controls."""
import hashlib
import json
import os
from pathlib import Path
from time import perf_counter
import httpx
from shared.water_study_provenance import evaluation_identity,sha256
from shared.models import ControlProposal,SetpointChanges
from .water_alarm import build_payload,validate_response
from .agent_audit import create_audit,update_audit

ROOT=next((p for p in Path(__file__).resolve().parents if (p/"shared").is_dir()), Path("/app"))
REVISION='4dcb3d101c2a062e5c1d4bb173588c54ea6c4d25'
ENDPOINT='http://127.0.0.1:18784'


def approval():
    if os.getenv('HOSTED_MODE')=='true':raise ValueError('Candidate is local-only')
    path=Path(os.getenv('WATER_ALARM_ACCEPTANCE_PATH',str(ROOT/'artifacts/posttraining/water-alarms-v2/acceptance.json')))
    try:
        report=json.loads(path.read_text()); summary=report['test']
        latency=report['candidate_latency'];base=report['base_latency']
        required={'critical','structured','references','assessments','noncritical','median_latency','p95_latency'}
        if not (report['approved'] is True and report['shadow_only'] is True and report['base_revision']==REVISION
                and required<=report['acceptance'].keys() and all(report['acceptance'][k] is True for k in required)
                and summary['count']==1000 and summary['critical_count']==500 and summary['critical_correct']==500
                and summary['valid']>=990 and summary['reference_errors']==0 and summary['supported_assessments']>=950
                and summary['other_count']==500 and summary['other_correct']>=475
                and 0<latency['warm_median_seconds']<=base['warm_median_seconds']
                and 0<latency['warm_p95_seconds']<=base['warm_p95_seconds']):
            raise ValueError('Water candidate did not pass acceptance checks')
        adapter=Path(report['adapter_path']).resolve()
        digest=hashlib.sha256((adapter/'adapters.safetensors').read_bytes()).hexdigest()
        if digest!=report['adapter_sha256']:raise ValueError('Adapter differs from evaluated weights')
        manifest=path.parent/'manifest.json'
        if hashlib.sha256(manifest.read_bytes()).hexdigest()!=report['dataset_manifest_sha256']:
            raise ValueError('Evaluation dataset manifest changed')
        identity=evaluation_identity(path.parent,REVISION,adapter)
        if report.get('evaluation_identity')!=identity or report.get('adapter_config_sha256')!=identity['adapter_config_sha256']:
            raise ValueError('Evaluation identity does not match candidate files')
        if summary.get('identity')!=identity or latency.get('identity')!=identity:
            raise ValueError('Candidate metrics are not bound to evaluated identity')
        if base.get('identity')!=evaluation_identity(path.parent,REVISION):
            raise ValueError('Base latency identity mismatch')
        results=path.parent/f"{report['candidate']}-test.jsonl"
        if summary.get('results_sha256')!=sha256(results):
            raise ValueError('Test results changed')
        return {**report,'adapter_path':str(adapter),'dataset_path':str(path.parent)}
    except (OSError,KeyError,TypeError,json.JSONDecodeError) as exc:
        raise ValueError('No complete passing water candidate evaluation is available') from exc


def verify_server_identity(body,report):
    if body.get('identity')!=report['evaluation_identity']:
        raise ValueError('Running service identity differs from approved candidate')


async def status():
    try:
        report=approval()
        async with httpx.AsyncClient(timeout=2) as client:
            response=await client.get(ENDPOINT+'/identity');response.raise_for_status()
            verify_server_identity(response.json(),report)
        return {'available':True,'shadow_only':True,'name':'Water alarm candidate','candidate':report['candidate']}
    except (ValueError,httpx.HTTPError):
        return {'available':False,'shadow_only':True,'name':'Water alarm candidate','reason':'Passing evaluation and local candidate service required'}


async def propose(context):
    from scripts.water_alarm_server import model_id
    report=approval()
    payload=build_payload(context['plant'],context['plc']['setpoints'],context['plc'].get('control_state',{}))
    request={'model':model_id(report['evaluation_identity']),'messages':payload['messages'],'temperature':0,'max_tokens':256,
             'chat_template_kwargs':{'enable_thinking':False}}
    identifier=create_audit('water',request)
    update_audit(identifier,shadow_only=True,evaluate_only=True,provider='qwen-water-candidate',model_name='Qwen3 4B water alarm adapter',
                 before=context,record_type='decision',applied=False,model_revision=REVISION,adapter_sha256=report['adapter_sha256'],
                 dataset_manifest_sha256=report['dataset_manifest_sha256'],sop_version=payload['context']['sop_version'],
                 sop_sha256=payload['context']['sop_sha256'],runtime='MLX',status='inferencing')
    start=perf_counter()
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response=await client.post(ENDPOINT+'/v1/chat/completions',json=request);response.raise_for_status()
        body=response.json();verify_server_identity(body,report)
        content=body['choices'][0]['message']['content']
        parsed=validate_response(json.loads(content),payload)
        proposal=ControlProposal(changes=SetpointChanges(**{a.target:a.value for a in parsed.actions}),
            confidence=parsed.confidence,expected_effect=parsed.reason,explanation=parsed.reason,
            episode_status=parsed.episode_status,alarm_assessment=parsed.alarm_assessment.model_dump() if parsed.alarm_assessment else None)
        proposal.decision_id=identifier
        update_audit(identifier,response=body,latency_seconds=perf_counter()-start,proposal=proposal.model_dump(mode='json'))
        return proposal,identifier
    except Exception as exc:
        update_audit(identifier,status='failed',applied=False,error=str(exc),latency_seconds=perf_counter()-start)
        raise
