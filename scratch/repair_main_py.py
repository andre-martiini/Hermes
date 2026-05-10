import sys

def fix_file():
    path = r'C:\Users\T-GAMER\Documents\gestao-Hermes\functions\main.py'
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Restoration 1: loop logic in deep_research_worker
    # Current lines 11116-11118 (approx) are broken.
    # We'll look for the pattern and replace.
    
    found_broken_1 = False
    for i in range(len(lines)):
        if '- Destaque incertezas e conflitos entre fontes.' in lines[i]:
            start = i
            # Found it. Now let's replace this and the following lines until the prompt end.
            new_block = [
                '            # Check Cancelled\n',
                '            if check_cancelled():\n',
                '                 print("[DeepResearch] Pesquisa cancelada pelo usuário.")\n',
                '                 return\n',
                '\n',
                '            prompt = f"""Você é o agente Hermes focado em Pesquisa Profunda com consulta à web.\n',
                'Pesquise sobre: "{topic}".\n',
                'Iteração {i+1} de {DEPTH_CAP}.\n',
                '\n',
                'Requisitos:\n',
                '- Use a Pesquisa Google quando ela ajudar a confirmar fatos, datas, normas, pessoas, empresas ou eventos recentes.\n',
                '- Destaque incertezas e conflitos entre fontes.\n',
                '- Inclua links/fontes citadas no texto sempre que a ferramenta retornar evidências.\n',
                '"""\n'
            ]
            # Replace lines[i] to lines[i+2]
            lines[i:i+3] = new_block
            found_broken_1 = True
            break
    
    if not found_broken_1:
        print("Could not find broken block 1")

    # Restoration 2: legacy_ref and acervo_ref logic
    found_broken_2 = False
    for i in range(len(lines)):
        if 'clean_text = re.sub(r"<[^>]+>", " ", final_html)' in lines[i] and '})' in lines[i+1]:
            # This is the second broken part.
            new_block_2 = [
                '        clean_text = re.sub(r"<[^>]+>", " ", final_html)\n',
                '        clean_text = re.sub(r"\\s+", " ", clean_text).strip()\n',
                '        tags = ["deep_research", "pesquisa_profunda"]\n',
                '        try:\n',
                '            emb = get_embedding(\n',
                '                f"Deep Research: {topic}\\n\\nResumo: {resumo_executivo}\\n\\n{clean_text[:7000]}",\n',
                '                api_key=api_key,\n',
                '            )\n',
                '        except Exception as emb_err:\n',
                '            print(f"[DeepResearch] Falha ao gerar embedding do resultado: {emb_err}")\n',
                '            emb = []\n',
                '\n',
                '        # Acervo Global (Gravação Enxuta)\n',
                '        legacy_ref = db.collection(\'conhecimento_mestre\').document()\n',
                '        legacy_ref.set({\n',
                '             \'titulo\': f"Deep Research: {topic}",\n',
                '             \'data_criacao\': firestore.SERVER_TIMESTAMP,\n',
                '             \'solicitante\': requester_email,\n',
                '             \'resumo\': resumo_executivo,\n',
                '             \'link_pdf\': pdf_link,\n',
                '             \'link_html\': html_link,\n',
                '             \'origem\': \'deep_research_max\'\n',
                '        })\n'
            ]
            lines[i:i+2] = new_block_2
            found_broken_2 = True
            break
            
    if not found_broken_2:
        print("Could not find broken block 2")

    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print("Repair complete.")

if __name__ == "__main__":
    fix_file()
