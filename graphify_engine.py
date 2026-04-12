
import firebase_admin
from firebase_admin import credentials, firestore
import networkx as nx
import uuid
from datetime import datetime
import os

class GraphifyEngineV2:
    """
    Motor de Grafo de Conhecimento Hermes v2.0
    Integrado com as lógicas do repositório Graphify-4.
    """
    def __init__(self):
        key_path = 'firebase_service_account_key.json'
        if not firebase_admin._apps:
            if not os.path.exists(key_path):
                raise FileNotFoundError("Chave do Firebase não encontrada.")
            cred = credentials.Certificate(key_path)
            firebase_admin.initialize_app(cred)
        self.db = firestore.client()
        self.G = nx.DiGraph() # Grafo Direcionado do NetworkX

    def run_pipeline(self):
        print("\n" + "="*60)
        print("🧠 HERMES GRAPHIFY V2.0: MEMÓRIA TOPOLÓGICA")
        print("="*60)
        
        # 1. Carregamento (Detect)
        docs = list(self.db.collection('conhecimento').stream())
        items = {doc.id: doc.to_dict() for doc in docs}
        print(f"📊 Artefactos carregados: {len(items)}")

        # 2. Construção do Grafo (Build)
        for item_id, data in items.items():
            self.G.add_node(item_id, **data)

        edges_to_create = []

        # 3. Extração de Relações (Extract & Infer)
        for item_id, data in items.items():
            # A. Relação de Derivação (EXTRACTED)
            source_id = data.get('source_artifact_id')
            if source_id and source_id in items:
                self.add_edge_logic(edges_to_create, item_id, source_id, 'derived_from', 'EXTRACTED')

            # B. Relação de Contexto MemPalace (INFERRED)
            loc = data.get('memory_location', {})
            if isinstance(loc, dict) and loc.get('room'):
                # Encontrar outros no mesmo Quarto
                for other_id, other_data in items.items():
                    if item_id == other_id: continue
                    other_loc = other_data.get('memory_location', {})
                    if other_loc.get('room') == loc.get('room'):
                        self.add_edge_logic(edges_to_create, item_id, other_id, 'related_to', 'INFERRED')

            # C. Relação de Menção Técnica (EXTRACTED)
            # Se um arquivo de código referencia outro via semântica
            semantics = data.get('semantics', [])
            for ref in semantics:
                for target_id, target_data in items.items():
                    if ref.lower() in target_data.get('titulo', '').lower():
                        self.add_edge_logic(edges_to_create, item_id, target_id, 'references', 'EXTRACTED')

        # 4. Análise de Cluster (Clusterize) - Louvain simplificado via NetworkX
        # Agrupamos por conectividade
        undirected_G = self.G.to_undirected()
        communities = sorted(nx.connected_components(undirected_G), key=len, reverse=True)
        print(f"🏘️  Comunidades detectadas: {len(communities)}")

        # 5. Persistência (Export)
        self.save_to_firestore(edges_to_create)

    def add_edge_logic(self, list_ref, source, target, kind, confidence):
        # Evitar loops e duplicatas
        if source == target: return
        edge_key = tuple(sorted([source, target]))
        
        # No NetworkX
        self.G.add_edge(source, target, relation=kind, confidence=confidence)
        
        # Para o Firestore
        list_ref.append({
            'source_id': source,
            'target_id': target,
            'relation_kind': kind,
            'confidence': confidence,
            'created_at': datetime.now().isoformat()
        })

    def save_to_firestore(self, edges):
        if not edges:
            print("✨ Grafo já está atualizado.")
            return

        print(f"🚀 Sincronizando {len(edges)} arestas com nível de confiança...")
        batch = self.db.batch()
        count = 0
        
        for edge in edges:
            # Criamos uma ID determinística baseada na conexão para evitar duplicatas infinitas
            edge_id = f"edge_{edge['source_id'][:8]}_{edge['target_id'][:8]}"
            ref = self.db.collection('knowledge_edges').document(edge_id)
            batch.set(ref, {**edge, 'id': edge_id, 'created_by': 'graphify_v2'}, merge=True)
            
            count += 1
            if count % 100 == 0:
                batch.commit()
                batch = self.db.batch()
        
        if count > 0: batch.commit()
        print(f"✅ Sucesso: Grafo V2.0 consolidado com {count} conexões inteligentes.")

if __name__ == "__main__":
    engine = GraphifyEngineV2()
    engine.run_pipeline()
