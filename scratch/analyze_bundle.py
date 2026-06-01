with open(r'c:\Users\T-GAMER\Documents\gestao-Hermes\dist\assets\index-B3trA2Fh.js', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print("Number of lines:", len(lines))
# Line 4680 is index 4679 (0-indexed)
if len(lines) >= 4680:
    line_content = lines[4679]
    print("Length of line 4680:", len(line_content))
    # Print the context around column 41926
    start = max(0, 41926 - 150)
    end = min(len(line_content), 41926 + 150)
    print("Context:")
    print(line_content[start:end])
else:
    print("Line 4680 doesn't exist.")
