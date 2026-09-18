export async function readLabJson(response) {
  if (!(response.headers.get('content-type') || '').includes('application/json')) {
    throw new Error(`Live API unavailable (HTTP ${response.status}). Open the live lab at http://127.0.0.1:18780/.`);
  }
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data));
  return data;
}
export function liveStatus({ connection = 'checking', agent, plant, records = [], hosted = false }) {
  const evaluations=records.filter(record=>record.status==='complete'&&record.evaluate_only===true).length;
  return {
    model: connection==='offline'?'Live lab unavailable':connection==='checking'?'Connecting to lab':agent?.model?.available&&agent?.model?.model_pulled?(hosted?'Cloud model ready':'Local model ready'):(hosted?'Cloud model unavailable':'Local model unavailable'),
    records: connection==='offline'?'Records unavailable':connection==='checking'?'Records pending':`${records.length} records · ${evaluations} ${evaluations===1?'evaluation':'evaluations'}`,
    plant: !plant?'Plant status unavailable':`${plant.controller_mode?.replaceAll('_',' ') || 'Mode unknown'} · ${typeof plant.running==='boolean'?(plant.running?'running':'paused'):'state unknown'}`,
  };
}
