import os
import yaml
import re
import json
from pathlib import Path

class HermesBrainMigrator:
    def __init__(self, wiki_path, output_path):
        self.wiki_path = Path(wiki_path)
        self.output_path = Path(output_path)
        self.knowledge_bank = []

    def parse_confidence(self, label):
        # Converte confiança passiva em score numérico
        scores = {"alta": 1.0, "media": 0.7, "baixa": 0.4}
        return scores.get(str(label).lower(), 0.5)

    def extract_sections(self, body):
        # Extrai as seções do markdown como campos do objeto
        sections = {}
        patterns = {
            "resumo": r"## Resumo Executivo\n(.*?)(?=\n##|$)",
            "extração": r"## Extracao Especifica\n(.*?)(?=\n##|$)",
            "fontes": r"## Fontes\n(.*?)(?=\n##|$)"
        }
        for key, pattern in patterns.items():
            match = re.search(pattern, body, re.DOTALL)
            sections[key] = match.group(1).strip() if match else ""
        return sections

    def migrate(self):
        print(f"Iniciando migracao de {self.wiki_path}...")
        
        if not self.wiki_path.exists():
            print(f"Erro: Diretorio {self.wiki_path} nao encontrado.")
            return

        for file_path in self.wiki_path.glob("*.md"):
            if file_path.name in ["log.md", "plano_de_revisao.md", "00_Mapa_do_Conhecimento.md"]: continue
            
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                # Split frontmatter
                parts = re.split(r"^---$", content, flags=re.MULTILINE)
                if len(parts) < 3: continue

                meta = yaml.safe_load(parts[1])
                body = parts[2]
                
                sections = self.extract_sections(body)
                links = re.findall(r"\[\[(.*?)\]\]", body)

                # Construcao do Item Relacional
                item = {
                    "id": f"item_{file_path.stem.lower().replace(' ', '_')}",
                    "display": {
                        "title": meta.get("title", file_path.stem),
                        "tldr": meta.get("tldr", ""),
                    },
                    "technical": {
                        "type": meta.get("source_type"),
                        "tags": meta.get("tags", []),
                        "project": meta.get("project", "Geral"),
                        "confidence_weight": self.parse_confidence(meta.get("confidence")),
                        "created_at": str(meta.get("created_at")),
                        "original_wiki_file": file_path.name
                    },
                    "content": {
                        "summary": sections["resumo"],
                        "details": sections["extração"],
                        "raw_sources_ref": sections["fontes"]
                    },
                    "graph": {
                        "explicit_links": list(set(links)),
                        "semantic_cluster": meta.get("project")
                    }
                }
                
                self.knowledge_bank.append(item)
                print(f"Processado: {item['display']['title']}")
            except Exception as e:
                print(f"Erro ao processar {file_path}: {e}")

        # Salva o Banco Relacional Consolidado
        try:
            with open(self.output_path, "w", encoding="utf-8") as f:
                json.dump(self.knowledge_bank, f, indent=2, ensure_ascii=False)
            print(f"\nMigracao concluida! {len(self.knowledge_bank)} itens salvos em {self.output_path}")
        except Exception as e:
            print(f"Erro ao salvar arquivo de saida: {e}")

if __name__ == "__main__":
    WIKI_DIR = r"C:\Users\andre\Documents\automacao-wiki\01_Wiki"
    OUTPUT_JSON = r"C:\Users\andre\Documents\Hermes\hermes_relational_knowledge.json"

    migrator = HermesBrainMigrator(WIKI_DIR, OUTPUT_JSON)
    migrator.migrate()
