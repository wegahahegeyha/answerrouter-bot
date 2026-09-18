#!/usr/bin/env python3
# answerrouter_bot - Telegram Business auto-reply bot
# Model: openrouter/inclusionai/ling-3.0-flash-vl:free (multimodal)
# Context in RAM only. Media processed in memory, never written to disk.

import os, sys, json, time, base64, io, traceback
import urllib.request, urllib.error

BASE = os.path.dirname(os.path.abspath(__file__))

# --- config ---
def load_env():
    with open(os.path.join(BASE, '.env')) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k, v)

load_env()
TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
OR_KEY = os.environ['OPENROUTER_API_KEY']
PROXY = os.environ.get('PROXY', '')

MODEL = "inclusionai/ling-3.0-flash-vl:free"
CTX_LIMIT = 10          # messages kept per side (me / them)
API = f"https://api.telegram.org/bot{TOKEN}"

proxy_handler = urllib.request.ProxyHandler({'http': PROXY, 'https': PROXY} if PROXY else None)
OPENER = urllib.request.build_opener(proxy_handler)
urllib.request.install_opener(OPENER)

# --- state (RAM only) ---
ctx = {}           # chat_id -> {"them": deque, "me": deque, "conn": str}
my_ids = set()     # business account owner ids (user we act for)

from collections import deque

def log(*a):
    print(time.strftime("[%H:%M:%S]"), *a, flush=True)

def tg(method, **params):
    data = json.dumps(params).encode()
    req = urllib.request.Request(f"{API}/{method}", data=data,
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=70) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        log("TG ERR", method, e.read().decode()[:300])
        return None

def or_chat(messages, model=None):
    body = json.dumps({"model": model or MODEL, "messages": messages, "max_tokens": 2000}).encode()
    for attempt in range(3):
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=body,
            headers={'Content-Type': 'application/json',
                     'Authorization': f'Bearer {OR_KEY}'})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.loads(r.read())
                msg = d['choices'][0]['message']
                content = msg.get('content')
                if not content:
                    log("OR: empty content, finish:", d['choices'][0].get('finish_reason'))
                    return None
                return content
        except urllib.error.HTTPError as e:
            err = e.read().decode()[:200]
            log("OR ERR", err)
            if '429' in err or 'rate-limited' in err:
                time.sleep(5 * (attempt + 1))
                continue
            return None
        except Exception as e:
            log("OR NET ERR", e)
            time.sleep(3)
    return None

def get_context(chat_id, conn_id):
    if chat_id not in ctx:
        c = tg('getBusinessConnection', business_connection_id=conn_id)
        if c and c.get('ok'):
            uid = c['result']['user']['id']
            my_ids.add(uid)
            log("business owner id:", uid)
        ctx[chat_id] = {"them": deque(maxlen=CTX_LIMIT),
                        "me": deque(maxlen=CTX_LIMIT), "conn": conn_id}
    return ctx[chat_id]

def file_bytes(file_id):
    fi = tg('getFile', file_id=file_id)
    if not fi or not fi.get('ok'):
        return None
    path = fi['result']['file_path']
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/file/bot{TOKEN}/{path}", timeout=60) as r:
            return r.read()
    except Exception as e:
        log("DL ERR", e)
        return None

def build_messages(chat_id):
    st = ctx[chat_id]
    history = []
    for m in st["them"]:
        history.append({"role": "user", "content": m})
    for m in st["me"]:
        history.append({"role": "assistant", "content": m})
    # simple interleave by order: rebuild properly
    return history

# We keep strict alternation in combined deque instead
ctx2 = {}  # chat_id -> list of (who, content) ; who: 'them'|'me'

def push(chat_id, who, content):
    h = ctx2.setdefault(chat_id, [])
    h.append((who, content))
    # keep last 10 per side
    them = [x for x in h if x[0] == 'them'][-CTX_LIMIT:]
    me = [x for x in h if x[0] == 'me'][-CTX_LIMIT:]
    # rebuild chronological merged limited
    merged = []
    ti = mi = 0
    # simpler: filter original h to only last kept ones
    keep = set(id(x) for x in them) | set(id(x) for x in me)
    ctx2[chat_id] = [x for x in h if id(x) in keep]

def history_messages(chat_id, system):
    msgs = [{"role": "system", "content": system}]
    for who, content in ctx2.get(chat_id, []):
        msgs.append({"role": "user" if who == 'them' else "assistant", "content": content})
    return msgs

OWNER_IDS = {712783140}

def handle_prompt_cmd(chat_id, conn, text, doc=None):
    cmd = '/promptset' if text.startswith('/promptset') else '/promptadd' if text.startswith('/promptadd') else '/prompt'
    arg = text[len(cmd):].strip()
    path = os.path.join(BASE, 'prompt.txt')
    if text.startswith('/promptset') or doc:
        # set prompt from attached document
        if not doc:
            tg('sendMessage', chat_id=chat_id,
               text='Send a .txt file with caption /promptset or as a reply to it')
            return
        raw = file_bytes(doc)
        if not raw:
            tg('sendMessage', chat_id=chat_id, text='Could not download the file')
            return
        new_prompt = raw.decode('utf-8', errors='replace')
        with open(path, 'w') as f:
            f.write(new_prompt)
        tg('sendMessage', chat_id=chat_id,
           text=f'Prompt replaced from file ({len(new_prompt)} chars)')
        log('prompt replaced from file, len', len(new_prompt))
        return
    if arg and cmd != '/promptset':
        if cmd == '/promptadd':
            cur = open(path).read().rstrip() + '\n\n'
            new_prompt = cur + arg + '\n'
        else:
            new_prompt = arg + '\n'
        with open(path, 'w') as f:
            f.write(new_prompt)
        tg('sendMessage', chat_id=chat_id,
           **({'business_connection_id': conn} if conn else {}),
           text=f'Prompt {"extended" if cmd=="/promptadd" else "updated"} ({len(new_prompt)} chars total)')
        log('prompt', cmd, 'total', len(new_prompt))
    else:
        # send current prompt as document (easy copy, no length limit)
        with open(path, 'rb') as f:
            data = f.read()
        boundary = '----botboundary'
        part = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="prompt.txt"\r\n'
            f'Content-Type: text/plain\r\n\r\n').encode() + data + f'\r\n--{boundary}--\r\n'.encode()
        req = urllib.request.Request(
            f"{API}/sendDocument" + ('?business_connection_id=' + conn if conn else ''),
            data=part, headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
        try:
            urllib.request.urlopen(req, timeout=60)
            log('prompt sent as document')
        except Exception as e:
            log('sendDocument ERR', e)

def handle_model_cmd(chat_id, text):
    global MODEL
    arg = text[len('/model'):].strip()
    if not arg:
        tg('sendMessage', chat_id=chat_id, text='Current model:\n' + MODEL)
        log('model queried:', MODEL)
        return
    # validate before switching
    test = or_chat([{'role': 'user', 'content': 'say ok'}], model=arg)
    if test is None:
        tg('sendMessage', chat_id=chat_id, text='Model ' + arg + ' does not respond or does not exist, not switching')
        return
    MODEL = arg
    tg('sendMessage', chat_id=chat_id, text='Model switched to:\n' + MODEL)
    log('model changed to', MODEL)

def handle_owner_command(msg):
    """Direct private messages from owner to the bot (not business)."""
    chat = msg.get('chat', {})
    if chat.get('type') != 'private' or msg['from']['id'] not in OWNER_IDS:
        return
    text = msg.get('text', '') or msg.get('caption', '')
    doc = None
    if msg.get('document') and msg['document'].get('file_id'):
        doc = msg['document']['file_id']
    if text.startswith('/promptset'):
        handle_prompt_cmd(chat['id'], None, '/promptset', doc=doc)
    elif text.startswith('/promptadd'):
        handle_prompt_cmd(chat['id'], None, text)
    elif text.startswith('/prompt'):
        handle_prompt_cmd(chat['id'], None, text)
    elif text.startswith('/model'):
        handle_model_cmd(chat['id'], text)
    elif text.startswith('/start') or text.startswith('/help'):
        tg('sendMessage', chat_id=chat['id'],
           text='Commands:\n/prompt - send current prompt as a file\n/prompt text - replace prompt with short text\n/promptadd text - append text to the end of the prompt\n/promptset + .txt file - replace prompt with file contents\n/model - show current model\n/model name - switch model (e.g. inclusionai/ling-3.0-flash-vl:free)')

def extract_content(msg):
    """Returns (kind, content). kind: text|photo|skip"""
    if msg.get('sticker') or msg.get('voice') or msg.get('video_note'):
        return ('skip', None)
    if msg.get('photo'):
        return ('photo', msg['photo'][-1]['file_id'])
    cap = msg.get('caption')
    if msg.get('text') or cap:
        return ('text', msg.get('text') or cap)
    return ('skip', None)

def handle(msg):
    conn = msg.get('business_connection_id')
    if not conn:
        return
    chat_id = msg['chat']['id']
    from_id = msg['from']['id']
    is_me = from_id in my_ids
    msg_id = msg.get('message_id')

    kind, content = extract_content(msg)
    if kind == 'skip':
        return

    get_context(chat_id, conn)

    # history should only contain messages from the counterpart + our replies.
    # If message is from us (e.g. typed manually from phone), store as 'me' but don't reply.
    if is_me:
        # no commands in business chats - only in owner's direct chat with bot
        if kind == 'text' and content:
            push(chat_id, 'me', content)
        return

    if kind == 'text':
        user_block = f"<message>{content}</message>"
        push(chat_id, 'them', user_block)
        content_for_model = user_block
        photo = None
    else:  # photo
        raw = file_bytes(content)
        if not raw:
            return
        b64 = base64.b64encode(raw).decode()
        del raw  # free memory
        cap = msg.get('caption', '')
        content_for_model = [
            {"type": "image_url",
             "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            {"type": "text", "text": f"<message>{cap}</message>" if cap else "<message>[photo without caption]</message>"}
        ]
        push(chat_id, 'them', cap or "[photo]")
        photo = True

    system = open(os.path.join(BASE, 'prompt.txt')).read()
    messages = history_messages(chat_id, system)
    messages[-1] = {"role": "user", "content": content_for_model}

    reply = or_chat(messages)
    if not reply:
        return
    reply = reply[:4000]
    push(chat_id, 'me', reply)

    tg('sendMessage', business_connection_id=conn, chat_id=chat_id, text=reply)
    log(f"chat {chat_id}: {'[photo]' if kind=='photo' else 'text'} -> replied ({len(reply)} ch)")

def main():
    log("bot starting, model:", MODEL)
    me = tg('getMe')
    if not me or not me.get('ok'):
        log("FATAL: bad token / no connection")
        sys.exit(1)
    log("authorized as @%s" % me['result']['username'])
    tg('setMyCommands', commands=[
        {'command': 'prompt', 'description': 'Send current prompt as a file (text - replace)'},
        {'command': 'promptadd', 'description': 'Append text to the end of the prompt'},
        {'command': 'promptset', 'description': 'Send with a .txt file - replace prompt from file'},
        {'command': 'model', 'description': 'Show/switch the model (model name)'}])

    offset = 0
    while True:
        try:
            r = tg('getUpdates', offset=offset, timeout=50,
                   allowed_updates=['business_message', 'edited_business_message', 'message'])
            if not r or not r.get('ok'):
                time.sleep(3)
                continue
            for upd in r['result']:
                offset = upd['update_id'] + 1
                types = [k for k in upd if k != 'update_id']
                log('update:', ','.join(types))
                msg = upd.get('business_message')
                if msg:
                    try:
                        handle(msg)
                    except Exception:
                        log("HANDLE ERR")
                        traceback.print_exc()
                    continue
                msg = upd.get('message')
                if msg:
                    try:
                        handle_owner_command(msg)
                    except Exception:
                        log("CMD ERR")
                        traceback.print_exc()
        except Exception:
            log("LOOP ERR")
            traceback.print_exc()
            time.sleep(5)

if __name__ == '__main__':
    main()
