
file_path = r'c:\Users\T-GAMER\Documents\gestao-Hermes\functions\main.py'
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i in range(8745, 8760):
    if i < len(lines):
        print(f"Line {i+1}: |{repr(lines[i])}|")
