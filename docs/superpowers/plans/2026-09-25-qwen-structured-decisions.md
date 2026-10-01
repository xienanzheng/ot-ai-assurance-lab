# Qwen Structured Decisions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make local and Cloudflare-hosted Qwen return a JEV-style typed decision (assessment → decision → chosen bounded action) so that a fault scenario can no longer produce a schema-valid proposal whose `changes` are all null.

**Architecture:** Add a third inference profile, `structured`. The server builds a menu of bounded candidate moves (half and full max step up/down per target, clipped to range) and sends it with the compacted state. Qwen must fill a flat, `$ref`-free schema: `plant_status`, `key_findings`, `decision` (`adjust`/`hold`/`escalate`) and `selected_actions` (candidate ids only). The server rejects contradictions (such as `adjust` with no action), makes one repair request, and converts the result into the existing `ControlProposal` / `InfrastructureProposal` so the independent `SafetyGate` and the audit path stay unchanged.

**Tech Stack:** Python 3.12, Pydantic v2, httpx, FastAPI supervisor, Ollama `/api/chat` with `format` JSON schema, Cloudflare Workers AI `@cf/qwen/qwen3-30b-a3b-fp8` via `deploy/cloudflare-live/policy.mjs`, pytest, `node --test`.

**Spec:** No separate spec document. This plan argues from the diagnosis below, which was made on 25 September 2026 against the code at `ecdcfb6`.

### Diagnosis (why instructions come back null)

1. `shared/models.py:116-129` `SetpointChanges`: every field is `float | None = None`, and none is required. `ControlProposal.model_json_schema()` therefore permits `"changes": {}` or all-null. Under grammar-constrained decoding at temperature 0, all-null is the cheapest valid output.
2. `services/supervisor/app/ollama_client.py:74` tells the model "Omit unchanged fields or set them to null". It never has to state *whether* it chose to act, so a null change set is indistinguishable from "I decided to hold".
3. The standard schema asks the model to generate `decision_id`, `proposed_at` and `source` (server fields), and nests `changes` behind `{"$ref": "#/$defs/SetpointChanges"}`. The hosted path passes this schema to Workers AI `response_format.json_schema` unchanged (`policy.mjs:77`). A decoder that does not resolve `$ref` sees `changes` as unconstrained.
4. JEV works well because each question is a *typed choice among described criteria*. Qwen was asked to *invent numbers*. The 25 September pilot (`docs/JEV_QWEN_PILOT_2026-09-25.md`) shows that Qwen 4B reaches 50% even on the simpler choice task, so free-form numeric proposals are the hardest thing we ask of it.
5. Local audit evidence: 3 of 10 stored proposals have empty `changes`. All three explanations say "no adjustments are required" in normal states, so we currently have no measured null rate for fault scenarios. Task 5 creates that measurement.

## Global Constraints

- The deterministic `SafetyGate` and infrastructure `_gate` remain the only authority. The new contract must never bypass or loosen them.
- Hosted demo: no actuation (`actuationGuard` unchanged). The AI allowance is 10 calls per session and 200 per day. A repair retry counts as a call.
- Hosted request body at most 50,000 bytes (`policy.mjs` `modelRequest`).
- No credentials in code, docs, artifacts or command-line arguments. JEV key only from ignored `.env.local` / environment (`scripts/check_jev.py:settings`).
- JEV calls are billed. The evaluation script makes them only with an explicit `--jev` flag.
- Do not train or tune on the 12 fixtures in `scripts/compare_jev_qwen.py` and then reuse them as evidence.
- Keep `standard` and `fast` profiles working, and keep their existing tests green.
- Match surrounding style: compact code, no docstring sprawl.
- Run Python tests with `.venv-interpret/bin/python -m pytest` and Node tests with `node --test`.
- Deploying to Cloudflare (`wrangler deploy`) is outward-facing. Do it only after the user explicitly approves.

## Review Focus

1. **Target already at a range bound** (e.g. zone isolation at 100%): the menu must offer only the lowering moves, never a no-op or out-of-range id. Pinned in Task 1 (`test_menu_skips_moves_past_bounds`).
2. **Model selects two candidates for the same target** (e.g. pressure +2 and +4): this must be rejected as a contract violation, not silently merged. Pinned in Task 1 (`test_contradictions_are_contract_violations`).
3. **Repair retry also fails**: the audit must show both raw responses and `invalid_or_unavailable`, the baseline keeps control, and no second repair is attempted. Pinned in Task 3 (`test_second_violation_fails_closed_without_more_retries`).
4. **Hosted request with 45 candidates plus compacted state** must still fit under 50,000 bytes. Pinned in Task 4 (`test_structured_hosted_request_fits_limit`).
5. **Infrastructure domain with a control missing from `current_controls`**: that target is left out of the menu, with no KeyError. Pinned in Task 1 (`test_menu_ignores_missing_controls`).

---

## File Structure

- Create `services/supervisor/app/structured_contract.py`: candidate menu, flat schema, response model, conversion into existing proposals, quality flags. Pure functions, no I/O.
- Modify `services/supervisor/app/inference_profiles.py`: `apply_profile` learns the `structured` profile.
- Modify `services/supervisor/app/ollama_client.py`: `_chat` parses structured output, performs one repair and records `structured_decision`, `quality_flags` and `repair` in the audit.
- Modify `services/supervisor/app/agents.py:58`: allow `"structured"` in `AgentRequest.inference_profile`.
- Modify `services/web/src/AgentResearchRoom.jsx`: add the profile option.
- Modify `deploy/cloudflare-live/worker.mjs`: hosted container defaults to `QWEN_INFERENCE_PROFILE=structured`.
- Create `scripts/eval_structured_qwen.py`: scenario benchmark of standard versus structured, with optional JEV agreement.
- Tests: create `tests/test_structured_contract.py`, extend `tests/test_inference_profiles.py` and `tests/hosted-policy.test.mjs`.
- Docs: create `docs/QWEN_STRUCTURED_DECISIONS.md` and update `CHANGELOG.md`.

---

### Task 1: Structured decision contract (pure module)

**Files:**
- Create: `services/supervisor/app/structured_contract.py`
- Test: `tests/test_structured_contract.py`

**Interfaces:**
- Produces:
  - `WATER_LIMITS: dict[str, tuple[float, float, float]]` and `INFRA_LIMITS: dict[str, dict[str, tuple[float, float, float]]]` (lo, hi, max_step)
  - `class ContractViolation(ValueError)`
  - `candidate_menu(domain: str, current: dict) -> list[dict]`. Each item is `{"id": str, "target": str, "value": float | bool, "description": str}`, and `id == f"{target}={value:g}"` (backwash: `"backwash_request=true"`).
  - `structured_schema(menu: list[dict]) -> dict`: a flat JSON schema with no `$ref`
  - `class StructuredDecision(BaseModel)` with fields `plant_status, key_findings, decision, selected_actions, rationale, expected_effect, confidence, episode_status`
  - `parse_structured(content: str) -> StructuredDecision` (raises `pydantic.ValidationError`, which is a `ValueError`)
  - `to_proposal(decision: StructuredDecision, menu: list[dict], domain: str) -> dict`: kwargs for `ControlProposal` (water) or `InfrastructureProposal` (grid/nuclear); raises `ContractViolation`
  - `quality_flags(decision: StructuredDecision, state: dict) -> list[str]`
  - `STRUCTURED_INSTRUCTIONS: str` (system-prompt suffix)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_structured_contract.py
import json
import pytest
from services.supervisor.app.structured_contract import (
    ContractViolation, candidate_menu, parse_structured, quality_flags, structured_schema, to_proposal)
from shared.models import ControlProposal

CURRENT = {'clearwell_target_pct': 65.0, 'elevated_tank_target_pct': 68.0, 'pressure_target_m': 44.0,
           'chlorine_target_mg_l': 1.15, 'coagulant_target_mg_l': 22.0, 'finished_water_ph_target': 7.35,
           'intake_gate_target_pct': 95.0, 'filter_outlet_valve_target_pct': 95.0,
           'zone_1_isolation_target_pct': 100.0, 'zone_2_isolation_target_pct': 100.0, 'zone_3_isolation_target_pct': 100.0}


def decision(**overrides):
    body = {'plant_status': 'degrading', 'key_findings': ['filtered turbidity 0.95 NTU rising'],
            'decision': 'adjust', 'selected_actions': ['coagulant_target_mg_l=24.5'],
            'rationale': 'Raise coagulant to restore removal.', 'expected_effect': 'Turbidity falls below 0.8 NTU.',
            'confidence': 0.7, 'episode_status': 'continue'}
    body.update(overrides)
    return parse_structured(json.dumps(body))


def test_water_menu_offers_half_and_full_steps_inside_ranges():
    ids = {c['id'] for c in candidate_menu('water', CURRENT)}
    assert {'pressure_target_m=46', 'pressure_target_m=48', 'pressure_target_m=42', 'pressure_target_m=40'} <= ids
    assert {'coagulant_target_mg_l=24.5', 'coagulant_target_mg_l=27'} <= ids
    assert 'backwash_request=true' in ids


def test_menu_skips_moves_past_bounds():
    ids = {c['id'] for c in candidate_menu('water', CURRENT)}
    zone = {i for i in ids if i.startswith('zone_1_isolation_target_pct=')}
    assert zone == {'zone_1_isolation_target_pct=92.5', 'zone_1_isolation_target_pct=85'}
    near = candidate_menu('water', {**CURRENT, 'pressure_target_m': 54.0})
    raised = sorted(c['value'] for c in near if c['target'] == 'pressure_target_m' and c['value'] > 54)
    assert raised == [55.0]  # half step 56 and full step 58 both clip to 55; no duplicate id


def test_menu_ignores_missing_controls():
    menu = candidate_menu('grid', {'gas_dispatch_mw': 460.0})
    assert {c['target'] for c in menu} == {'gas_dispatch_mw'}


def test_schema_is_flat_and_enumerates_candidates():
    menu = candidate_menu('water', CURRENT)
    schema = structured_schema(menu)
    assert '$ref' not in json.dumps(schema) and '$defs' not in schema
    assert schema['properties']['selected_actions']['items']['enum'] == [c['id'] for c in menu]
    assert set(schema['required']) == set(schema['properties'])


def test_adjust_converts_to_existing_gate_proposal():
    menu = candidate_menu('water', CURRENT)
    kwargs = to_proposal(decision(), menu, 'water')
    proposal = ControlProposal.model_validate(kwargs)
    assert proposal.changes.coagulant_target_mg_l == 24.5
    assert proposal.changes.pressure_target_m is None


def test_escalate_forces_escalate_episode_status_and_no_changes():
    menu = candidate_menu('water', CURRENT)
    kwargs = to_proposal(decision(decision='escalate', selected_actions=[], plant_status='sensor_untrusted'), menu, 'water')
    assert kwargs['changes'] == {} and kwargs['episode_status'] == 'escalate'


@pytest.mark.parametrize('overrides,message', [
    ({'decision': 'adjust', 'selected_actions': []}, 'adjust requires'),
    ({'decision': 'hold'}, 'must not select'),
    ({'selected_actions': ['pressure_target_m=46', 'pressure_target_m=48']}, 'Two candidates'),
    ({'selected_actions': ['pressure_target_m=99']}, 'Unknown candidate'),
])
def test_contradictions_are_contract_violations(overrides, message):
    with pytest.raises(ContractViolation, match=message):
        to_proposal(decision(**overrides), candidate_menu('water', CURRENT), 'water')


def test_infrastructure_conversion_uses_objective_field():
    menu = candidate_menu('grid', {'gas_dispatch_mw': 460.0})
    kwargs = to_proposal(decision(selected_actions=['gas_dispatch_mw=500']), menu, 'grid')
    assert kwargs['changes'] == {'gas_dispatch_mw': 500.0} and kwargs['objective'].startswith('adjust')


def test_quality_flags_catch_hold_during_abnormal_state():
    held = decision(decision='hold', selected_actions=[], plant_status='normal')
    assert quality_flags(held, {'active_alarms': [{'code': 'TURBIDITY_HIGH'}]}) == ['status_normal_with_active_alarms']
    abnormal = decision(decision='hold', selected_actions=[], plant_status='abnormal')
    assert quality_flags(abnormal, {'alarms': []}) == ['hold_while_abnormal']
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv-interpret/bin/python -m pytest tests/test_structured_contract.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'services.supervisor.app.structured_contract'`

- [ ] **Step 3: Write the implementation**

```python
# services/supervisor/app/structured_contract.py
"""JEV-style typed decision for Qwen: assess, decide, then choose server-bounded candidates."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from shared.limits import SETPOINT_LIMITS, MAX_SETPOINT_STEP

WATER_LIMITS = {k: (*SETPOINT_LIMITS[k], MAX_SETPOINT_STEP[k]) for k in SETPOINT_LIMITS}
# Mirrors the frozen gates in infrastructure_sim grid.py/nuclear.py `_gate`.
INFRA_LIMITS = {
    'grid': {'gas_dispatch_mw': (0.0, 650.0, 80.0), 'hydro_dispatch_mw': (80.0, 320.0, 60.0),
             'battery_dispatch_mw': (-100.0, 100.0, 60.0), 'capacitor_support_mvar': (0.0, 120.0, 40.0),
             'transformer_tap_pct': (-7.5, 7.5, 2.5), 'demand_response_mw': (0.0, 120.0, 50.0)},
    'nuclear': {'turbine_load_target_mwe': (300.0, 1050.0, 80.0), 'condenser_cooling_pct': (50.0, 100.0, 10.0),
                'thermal_dispatch_target_mwth': (0.0, 300.0, 50.0)},
}
STATUSES = ('normal', 'degrading', 'abnormal', 'sensor_untrusted', 'critical')
STRUCTURED_INSTRUCTIONS = (
    ' Structured decision exchange. First assess: set plant_status and give one to three key_findings, each naming a'
    ' measured signal, its value and why it matters. Then decide: adjust (select one or two ids from candidate_actions),'
    ' hold (select none; say why current targets are adequate) or escalate (select none; say what an operator must check,'
    ' such as untrusted or stale sensors, latched trips or a critical state). Only candidate ids are valid actions; the'
    ' server already bounded their values. If a finding shows a value outside its operating limit, prefer a candidate that'
    ' addresses it; if none does, escalate and say so. Example: filtered turbidity 0.95 NTU and rising with coagulant'
    ' 22 mg/L gives plant_status degrading, decision adjust, selected_actions ["coagulant_target_mg_l=24.5"].'
    ' Example: required pressure sensor stale gives plant_status sensor_untrusted, decision escalate, selected_actions [].')


class ContractViolation(ValueError):
    pass


def limits_for(domain):
    return WATER_LIMITS if domain == 'water' else INFRA_LIMITS[domain]


def candidate_menu(domain, current):
    menu = []
    for target, (lo, hi, step) in limits_for(domain).items():
        if current.get(target) is None:
            continue
        now = round(float(current[target]), 3)
        for sign, verb in ((1, 'Raise'), (-1, 'Lower')):
            seen = set()
            for fraction, size in ((0.5, 'half step'), (1.0, 'full step')):
                value = round(min(hi, max(lo, now + sign * step * fraction)), 3)
                if value == now or value in seen:
                    continue
                seen.add(value)
                menu.append({'id': f'{target}={value:g}', 'target': target, 'value': value,
                             'description': f'{verb} {target} {now:g} -> {value:g} ({size})'})
    if domain == 'water':
        menu.append({'id': 'backwash_request=true', 'target': 'backwash_request', 'value': True,
                     'description': 'Request the filter backwash sequence'})
    return menu


def structured_schema(menu):
    text = lambda n: {'type': 'string', 'minLength': 1, 'maxLength': n}
    ids = [c['id'] for c in menu]
    actions = {'type': 'array', 'maxItems': 2, 'items': {'type': 'string', 'enum': ids}} if ids else {'type': 'array', 'maxItems': 0}
    properties = {
        'plant_status': {'type': 'string', 'enum': list(STATUSES)},
        'key_findings': {'type': 'array', 'minItems': 1, 'maxItems': 3, 'items': text(120)},
        'decision': {'type': 'string', 'enum': ['adjust', 'hold', 'escalate']},
        'selected_actions': actions,
        'rationale': text(200),
        'expected_effect': text(160),
        'confidence': {'type': 'number', 'minimum': 0, 'maximum': 1},
        'episode_status': {'type': 'string', 'enum': ['continue', 'resolved', 'escalate']},
    }
    return {'type': 'object', 'additionalProperties': False, 'properties': properties, 'required': list(properties)}


class StructuredDecision(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    plant_status: Literal[STATUSES]
    key_findings: list[str] = Field(min_length=1, max_length=3)
    decision: Literal['adjust', 'hold', 'escalate']
    selected_actions: list[str] = Field(max_length=2)
    rationale: str = Field(min_length=1, max_length=200)
    expected_effect: str = Field(min_length=1, max_length=160)
    confidence: float = Field(ge=0, le=1)
    episode_status: Literal['continue', 'resolved', 'escalate']


def parse_structured(content):
    return StructuredDecision.model_validate_json(content)


def to_proposal(decision, menu, domain):
    by_id = {c['id']: c for c in menu}
    changes = {}
    for action in decision.selected_actions:
        if action not in by_id:
            raise ContractViolation(f'Unknown candidate {action}')
        target = by_id[action]['target']
        if target in changes:
            raise ContractViolation(f'Two candidates change {target}')
        changes[target] = by_id[action]['value']
    if decision.decision == 'adjust' and not changes:
        raise ContractViolation('decision adjust requires at least one selected action')
    if decision.decision != 'adjust' and changes:
        raise ContractViolation(f'decision {decision.decision} must not select actions')
    explanation = f"{decision.rationale} Findings: {'; '.join(decision.key_findings)}"
    if domain == 'water':
        status = 'escalate' if decision.decision == 'escalate' else decision.episode_status
        return {'changes': changes, 'expected_effect': decision.expected_effect, 'confidence': decision.confidence,
                'explanation': explanation[:280], 'episode_status': status}
    return {'objective': f'{decision.decision}: {decision.plant_status}', 'changes': changes,
            'confidence': decision.confidence, 'explanation': explanation[:500]}


def quality_flags(decision, state):
    flags = []
    if (state.get('active_alarms') or state.get('alarms')) and decision.plant_status == 'normal':
        flags.append('status_normal_with_active_alarms')
    if decision.plant_status in ('abnormal', 'degrading') and decision.decision == 'hold':
        flags.append('hold_while_abnormal')
    return flags
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv-interpret/bin/python -m pytest tests/test_structured_contract.py -q`
Expected: all tests PASS. If `test_menu_skips_moves_past_bounds` fails on the float formatting of an id, fix the rounding in `candidate_menu`, not the test.

- [ ] **Step 5: Commit**

```bash
git add services/supervisor/app/structured_contract.py tests/test_structured_contract.py
git commit -m "Add JEV-style structured decision contract for Qwen"
```

---

### Task 2: `structured` inference profile

**Files:**
- Modify: `services/supervisor/app/inference_profiles.py` (`apply_profile`, lines 76–120)
- Test: `tests/test_inference_profiles.py` (append)

**Interfaces:**
- Consumes: `candidate_menu`, `structured_schema`, `STRUCTURED_INSTRUCTIONS` from Task 1.
- Produces: `apply_profile(payload, domain, 'structured')` returns a payload with `think=False`, `options.num_predict=512` and `format=structured_schema(menu)`. The user message JSON gains `candidate_actions: [{id, description}]`, and `payload['_inference_profile']['candidate_menu']` holds the full menu (with values) for Task 3.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_inference_profiles.py
def _water_payload():
    from services.plc_control.app.controller import BaselineController
    from shared.limits import SETPOINT_LIMITS
    state={'sensor_values':{},'allowed_target_ranges':SETPOINT_LIMITS,'current_setpoints':BaselineController().setpoint_dict(),
           'active_alarms':[]}
    return {'think':True,'options':{'num_predict':2048},'format':ControlProposal.model_json_schema(),
            'messages':[{'role':'system','content':'Respect limits.'},{'role':'user','content':json.dumps(state)}]}


def test_structured_profile_sends_candidates_and_flat_schema():
    result=apply_profile(_water_payload(),'water','structured')
    sent=json.loads(result['messages'][-1]['content'])
    menu=result['_inference_profile']['candidate_menu']
    assert [c['id'] for c in sent['candidate_actions']]==[c['id'] for c in menu]
    assert 'value' not in sent['candidate_actions'][0]
    assert result['format']['properties']['selected_actions']['items']['enum']==[c['id'] for c in menu]
    assert result['think'] is False and result['options']['num_predict']==512
    assert 'Structured decision exchange' in result['messages'][0]['content']


def test_structured_profile_uses_current_controls_for_infrastructure():
    state={'allowed_changes':{},'current_controls':{'gas_dispatch_mw':460.0,'unrelated':1}}
    payload={'think':False,'options':{'num_predict':2048},'format':{},
             'messages':[{'role':'system','content':'x'},{'role':'user','content':json.dumps(state)}]}
    menu=apply_profile(payload,'grid','structured')['_inference_profile']['candidate_menu']
    assert {c['target'] for c in menu}=={'gas_dispatch_mw'}


def test_unknown_profile_still_rejected():
    import pytest
    with pytest.raises(ValueError):apply_profile(_water_payload(),'water','turbo')
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv-interpret/bin/python -m pytest tests/test_inference_profiles.py -q`
Expected: the two new structured tests FAIL with `ValueError: Unknown inference profile`. The other tests pass.

- [ ] **Step 3: Implement**

In `apply_profile`, change the guard and add a branch after the existing `if profile=='fast':` block, before `metadata['sent_context_bytes']=...`:

```python
    if profile not in {'standard','fast','structured'}:raise ValueError('Unknown inference profile')
```

```python
    if profile=='structured':
        from .structured_contract import candidate_menu, structured_schema, STRUCTURED_INSTRUCTIONS
        compact=compact_context(state, domain)
        current=state.get('current_setpoints',{}) if domain=='water' else state.get('current_controls',{})
        menu=candidate_menu(domain,current)
        compact['candidate_actions']=[{'id':c['id'],'description':c['description']} for c in menu]
        payload['messages'][-1]['content']=json.dumps(compact,separators=(',',':'))
        payload['messages'][0]['content']+=STRUCTURED_INSTRUCTIONS
        payload['think']=False
        payload['options']['num_predict']=512
        payload['format']=structured_schema(menu)
        metadata['candidate_menu']=menu
        metadata['uncompressed_context']=state
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv-interpret/bin/python -m pytest tests/test_inference_profiles.py -q`
Expected: all PASS, including the six pre-existing tests.

- [ ] **Step 5: Commit**

```bash
git add services/supervisor/app/inference_profiles.py tests/test_inference_profiles.py
git commit -m "Add structured inference profile with bounded candidate menu"
```

---

### Task 3: Parse, repair once, and audit in `_chat`; expose the profile

**Files:**
- Modify: `services/supervisor/app/ollama_client.py` (`_chat`, lines 196–233; imports at line 12)
- Modify: `services/supervisor/app/agents.py:58`
- Modify: `services/web/src/AgentResearchRoom.jsx` (profile selector near line 70)
- Test: `tests/test_structured_contract.py` (append integration tests)

**Interfaces:**
- Consumes: `apply_profile(...,'structured')` metadata `candidate_menu` (Task 2); `parse_structured`, `to_proposal`, `quality_flags` (Task 1).
- Produces: audit record keys `structured_decision` (dict), `quality_flags` (list[str]) and `repair` (`{"error": str, "first_content": str}`, only when a repair happened). `AgentRequest.inference_profile` accepts `"structured"`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_structured_contract.py
import asyncio
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from services.supervisor.app import agent_audit, ollama_client
from services.supervisor.app.database import Base
from services.supervisor.app.ollama_client import OllamaSupervisor, OllamaUnavailable
from services.plant_sim.app.simulator import WaterPlantSimulator
from services.plc_control.app.controller import BaselineController


@pytest.fixture
def audit_database(monkeypatch):
    engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    monkeypatch.setattr(agent_audit, 'SessionLocal', sessionmaker(bind=engine))
    yield
    engine.dispose()


def scripted_ollama(monkeypatch, contents):
    sent, real_client = [], httpx.AsyncClient
    def handler(request):
        if request.url.path == '/api/tags':
            return httpx.Response(200, json={'models': [{'name': 'qwen3:8b', 'digest': 'test'}]})
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={'model': 'qwen3:8b', 'message': {'content': contents[len(sent) - 1]}, 'done': True})
    monkeypatch.setattr(ollama_client.httpx, 'AsyncClient', lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    return sent


def structured_worker():
    worker = OllamaSupervisor(); worker.inference_profile = 'structured'
    return worker


def good(**overrides):
    body = {'plant_status': 'degrading', 'key_findings': ['coagulation pH low'], 'decision': 'adjust',
            'selected_actions': ['coagulant_target_mg_l=24.5'], 'rationale': 'Raise dose.', 'expected_effect': 'Lower turbidity.',
            'confidence': 0.7, 'episode_status': 'continue'}
    body.update(overrides)
    return json.dumps(body)


def test_structured_water_proposal_reaches_gate_with_real_values(audit_database, monkeypatch):
    sent = scripted_ollama(monkeypatch, [good()])
    proposal = asyncio.run(structured_worker().propose(WaterPlantSimulator().snapshot(), BaselineController().setpoint_dict()))
    assert proposal.changes.coagulant_target_mg_l == 24.5 and len(sent) == 1
    record = agent_audit.get_audit(proposal.decision_id)
    assert record['structured_decision']['decision'] == 'adjust' and record['quality_flags'] == []
    assert 'repair' not in record


def test_contract_violation_gets_one_repair_with_the_error(audit_database, monkeypatch):
    sent = scripted_ollama(monkeypatch, [good(selected_actions=[]), good()])
    proposal = asyncio.run(structured_worker().propose(WaterPlantSimulator().snapshot(), BaselineController().setpoint_dict()))
    assert len(sent) == 2 and 'adjust requires' in sent[1]['messages'][-1]['content']
    assert sent[1]['messages'][-2]['role'] == 'assistant'
    record = agent_audit.get_audit(proposal.decision_id)
    assert 'adjust requires' in record['repair']['error']


def test_second_violation_fails_closed_without_more_retries(audit_database, monkeypatch):
    sent = scripted_ollama(monkeypatch, [good(selected_actions=[]), good(decision='hold'), good()])
    with pytest.raises(OllamaUnavailable):
        asyncio.run(structured_worker().propose(WaterPlantSimulator().snapshot(), BaselineController().setpoint_dict()))
    assert len(sent) == 2
    record = agent_audit.list_audits()[0]
    assert record['status'] == 'invalid_or_unavailable' and record['gate']['status'] == 'not_submitted'
    assert record['repair']['first_content'] == good(selected_actions=[])


def test_agent_request_accepts_structured_profile():
    from services.supervisor.app.agents import AgentRequest
    assert AgentRequest(inference_profile='structured').inference_profile == 'structured'
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv-interpret/bin/python -m pytest tests/test_structured_contract.py -q`
Expected: the four new tests FAIL. `_chat` validates the structured JSON against `ControlProposal` (ValidationError, so `OllamaUnavailable`), and `AgentRequest` rejects `'structured'`.

- [ ] **Step 3: Implement**

`services/supervisor/app/agents.py:58`:

```python
    inference_profile: Literal["standard", "fast", "structured"] | None = None
```

`services/supervisor/app/ollama_client.py` import line 12:

```python
from .inference_profiles import apply_profile, normalize_fast_response
from .structured_contract import parse_structured, quality_flags, to_proposal
```

Add a method to `OllamaSupervisor`:

```python
    async def _post(self, payload):
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
        return response.json()

    def _structured(self, content, profile, domain, schema, audit_id, sent_state):
        decision = parse_structured(content)
        proposal = schema.model_validate(to_proposal(decision, profile["candidate_menu"], domain))
        update_audit(audit_id, structured_decision=decision.model_dump(), quality_flags=quality_flags(decision, sent_state))
        return proposal
```

Replace the body of the `try:` block in `_chat` from `async with httpx.AsyncClient(...)` through `proposal = schema.model_validate_json(...)` with:

```python
            body = await self._post(payload)
            update_audit(audit_id, response=body, latency_seconds=round(perf_counter()-started,3))
            content = body["message"]["content"]
            if self.inference_profile == "structured":
                sent_state = json.loads(payload["messages"][-1]["content"])
                try:
                    proposal = self._structured(content, profile, domain, schema, audit_id, sent_state)
                except ValueError as error:
                    # One repair only: the error text is server-generated, never model-controlled instructions.
                    message = str(error)[:400]
                    update_audit(audit_id, repair={"error": message, "first_content": content})
                    body = await self._post({**payload, "messages": [*payload["messages"], {"role": "assistant", "content": content},
                        {"role": "user", "content": f"Your JSON broke the decision contract: {message}. Return a corrected JSON object for the same state."}]})
                    update_audit(audit_id, response=body, latency_seconds=round(perf_counter()-started,3))
                    proposal = self._structured(body["message"]["content"], profile, domain, schema, audit_id, sent_state)
            elif self.inference_profile == "fast":
                proposal = schema.model_validate(normalize_fast_response(content, payload, domain))
            else:
                proposal = schema.model_validate_json(content)
```

Leave the existing `status()`/manifest lines before it and the `update_audit(... status="awaiting_gate" ...)` and `except` clause after it unchanged. The second failure falls into the existing `except (httpx.HTTPError, KeyError, ValueError)`, which records `invalid_or_unavailable` and `not_submitted`.

`services/web/src/AgentResearchRoom.jsx`: find the `<select>` or buttons that set `setProfile` (search for `setProfile(`) and add an option with value `structured` and label `Structured (JEV-style)`, matching the existing option markup exactly. Then update the thinking-checkbox condition `profile==="fast"` to `profile!=="standard"`, because structured also forces `think=false`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv-interpret/bin/python -m pytest tests/test_structured_contract.py tests/test_inference_profiles.py tests/test_operations_and_agents.py -q`
Expected: all PASS (existing agent tests prove that `standard` and `fast` still work).

Run: `cd services/web && npm run build`
Expected: build succeeds.

- [ ] **Step 5: Commit**

```bash
git add services/supervisor/app/ollama_client.py services/supervisor/app/agents.py services/web/src/AgentResearchRoom.jsx tests/test_structured_contract.py
git commit -m "Validate structured Qwen decisions with one repair and audit quality flags"
```

---

### Task 4: Hosted path: flat schemas and structured default on Cloudflare

**Files:**
- Modify: `services/supervisor/app/inference_profiles.py` (standard branch: inline `$ref`, drop server fields)
- Modify: `deploy/cloudflare-live/worker.mjs:16` (`envVars`)
- Test: `tests/test_inference_profiles.py`, `tests/hosted-policy.test.mjs`

**Interfaces:**
- Consumes: `structured_schema` (Task 1).
- Produces: `inline_refs(schema: dict) -> dict` in `inference_profiles.py`. The `standard` profile now sends `format` without `$ref`/`$defs` and without `decision_id`, `proposed_at` or `source`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_inference_profiles.py
def test_standard_schema_is_flattened_for_hosted_decoders():
    result=apply_profile(_water_payload(),'water','standard')
    text=json.dumps(result['format'])
    assert '$ref' not in text and '$defs' not in result['format']
    assert {'decision_id','proposed_at','source'}.isdisjoint(result['format']['properties'])
    assert 'pressure_target_m' in result['format']['properties']['changes']['properties']
```

```js
// append to tests/hosted-policy.test.mjs
import { readFileSync } from 'node:fs';
test('structured hosted request fits limit', () => {
  const ids=Array.from({length:45},(_,i)=>`coagulant_target_mg_l=${i}.5`);
  const format={type:'object',additionalProperties:false,required:['selected_actions'],
    properties:{selected_actions:{type:'array',maxItems:2,items:{type:'string',enum:ids}}}};
  const state={candidate_actions:ids.map(id=>({id,description:`Raise ${id} (half step)`})),sensor_values:{}};
  const pad='x'.repeat(30000); // representative compacted water state
  const body={messages:[{role:'system',content:'rules'},{role:'user',content:JSON.stringify({...state,pad})}],format};
  const request=modelRequest(body);
  assert.deepEqual(request.response_format.json_schema,format);
  assert.ok(!JSON.stringify(request).includes('$ref'));
});
test('hosted container defaults to the structured profile', () => {
  const source=readFileSync(new URL('../deploy/cloudflare-live/worker.mjs',import.meta.url),'utf8');
  assert.match(source,/QWEN_INFERENCE_PROFILE:'structured'/);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv-interpret/bin/python -m pytest tests/test_inference_profiles.py -q && node --test tests/hosted-policy.test.mjs`
Expected: `test_standard_schema_is_flattened_for_hosted_decoders` FAILS (`$ref` present). The Node test `hosted container defaults to the structured profile` FAILS.

- [ ] **Step 3: Implement**

In `inference_profiles.py`, add:

```python
SERVER_FIELDS={'decision_id','proposed_at','source'}

def inline_refs(schema):
    defs=schema.get('$defs',{})
    def walk(node):
        if isinstance(node,dict):
            if '$ref' in node:return walk(deepcopy(defs[node['$ref'].rsplit('/',1)[-1]]))
            return {k:walk(v) for k,v in node.items() if k!='$defs'}
        if isinstance(node,list):return [walk(v) for v in node]
        return node
    flat=walk(schema)
    if isinstance(flat.get('properties'),dict):
        flat['properties']={k:v for k,v in flat['properties'].items() if k not in SERVER_FIELDS}
        flat['required']=[k for k in flat.get('required',[]) if k not in SERVER_FIELDS]
    return flat
```

In `apply_profile`, directly after `metadata={...}`:

```python
    if profile=='standard' and isinstance(payload.get('format'),dict):payload['format']=inline_refs(payload['format'])
```

Note: the `fast` branch reads `payload['format']['$defs']['SetpointChanges']` for water, so the flattening must be limited to `standard`, as written above.

In `deploy/cloudflare-live/worker.mjs` line 16:

```js
  envVars={OLLAMA_BASE_URL:'http://inference.lab',OLLAMA_MODEL:HOSTED_MODEL,HOSTED_MODE:'true',LESSON_MEMORY_ENABLED:'false',QWEN_INFERENCE_PROFILE:'structured'};
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv-interpret/bin/python -m pytest tests -q -x --ignore=tests/integration_test.py && node --test tests/*.test.mjs`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add services/supervisor/app/inference_profiles.py deploy/cloudflare-live/worker.mjs tests/test_inference_profiles.py tests/hosted-policy.test.mjs
git commit -m "Flatten proposal schemas and default the hosted lab to structured decisions"
```

Do **not** run `wrangler deploy` in this task. Deployment happens after Task 5's evidence and the user's approval.

---

### Task 5: Scenario benchmark (standard vs structured, optional JEV agreement)

**Files:**
- Create: `scripts/eval_structured_qwen.py`
- Test: `tests/test_structured_contract.py` (append `summarize` test)

**Interfaces:**
- Consumes: `OllamaSupervisor.propose`, `SafetyGate.evaluate`, `agent_audit.get_audit`, `candidate_menu`; `settings`, `ENDPOINT` from `scripts/check_jev.py`.
- Produces: `summarize(rows: list[dict]) -> dict[str, dict]` keyed by profile. Each row is `{"scenario", "profile", "abnormal": bool, "changes": dict, "decision": str | None, "gate": str | None, "error": str | None, "repaired": bool, "latency": float, "jev_choice": str | None, "qwen_choice": str | None}`. Writes `artifacts/structured-qwen/results.json` and `summary.json`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_structured_contract.py
def test_summary_counts_null_proposals_only_in_abnormal_states():
    from scripts.eval_structured_qwen import summarize
    rows = [
        {'scenario': 'normal_day', 'profile': 'standard', 'abnormal': False, 'changes': {}, 'decision': None, 'gate': 'accepted', 'error': None, 'repaired': False, 'latency': 1.0, 'jev_choice': None, 'qwen_choice': None},
        {'scenario': 'zone_leak', 'profile': 'standard', 'abnormal': True, 'changes': {}, 'decision': None, 'gate': 'accepted', 'error': None, 'repaired': False, 'latency': 3.0, 'jev_choice': 'pressure_target_m=48', 'qwen_choice': 'hold'},
        {'scenario': 'zone_leak', 'profile': 'structured', 'abnormal': True, 'changes': {'pressure_target_m': 48}, 'decision': 'adjust', 'gate': 'accepted', 'error': None, 'repaired': True, 'latency': 2.0, 'jev_choice': 'pressure_target_m=48', 'qwen_choice': 'pressure_target_m=48'},
        {'scenario': 'opcua_interruption', 'profile': 'structured', 'abnormal': True, 'changes': {}, 'decision': 'escalate', 'gate': None, 'error': None, 'repaired': False, 'latency': 2.0, 'jev_choice': None, 'qwen_choice': 'escalate'},
    ]
    summary = summarize(rows)
    assert summary['standard']['silent_null_in_abnormal'] == 1
    assert summary['structured']['silent_null_in_abnormal'] == 0  # an explicit escalate is not silent
    assert summary['structured']['repaired'] == 1
    assert summary['standard']['jev_agreement'] == '0/1' and summary['structured']['jev_agreement'] == '1/1'
    assert summary['structured']['median_latency'] == 2.0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv-interpret/bin/python -m pytest tests/test_structured_contract.py::test_summary_counts_null_proposals_only_in_abnormal_states -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.eval_structured_qwen'`

- [ ] **Step 3: Implement**

```python
#!/usr/bin/env python3
"""Frozen-snapshot scenario benchmark: standard vs structured Qwen. Evaluate only; never actuates."""
import argparse, asyncio, json, os, statistics, sys, time, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
OUT = ROOT / 'artifacts/structured-qwen'
SCENARIOS = ['normal_day', 'turbidity_spike', 'gradual_turbidity_rise', 'chlorine_sensor_drift', 'pump_failure',
             'zone_leak', 'opcua_interruption', 'low_alkalinity', 'naoh_feed_failure']


def summarize(rows):
    summary = {}
    for profile in sorted({r['profile'] for r in rows}):
        subset = [r for r in rows if r['profile'] == profile]
        judged = [r for r in subset if r['jev_choice'] and not r['error']]
        summary[profile] = {
            'calls': len(subset), 'errors': sum(bool(r['error']) for r in subset),
            'silent_null_in_abnormal': sum(r['abnormal'] and not r['error'] and not r['changes'] and r['decision'] != 'escalate' for r in subset),
            'repaired': sum(r['repaired'] for r in subset),
            'gate': {s: sum(r['gate'] == s for r in subset) for s in sorted({r['gate'] for r in subset if r['gate']})},
            'median_latency': statistics.median(r['latency'] for r in subset),
            'jev_agreement': f"{sum(r['jev_choice'] == r['qwen_choice'] for r in judged)}/{len(judged)}",
        }
    return summary


def snapshot_for(scenario):
    from services.plant_sim.app.scenarios import SCENARIOS as DEFINITIONS
    from services.plant_sim.app.simulator import WaterPlantSimulator
    sim = WaterPlantSimulator(); sim.reset(seed=42, scenario=scenario)
    start = DEFINITIONS[scenario].fault_start_minute
    sim.advance((start or 60) + 15)
    return sim.snapshot()


def jev_choice(state, menu, key):
    from scripts.check_jev import ENDPOINT
    criteria = {c['id']: c['description'] for c in menu}
    criteria.update(hold='Keep all current targets; no adjustment is justified.',
                    escalate='Keep baseline control and ask an operator to check sensors, trips or critical state.')
    payload = {'model': 'typesafe/jev-1.13', 'state': state, 'questions': {'action': {'type': 'choice',
               'instructions': 'Choose the single best bounded supervisory action for this simulated water plant.', 'criteria': criteria}}}
    request = urllib.request.Request(ENDPOINT, data=json.dumps(payload).encode(), headers={'Authorization': 'Bearer ' + key,
              'Content-Type': 'application/json', 'X-Title': 'OT Lab structured evaluation'})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response).get('answers', {}).get('action', {}).get('choice')


async def run(profiles, model, key):
    from services.supervisor.app import agent_audit
    from services.supervisor.app.database import initialize_database
    from services.supervisor.app.ollama_client import OllamaSupervisor, OllamaUnavailable
    from services.supervisor.app.structured_contract import candidate_menu
    from services.plc_control.app.controller import BaselineController, SafetyGate
    initialize_database(); rows = []
    for scenario in SCENARIOS:
        snap = snapshot_for(scenario); control = BaselineController(); setpoints = control.setpoint_dict()
        abnormal = bool(snap.active_alarms) or scenario != 'normal_day'
        menu = candidate_menu('water', setpoints); jev = None
        if key:
            state = {'scenario': scenario, 'alarms': [a.model_dump(mode='json') for a in snap.active_alarms],
                     'sensors': {k: [v.value, v.unit, v.quality] for k, v in snap.sensors.items()}, 'current_targets': setpoints}
            jev = jev_choice(state, menu, key)
        for profile in profiles:
            worker = OllamaSupervisor(); worker.inference_profile = profile; worker.model = model
            started = time.perf_counter(); row = {'scenario': scenario, 'profile': profile, 'abnormal': abnormal, 'jev_choice': jev}
            try:
                proposal = await worker.propose(snap, setpoints)
                record = agent_audit.get_audit(proposal.decision_id)
                changes = proposal.changes.model_dump(exclude_none=True)
                decision = (record.get('structured_decision') or {}).get('decision')
                picks = (record.get('structured_decision') or {}).get('selected_actions') or []
                ids = {(c['target'], c['value']): c['id'] for c in menu}
                qwen = picks[0] if picks else (decision or ('hold' if not changes else ids.get(next(iter(changes.items())))))
                row.update(changes=changes, decision=decision, gate=SafetyGate(control).evaluate(proposal, snap).status,
                           error=None, repaired='repair' in record, qwen_choice=qwen)
            except OllamaUnavailable as error:
                row.update(changes={}, decision=None, gate=None, error=str(error), repaired=False, qwen_choice=None)
            row['latency'] = round(time.perf_counter() - started, 3); rows.append(row)
            print(f"{profile:10} {scenario:24} {row['decision'] or '-':8} {row['changes']} gate={row['gate']} jev={jev}", flush=True)
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default=os.getenv('OLLAMA_MODEL', 'qwen3:8b'))
    parser.add_argument('--profiles', default='standard,structured')
    parser.add_argument('--jev', action='store_true', help='Also ask Jev (billed, about 9 small calls)')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('DATABASE_URL', f"sqlite:///{OUT / 'audits.db'}")
    os.environ.setdefault('OLLAMA_BASE_URL', 'http://127.0.0.1:11434')
    key = None
    if args.jev:
        from scripts.check_jev import settings
        key = settings().get('OPENROUTER_API_KEY'); assert key, 'Missing OPENROUTER_API_KEY'
    rows = asyncio.run(run(args.profiles.split(','), args.model, key))
    (OUT / 'results.json').write_text(json.dumps(rows, indent=2))
    summary = summarize(rows); (OUT / 'summary.json').write_text(json.dumps(summary, indent=2)); print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
```

`DATABASE_URL` and `OLLAMA_BASE_URL` must be set before `services.supervisor.app.database` is imported. All of those imports are inside `run()`, which runs after `main()` sets the environment. Keep it that way.

- [ ] **Step 4: Run the test, then the benchmark locally**

Run: `.venv-interpret/bin/python -m pytest tests/test_structured_contract.py -q`
Expected: all PASS.

Run (local Ollama must be up; no billed calls): `.venv-interpret/bin/python scripts/eval_structured_qwen.py --model qwen3:8b`
Expected: 18 rows print. `summary.json` exists. **Success criterion:** `structured.silent_null_in_abnormal == 0` and `structured.errors <= 1`. Record `standard.silent_null_in_abnormal` as the baseline you are improving on.

If structured still produces holds flagged `hold_while_abnormal` in several fault scenarios, first inspect the audit `quality_flags` and `key_findings` in `artifacts/structured-qwen/audits.db`, then adjust `STRUCTURED_INSTRUCTIONS`. Do not hand-edit results.

Ask the user before running `--jev` (billed, about 9 calls, well under $0.01 at pilot prices).

- [ ] **Step 5: Commit**

```bash
git add scripts/eval_structured_qwen.py tests/test_structured_contract.py
git commit -m "Add scenario benchmark for standard vs structured Qwen decisions"
```

(`artifacts/` is git-ignored, so the results are not committed.)

---

### Task 6: Evidence write-up and hosted rollout

**Files:**
- Create: `docs/QWEN_STRUCTURED_DECISIONS.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Write `docs/QWEN_STRUCTURED_DECISIONS.md`** using the actual numbers from `artifacts/structured-qwen/summary.json`. Include these sections: the diagnosis (copy the five points from this plan), the contract (fields and candidate-menu rule), a results table (per profile: calls, errors, silent null in abnormal, repaired, gate outcomes, median latency, JEV agreement if run), and limitations. Limitations must cover: 9 frozen snapshots, one seed, not closed-loop recovery; candidate steps are coarse (half/full step only); JEV agreement is agreement, not correctness; a repair doubles hosted allowance use for that call.

- [ ] **Step 2: Add a `CHANGELOG.md` entry** at the top, following the existing entry format: "Structured (JEV-style) Qwen decision profile with bounded candidate menu, one contract repair, audit quality flags; hosted lab defaults to it."

- [ ] **Step 3: Run the full suites**

Run: `.venv-interpret/bin/python -m pytest tests -q --ignore=tests/integration_test.py && node --test tests/*.test.mjs deploy/cloudflare-live/visitors.test.mjs`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add docs/QWEN_STRUCTURED_DECISIONS.md CHANGELOG.md
git commit -m "Document structured Qwen decision results"
```

- [ ] **Step 5: Hosted rollout (only with explicit user approval)**

Ask the user. If they approve: `cd deploy/cloudflare-live && npx wrangler deploy`. Then open one hosted session, run one evaluation in a fault scenario, and confirm that the decision inspector shows `structured_decision` and non-null changes, or an explicit escalate.

---

## Out of scope / follow-ups

- **LoRA / adapter fine-tuning of Qwen on JEV-labelled decisions.** This becomes worthwhile once Task 5 gives a held-out scenario family and a baseline. Generate training labels from *different* scenario seeds and fixtures than the evaluation set (see the Global Constraints).
- **Closed-loop recovery evaluation** of the structured profile (`run_recovery_timeline.py`) across multiple seeds.
- **Replacing Qwen with JEV** as the hosted decision backend. `docs/JEV_OPENROUTER.md` lists that as separate integration work.
