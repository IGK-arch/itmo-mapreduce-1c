"""Read-only localhost console streaming two real calculation subprocesses."""
import html
import json
import subprocess
import sys
import threading
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
states={key:{'status':'Ожидает запуска','lines':[],'exit_code':None} for key in ('compute','verify')}
titles={'compute':'Запуск MapReduce и DuckDB','verify':'Полная сверка результатов'}


def run_jobs():
    sessions=[]
    for action in ('compute','verify'):
        state=states[action]
        state['status']='Выполняется'
        start=datetime.now(timezone.utc).isoformat()
        args=[sys.executable,str(ROOT/'scripts'/'demo_terminal.py'),action]
        with (ROOT/'evidence'/f'terminal-{action}-output.log').open('w',encoding='utf-8',newline='\n') as log:
            proc=subprocess.Popen(args,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                  text=True,encoding='utf-8',bufsize=1,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
            for line in proc.stdout:
                log.write(line);log.flush()
                state['lines'].append(line.rstrip('\r\n'))
            code=proc.wait()
        state['exit_code']=code
        state['status']='Завершено' if code==0 else 'Ошибка'
        sessions.append({'action':action,'command':args,'started_at_utc':start,
                         'finished_at_utc':datetime.now(timezone.utc).isoformat(),'exit_code':code})
        (ROOT/'evidence'/'terminal-sessions.json').write_text(json.dumps(sessions,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        if code:
            break


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):
        pass

    def do_GET(self):
        key=self.path.strip('/').removeprefix('status/')
        if key not in states:
            self.send_error(404);return
        self.send_response(200)
        if self.path.startswith('/status/'):
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Cache-Control','no-store');self.end_headers()
            self.wfile.write(json.dumps(states[key],ensure_ascii=False).encode());return
        self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers()
        source='''<!doctype html><html lang="ru"><meta charset="utf-8">
<title>TITLE · Локальная консоль</title><style>
*{box-sizing:border-box}body{margin:0;background:#f1f3f6;color:#172331;font-family:Segoe UI,Arial,sans-serif}
main{width:900px;margin:14px auto}.top{font-size:14px;color:#536072;margin-bottom:7px}
h1{font-size:23px;margin:0 0 8px;font-weight:600}.meta{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;font-size:14px}
.state{background:#dfede5;color:#175b35;padding:4px 10px;border-radius:4px}.cmd{font-family:Consolas,monospace}
pre{background:#13202d;color:#eef3f8;padding:17px 19px;margin:0;border:1px solid #34465a;border-radius:5px;font:17px/1.28 Consolas,monospace;white-space:pre;overflow:auto;min-height:70px}
footer{font-size:13px;color:#536072;margin:9px 0}
</style><main><div class="top">Лабораторная работа 3 · Вариант 1: разработчики 1С · localhost</div>
<h1>TITLE</h1><div class="meta"><span class="cmd">python scripts/demo_terminal.py ACTION</span><span class="state" id="state">Ожидает запуска</span></div>
<pre id="output" aria-label="Вывод процесса"></pre><footer>Локальная консоль: живой вывод процесса. Данные — s3://hh-lake/raw/it_vacancies_2024.csv</footer></main>
<script>async function update(){const r=await fetch('/status/ACTION');const s=await r.json();document.getElementById('output').textContent=s.lines.join('\\n');document.getElementById('state').textContent=s.status+(s.exit_code===null?'':' · код '+s.exit_code);if(s.exit_code===null)setTimeout(update,600)}update();</script></html>'''
        self.wfile.write(source.replace('TITLE',html.escape(titles[key])).replace('ACTION',key).encode())


if __name__=='__main__':
    server=ThreadingHTTPServer(('127.0.0.1',8765),Handler)
    threading.Thread(target=run_jobs,daemon=True).start()
    print('Read-only live console: http://127.0.0.1:8765/compute',flush=True)
    server.serve_forever()
