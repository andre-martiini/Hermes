
import React, { useState, useMemo } from 'react';
import { ConhecimentoItem, KnowledgeEdge } from '../../../types';
import { KnowledgeGraphView } from './KnowledgeGraphView';

interface GlobalKnowledgeGraphProps {
    items: ConhecimentoItem[];
    edges: KnowledgeEdge[];
    onNodeClick?: (id: string) => void;
}

export const GlobalKnowledgeGraph: React.FC<GlobalKnowledgeGraphProps> = ({
    items,
    edges,
    onNodeClick
}) => {
    const [filter, setFilter] = useState<string>('all');

    const filteredItems = useMemo(() => {
        if (filter === 'all') return items;
        return items.filter(i => i.memory_location?.wing === filter);
    }, [items, filter]);

    return (
        <div className="w-full h-full flex flex-col gap-6 animate-in fade-in duration-700">
            {/* Header / Toolbar */}
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 bg-white/40 backdrop-blur-xl p-6 rounded-[2.5rem] border border-slate-200 shadow-sm">
                <div>
                    <h2 className="text-2xl font-black text-slate-900 tracking-tight">Cérebro Hermes</h2>
                    <p className="text-xs font-bold text-slate-400 uppercase tracking-widest mt-1">Conexões entre {items.length} artefactos</p>
                </div>
                
                <div className="flex gap-2">
                    {['all', 'sistemas', 'operacoes', 'captura'].map((f) => (
                        <button
                            key={f}
                            onClick={() => setFilter(f)}
                            className={`px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${filter === f ? 'bg-slate-900 text-white shadow-lg' : 'bg-white text-slate-500 hover:bg-slate-50 border border-slate-200'}`}
                        >
                            {f === 'all' ? 'Ver Tudo' : f}
                        </button>
                    ))}
                </div>
            </div>

            {/* Graph Canvas */}
            <div className="flex-1 bg-white rounded-[3rem] border border-slate-200 shadow-xl overflow-hidden relative">
                <KnowledgeGraphView 
                    items={filteredItems} 
                    edges={edges} 
                    width={window.innerWidth - 100} 
                    height={window.innerHeight - 300}
                    onNodeClick={(node) => onNodeClick && onNodeClick(node.id)}
                />
                
                <div className="absolute top-8 left-8 pointer-events-none">
                    <div className="bg-slate-900/10 backdrop-blur-sm border border-slate-900/10 p-4 rounded-2xl">
                        <p className="text-[10px] font-black text-slate-600 uppercase tracking-[0.2em] mb-1">Dica de Navegação</p>
                        <ul className="text-[9px] font-bold text-slate-500 space-y-1">
                            <li>• Use o Scroll para ZOOM</li>
                            <li>• Clique e Arraste para MOVER</li>
                            <li>• Clique no NÓ para abrir detalhe</li>
                        </ul>
                    </div>
                </div>
            </div>
        </div>
    );
};
