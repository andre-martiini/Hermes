import os

files = ['functions/main.py', 'hermes_cli.py']

for file_path in files:
    if not os.path.exists(file_path):
        continue
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Apply substitutions for the python files
    content = content.replace("'origem': 'google'", "'origem': 'manual'")
    content = content.replace('categoria', 'area_tematica')
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

print('Done refactoring python files')
