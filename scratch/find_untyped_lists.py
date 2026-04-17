import re

file_path = r'c:\Users\andre\Documents\Hermes\functions\main.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Pattern for function parameter type hints
# Look for ": list " or ": list," or ": list)"
matches = re.finditer(r'def\s+\w+\s*\((.*?)\)\s*:', content, re.DOTALL)

for match in matches:
    params_str = match.group(1)
    func_name = re.search(r'def\s+(\w+)', match.group(0)).group(1)
    
    # Simple check for ": list" without brackets
    if re.search(r':\s*list\s*[,\)]', params_str):
        print(f"Function '{func_name}' has untyped list parameter in '{params_str.strip()}'")
