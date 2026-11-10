"""CLI for the isolated local typed-choice Qwen experiment."""
import argparse
from training.mlx_experiment import run_stage


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',required=True,choices=['prepare','baseline','train','validate','test','report'])
    parser.add_argument('--root',required=True)
    parser.add_argument('--model',required=True)
    args=parser.parse_args()
    run_stage(args.stage,args.root,args.model)


if __name__=='__main__':main()
