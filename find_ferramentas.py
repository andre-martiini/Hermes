
with open('c:/Users/T-GAMER/Documents/gestao-Hermes/index.tsx', 'r', encoding='utf-8') as f:
    lines = f.readlines()
    for i, line in enumerate(lines):
        if 'FerramentasView' in line:
            print(f"{i+1}: {line.strip()}")
