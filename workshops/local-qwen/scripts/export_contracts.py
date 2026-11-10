"""Export integration contracts for a separately implemented adapter/PLC bench."""
import json
from pathlib import Path
from v2.contracts import Measurement,Snapshot,Proposal,AuditResult,CommandRequest,Package

root=Path(__file__).resolve().parents[1]/'contracts'
root.mkdir(exist_ok=True)
for contract in (Measurement,Snapshot,Proposal,AuditResult,CommandRequest,Package):
    (root/(contract.__name__+'.schema.json')).write_text(json.dumps(contract.model_json_schema(),indent=2)+'\n')
print('Exported six schemas to contracts/. Python validators remain authoritative for cross-field rules.')
