import json
import re

lines_dict = {}

transcript_path = r'C:\Users\T-GAMER\.gemini\antigravity\brain\c6c8078c-790c-4b84-a2a8-c2b2bcf5f297\.system_generated\logs\transcript_full.jsonl'
with open(transcript_path, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            data = json.loads(line)
            if data.get('step_index', 999) < 49 and data.get('type') == 'VIEW_FILE' and 'StrategyDashboardView.tsx' in data.get('content', ''):
                content = data.get('content', '')
                if 'The following code has been modified' in content:
                    parts = content.split('The following code has been modified to include a line number before every line, in the format: <line_number>: <original_line>. Please note that any changes targeting the original code should remove the line number, colon, and leading space.')
                    if len(parts) > 1:
                        code_lines = parts[1].split('\n')
                        for cl in code_lines:
                            if cl.strip() and ':' in cl:
                                num_str, rest = cl.split(':', 1)
                                if num_str.isdigit():
                                    num = int(num_str)
                                    if rest.startswith(' '):
                                        rest = rest[1:]
                                    # Always overwrite with latest valid state before step 49
                                    lines_dict[num] = rest
        except Exception as e:
            pass

if lines_dict:
    with open(r'C:\Users\T-GAMER\Documents\gestao-Hermes\src\views\StrategyDashboardView.tsx', 'w', encoding='utf-8') as out:
        for i in range(1, max(lines_dict.keys()) + 1):
            out.write(lines_dict.get(i, '') + '\n')
    print(f'Restored {max(lines_dict.keys())} lines from before step 49!')
else:
    print('No lines found.')
