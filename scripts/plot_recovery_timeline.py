#!/usr/bin/env python3
"""Export publication-style plots from a recovery session (requires matplotlib)."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session', type=Path)
    args=parser.parse_args()
    d=json.loads(args.session.read_text())
    fig, axes=plt.subplots(3,1,figsize=(11,9),sharex=True,layout='constrained')
    arms=[('baseline','PLC baseline','#777e85'),('agent','PLC + gated Qwen3 8B','#126d65')]
    for key,label,color in arms:
        samples=d.get(key,{}).get('samples',[])
        if not samples:continue
        x=[s['minute'] for s in samples]
        axes[0].plot(x,[s['values']['raw_turbidity_ntu'] for s in samples],color=color,label=label)
        axes[1].plot(x,[s['values']['filtered_turbidity_ntu'] for s in samples],color=color,label=label,lw=2)
        axes[2].step(x,[s['setpoints']['coagulant_target_mg_l'] for s in samples],color=color,label=label+' target',where='post')
        axes[2].plot(x,[s['values']['coagulant_dose_actual_mg_l'] for s in samples],color=color,linestyle=':',label=label+' delivered')
    axes[0].set_ylabel('Source turbidity (NTU)')
    axes[0].set_title('Gradual, sustained source disturbance → measured response → gated adjustments',loc='left')
    axes[1].set_ylabel('Filter effluent (NTU)')
    axes[1].axhline(1,color='#ab3038',ls='--',label='Illustrative limit: 1.0 NTU')
    axes[2].set_ylabel('Coagulant (mg/L)');axes[2].set_xlabel('Simulated minute; clock paused during inference')
    for ax in axes:
        ax.spines[['top','right']].set_visible(False);ax.grid(alpha=.15);ax.legend(loc='upper left',fontsize=8)
        for t in d.get('agent',{}).get('exchanges',[]): ax.axvline(t['minute'],color='#126d65',alpha=.16,lw=1)
    fig.suptitle('Water recovery experiment · '+d.get('status',''),fontsize=16)
    for ext in ['png','svg']:fig.savefig(args.session.parent/f'comparison.{ext}',dpi=180)
    print(args.session.parent/'comparison.png')


if __name__=='__main__':main()
