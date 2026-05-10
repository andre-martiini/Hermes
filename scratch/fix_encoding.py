with open('index.tsx', 'rb') as f:
    raw = f.read()

# Decode assuming it might be utf-16le or utf-8 with BOM
if raw.startswith(b'\xff\xfe'):
    text = raw.decode('utf-16le')
elif raw.startswith(b'\xfe\xff'):
    text = raw.decode('utf-16be')
elif raw.startswith(b'\xef\xbb\xbf'):
    text = raw.decode('utf-8-sig')
else:
    text = raw.decode('utf-8', errors='ignore')

with open('index.tsx', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
