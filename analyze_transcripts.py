import json, os, glob, re
from collections import Counter

files = glob.glob('/Users/rakeshreddy/.claude/projects/**/*.jsonl', recursive=True)
files.sort(key=os.path.getmtime, reverse=True)
files = files[:50]

cmd_counter = Counter()
full_cmds = []

for fpath in files:
    try:
        with open(fpath) as f:
            for line in f:
                try:
                    obj = json.loads(line.strip())
                    msg = obj.get('message', {})
                    if msg.get('role') != 'assistant':
                        continue
                    for content in msg.get('content', []):
                        if content.get('type') != 'tool_use':
                            continue
                        name = content.get('name', '')
                        if name == 'Bash':
                            cmd = content.get('input', {}).get('command', '')
                            if cmd:
                                full_cmds.append(cmd[:150])
                                stripped = re.sub(r'^(\s*\w+=\S+\s+)+', '', cmd.strip())
                                first = re.split(r'[|;&]', stripped)[0].strip()
                                tokens = first.split()
                                if not tokens:
                                    continue
                                t0 = tokens[0]
                                if t0 in ('sudo', 'timeout', 'time', 'env'):
                                    tokens = tokens[1:]
                                    if not tokens:
                                        continue
                                    t0 = tokens[0]
                                t1 = tokens[1] if len(tokens) > 1 else ''
                                if t0 in ('git', 'gh', 'docker', 'npm', 'yarn', 'pnpm', 'bun', 'pip', 'pytest', 'docker-compose'):
                                    key = (t0 + ' ' + t1).strip() if t1 else t0
                                else:
                                    key = t0
                                cmd_counter[key] += 1
                except Exception:
                    pass
    except Exception:
        pass

print('TOP BASH COMMAND FREQUENCIES:')
for cmd, count in cmd_counter.most_common(60):
    print(f'{count:4d}  {cmd}')

print()
print('SAMPLE FULL COMMANDS (first 80):')
for c in full_cmds[:80]:
    print(' ', repr(c))
