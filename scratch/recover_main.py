import os

search_dirs = [
    r"C:\Users\T-GAMER\.gemini",
    r"C:\Users\T-GAMER\AppData\Local\Temp",
]

print("Searching for backup files containing 'generate_content_logged'...")
found_files = []

for sdir in search_dirs:
    if not os.path.exists(sdir):
        continue
    for root, dirs, files in os.walk(sdir):
        for file in files:
            if file.endswith(".py") or "main.py" in file or file.endswith(".txt") or file.endswith(".log"):
                fpath = os.path.join(root, file)
                try:
                    # Skip large files
                    if os.path.getsize(fpath) > 10 * 1024 * 1024:
                        continue
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        if "generate_content_logged" in content and "def generate_content_logged" not in content:
                            print(f"FOUND backup file: {fpath}")
                            found_files.append(fpath)
                except Exception:
                    pass

print(f"Done. Found {len(found_files)} potential backup files.")
