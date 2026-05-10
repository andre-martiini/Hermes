with open('index.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace \r\n\r\n with \r\n, and \n\n with \n
while '\r\n\r\n' in content:
    content = content.replace('\r\n\r\n', '\r\n')
while '\n\n' in content:
    content = content.replace('\n\n', '\n')

with open('index.tsx', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
