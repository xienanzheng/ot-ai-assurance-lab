"""Check only V2 ports; initialise separate local secrets without printing them."""
import argparse
from pathlib import Path
import secrets
import socket
import os
p=argparse.ArgumentParser(); p.add_argument('--init',action='store_true'); args=p.parse_args()
root=Path(__file__).resolve().parents[1]
for port in (18790,18840):
    with socket.socket() as s:
        try: s.bind(('127.0.0.1',port))
        except OSError: raise SystemExit(f'V2 port {port} is occupied. No service was stopped.')
if args.init and not (root/'.env').exists():
    fd=os.open(root/'.env',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:
        f.write('DB_PASSWORD='+secrets.token_hex(24)+'\nSERVICE_TOKEN='+secrets.token_hex(32)+'\n')
print('V2 ports available. Local secrets '+('present' if (root/'.env').exists() else 'missing; use --init')+'.')
