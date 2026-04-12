
import React, { useMemo, useRef, useEffect } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { ConhecimentoItem, KnowledgeEdge } from '../../../types';

interface KnowledgeGraphViewProps {
    items: ConhecimentoItem[];
    edges: KnowledgeEdge[];
    onNodeClick?: (node: any) => void;
    width?: number;
    height?: number;
}

const WING_COLORS: Record<string, string> = {
    sistemas: '#3b82f6', // Azul
    operacoes: '#10b981', // Verde
    captura: '#f59e0b',   // Amarelo
    default: '#94a3b8'   // Cinza
};

export const KnowledgeGraphView: React.FC<KnowledgeGraphViewProps> = ({
    items,
    edges,
    onNodeClick,
    width = 800,
    height = 600
}) => {
    const fgRef = useRef<any>(null);

    // Transformar dados do Firestore para o formato do ForceGraph
    const gData = useMemo(() => {
        // Filtramos apenas itens que não sejam pastas para o grafo não ficar poluído
        const nodes = items
            .filter(item => !item.is_folder)
            .map(item => ({
                id: item.id,
                name: item.titulo,
                val: 1,
                color: WING_COLORS[item.memory_location?.wing || 'default'],
                wing: item.memory_location?.wing || 'Outros'
            }));

        const nodeIds = new Set(nodes.map(n => n.id));

        let links = edges
            .map(e => {
                const sId = e.source_id || (e as any).source || (e as any).from;
                const tId = e.target_id || (e as any).target || (e as any).to;
                
                if (!sId || !tId || !nodeIds.has(sId) || !nodeIds.has(tId)) return null;

                return {
                    source: String(sId),
                    target: String(tId),
                    relation: e.relation_kind || (e as any).relation || 'related_to',
                    confidence: (e as any).confidence || 'EXTRACTED',
                    color: '#6366f1',
                    value: 1
                };
            })
            .filter((l): l is any => l !== null);

        // Otimização de performance: Se houver muitas arestas, filtramos
        if (links.length > 2000) {
            const extracted = links.filter(l => l.confidence === 'EXTRACTED');
            const others = links.filter(l => l.confidence !== 'EXTRACTED');
            links = [...extracted, ...others.slice(0, Math.max(0, 2000 - extracted.length))];
        }

        return { nodes, links };
    }, [items, edges]);

    // Centralizar o grafo ao carregar
    useEffect(() => {
        if (fgRef.current) {
            fgRef.current.d3Force('charge').strength(-1000);
            fgRef.current.d3Force('link').distance(250).strength(0.05);
            fgRef.current.d3Force('center').strength(0.05);
        }
    }, [gData]);

    return (
        <div className="relative w-full h-full bg-slate-50 rounded-3xl overflow-hidden border border-slate-200 shadow-inner">
            <ForceGraph2D
                ref={fgRef}
                graphData={gData}
                width={width}
                height={height}
                nodeLabel={(node: any) => `
                    <div class="bg-slate-900 text-white p-2 rounded-lg text-xs shadow-xl border border-slate-700">
                        <div class="font-black mb-1">${node.name}</div>
                        <div class="opacity-70">Ala: ${node.wing}</div>
                    </div>
                `}
                nodeColor={node => (node as any).color}
                nodeRelSize={6}
                linkColor={link => (link as any).color}
                linkWidth={0.5}
                linkDirectionalParticles={1}
                linkDirectionalParticleSpeed={0.005}
                linkDirectionalArrowLength={3}
                linkDirectionalArrowRelPos={1}
                linkCurvature={0.2}
                linkLabel={(link: any) => `<div class="bg-white px-2 py-1 rounded text-[10px] border shadow-sm">${link.relation}</div>`}
                onNodeClick={onNodeClick}
                cooldownTicks={500}
            />
            
            {/* Legend */}
            <div className="absolute bottom-4 left-4 bg-white/80 backdrop-blur-md p-3 rounded-2xl border border-slate-200 shadow-sm flex flex-col gap-2">
                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Mapa Mental Hermes</p>
                {Object.entries(WING_COLORS).map(([wing, color]) => (
                    <div key={wing} className="flex items-center gap-2">
                        <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }} />
                        <span className="text-[10px] font-bold text-slate-600 uppercase">{wing}</span>
                    </div>
                ))}
            </div>
        </div>
    );
};

export default KnowledgeGraphView;
