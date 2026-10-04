"""Fixed-model, loopback-only MLX shadow service; launched by the approval wrapper."""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from shared.water_study_provenance import evaluation_identity


def model_id(identity):
    return 'water-alarm-'+hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()


def validate_request(body,expected_model):
    if not isinstance(body,dict) or body.get('model')!=expected_model:
        raise ValueError('Candidate model identity does not match')
    if set(body)-{'model','messages','temperature','max_tokens','chat_template_kwargs'}:
        raise ValueError('Unsupported candidate request fields')
    messages=body.get('messages')
    if not isinstance(messages,list) or not 1<=len(messages)<=20:
        raise ValueError('Invalid messages')
    for message in messages:
        if not isinstance(message,dict) or set(message)!={'role','content'} or message['role'] not in {'system','user','assistant'} or not isinstance(message['content'],str):
            raise ValueError('Invalid message')
    if body.get('temperature',0)!=0 or body.get('max_tokens',256)!=256 or body.get('chat_template_kwargs',{'enable_thinking':False})!={'enable_thinking':False}:
        raise ValueError('Candidate decoding is fixed to evaluated settings')


def encode_request(tokenizer,body,expected_model):
    validate_request(body,expected_model)
    tokens=tokenizer.apply_chat_template(body['messages'],tokenize=True,return_dict=False,
                                        add_generation_prompt=True,enable_thinking=False)
    if len(tokens)+256>4096:raise ValueError('Full context exceeds evaluated token budget; no truncation')
    return tokens


def serve(config):
    from mlx_lm import load,generate
    from mlx_lm.sample_utils import make_sampler
    identity=config['identity']
    pinned=json.loads((ROOT/'artifacts/posttraining/models.json').read_text())['mlx-community/Qwen3-4B-4bit']
    if Path(config['model']).resolve()!=Path(pinned['path']).resolve():raise ValueError('Serving base path does not match pinned model')
    def verify_files():
        if evaluation_identity(config['dataset'],identity['base_revision'],config['adapter'])!=identity:
            raise ValueError('Serving files differ from evaluated identity')
    verify_files()
    model,tokenizer=load(config['model'],adapter_path=config['adapter'])
    verify_files()  # Detect a change while loading; retain identity of loaded weights.
    identifier=model_id(identity)
    class Handler(BaseHTTPRequestHandler):
        def reply(self,status,body):
            encoded=json.dumps(body).encode();self.send_response(status)
            self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(encoded)))
            self.end_headers();self.wfile.write(encoded)
        def do_GET(self):
            if self.path!='/identity':return self.reply(404,{'error':'Not found'})
            self.reply(200,{'identity':identity,'model':identifier})
        def do_POST(self):
            if self.path!='/v1/chat/completions':return self.reply(404,{'error':'Not found'})
            try:
                if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('JSON required')
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=262144:raise ValueError('Invalid request size')
                body=json.loads(self.rfile.read(length));prompt=encode_request(tokenizer,body,identifier)
                text=generate(model,tokenizer,prompt=prompt,max_tokens=256,sampler=make_sampler(temp=0),verbose=False)
                self.reply(200,{'model':identifier,'identity':identity,'choices':[{'message':{'role':'assistant','content':text}}]})
            except (ValueError,TypeError,KeyError) as exc:self.reply(400,{'error':str(exc)})
            except Exception:self.reply(500,{'error':'Candidate inference failed'})
    # Single request at a time. No CORS, model-path overrides or hosted binding.
    HTTPServer(('127.0.0.1',18784),Handler).serve_forever()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',required=True)
    serve(json.loads(Path(parser.parse_args().config).read_text()))
