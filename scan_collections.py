import os
import re

def find_collections(path):
    collections = set()
    pattern = re.compile(r"collection\(['\"](.+?)['\"]")
    
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith(('.py', '.ts', '.tsx', '.js', '.jsx')):
                try:
                    with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                        matches = pattern.findall(f.read())
                        for m in matches:
                            collections.add(m)
                except:
                    pass
    return sorted(list(collections))

if __name__ == "__main__":
    base_path = r"C:\Users\andre\Documents\Hermes"
    cols = find_collections(base_path)
    with open(os.path.join(base_path, "lista_colecoes.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(cols))
    print(f"Encontradas {len(cols)} coleções. Salvo em lista_colecoes.txt")
