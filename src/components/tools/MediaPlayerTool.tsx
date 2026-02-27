import React, { useState, useMemo, useEffect, useRef } from 'react';
import { ConhecimentoItem } from '@/types';

interface MediaPlayerToolProps {
    onBack: () => void;
    showToast: (msg: string, type: 'success' | 'error' | 'info') => void;
    items: ConhecimentoItem[];
}

export const MediaPlayerTool: React.FC<MediaPlayerToolProps> = ({ onBack, showToast, items }) => {
    const [searchTerm, setSearchTerm] = useState('');
    const [currentMediaId, setCurrentMediaId] = useState<string | null>(null);
    const audioRef = useRef<HTMLAudioElement>(null);
    const videoRef = useRef<HTMLVideoElement>(null);

    // Filter only audio/video files
    const mediaItems = useMemo(() => {
        return items.filter(item => {
            const ext = item.tipo_arquivo.toLowerCase();
            const isMedia = ['mp3', 'wav', 'm4a', 'ogg', 'mp4', 'mov', 'avi', 'webm', 'mkv'].includes(ext);
            if (!isMedia) return false;

            if (searchTerm) {
                return item.titulo.toLowerCase().includes(searchTerm.toLowerCase());
            }
            return true;
        }).sort((a, b) => new Date(b.data_criacao).getTime() - new Date(a.data_criacao).getTime());
    }, [items, searchTerm]);

    const currentMedia = useMemo(() => {
        return mediaItems.find(i => i.id === currentMediaId) || null;
    }, [mediaItems, currentMediaId]);

    const isVideo = (item: ConhecimentoItem) => {
        return ['mp4', 'mov', 'avi', 'webm', 'mkv'].includes(item.tipo_arquivo.toLowerCase());
    };

    useEffect(() => {
        // Auto-play when media changes
        if (currentMedia) {
            if (isVideo(currentMedia) && videoRef.current) {
                videoRef.current.load();
                videoRef.current.play().catch(e => console.error("Auto-play blocked", e));
            } else if (audioRef.current) {
                audioRef.current.load();
                audioRef.current.play().catch(e => console.error("Auto-play blocked", e));
            }
        }
    }, [currentMedia]);

    const handleMediaEnded = () => {
        // Find next media
        const currentIndex = mediaItems.findIndex(i => i.id === currentMediaId);
        if (currentIndex !== -1 && currentIndex < mediaItems.length - 1) {
            setCurrentMediaId(mediaItems[currentIndex + 1].id);
            showToast(`Reproduzindo: ${mediaItems[currentIndex + 1].titulo}`, "info");
        }
    };

    return (
        <div className="animate-in fade-in slide-in-from-bottom-4 duration-500 h-full flex flex-col md:flex-row gap-6 pb-20 md:pb-0">
            {/* Sidebar / Playlist */}
            <div className="w-full md:w-96 flex flex-col gap-4 h-[400px] md:h-auto md:max-h-[calc(100vh-120px)] bg-white rounded-[2rem] border border-slate-200 shadow-xl overflow-hidden order-2 md:order-1">
                <div className="p-6 border-b border-slate-100 bg-slate-50/50">
                    <div className="flex items-center gap-4 mb-4">
                        <button onClick={onBack} className="w-10 h-10 bg-white rounded-xl flex items-center justify-center text-slate-400 hover:text-slate-900 border border-slate-200 hover:border-slate-900 transition-all shadow-sm">
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" /></svg>
                        </button>
                        <h2 className="text-xl font-black text-slate-900 tracking-tighter">Media Player</h2>
                    </div>
                    <div className="relative">
                        <svg className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                        <input
                            type="text"
                            placeholder="Buscar mídia..."
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            className="w-full bg-white border border-slate-200 rounded-xl pl-10 pr-4 py-3 text-xs font-bold text-slate-700 focus:ring-2 focus:ring-violet-500 outline-none"
                        />
                    </div>
                </div>

                <div className="flex-1 overflow-y-auto p-4 space-y-2 custom-scrollbar">
                    {mediaItems.length === 0 ? (
                        <div className="py-12 text-center">
                            <p className="text-slate-400 text-xs font-bold uppercase tracking-widest">Nenhuma mídia encontrada</p>
                        </div>
                    ) : (
                        mediaItems.map(item => (
                            <button
                                key={item.id}
                                onClick={() => setCurrentMediaId(item.id)}
                                className={`w-full text-left p-4 rounded-2xl border transition-all group relative overflow-hidden ${currentMediaId === item.id ? 'bg-violet-600 text-white border-violet-600 shadow-lg scale-[1.02]' : 'bg-slate-50 border-slate-100 text-slate-600 hover:bg-white hover:shadow-md'}`}
                            >
                                <div className="flex items-center gap-3 relative z-10">
                                    <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${currentMediaId === item.id ? 'bg-white/20 text-white' : 'bg-white text-violet-500'}`}>
                                        {currentMediaId === item.id ? (
                                            <div className="flex gap-0.5 items-end h-3">
                                                <div className="w-0.5 bg-white animate-[bounce_1s_infinite] h-2"></div>
                                                <div className="w-0.5 bg-white animate-[bounce_1.2s_infinite] h-3"></div>
                                                <div className="w-0.5 bg-white animate-[bounce_0.8s_infinite] h-1.5"></div>
                                            </div>
                                        ) : isVideo(item) ? (
                                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
                                        ) : (
                                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" /></svg>
                                        )}
                                    </div>
                                    <div className="min-w-0">
                                        <p className="text-xs font-black truncate">{item.titulo}</p>
                                        <p className={`text-[9px] font-bold uppercase tracking-widest mt-0.5 ${currentMediaId === item.id ? 'text-white/60' : 'text-slate-400'}`}>
                                            {item.categoria || 'Geral'} • {isVideo(item) ? 'Vídeo' : 'Áudio'}
                                        </p>
                                    </div>
                                </div>
                            </button>
                        ))
                    )}
                </div>

                <div className="p-4 bg-slate-50 border-t border-slate-100 text-center">
                    <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">{mediaItems.length} Arquivos de Mídia</p>
                </div>
            </div>

            {/* Main Player */}
            <div className="flex-1 bg-black rounded-[2.5rem] overflow-hidden shadow-2xl flex flex-col items-center justify-center relative order-1 md:order-2 min-h-[400px]">
                {currentMedia ? (
                    <>
                        {isVideo(currentMedia) ? (
                            <video
                                ref={videoRef}
                                src={currentMedia.url_drive}
                                controls
                                className="w-full h-full object-contain"
                                onEnded={handleMediaEnded}
                            >
                                Seu navegador não suporta o elemento de vídeo.
                            </video>
                        ) : (
                            <div className="w-full h-full flex flex-col items-center justify-center bg-gradient-to-br from-slate-900 to-slate-800 text-white p-10 relative overflow-hidden">
                                {/* Visualizer FX */}
                                <div className="absolute inset-0 opacity-20">
                                    <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-violet-500 rounded-full blur-[100px] animate-pulse"></div>
                                </div>

                                <div className="relative z-10 text-center space-y-8">
                                    <div className="w-48 h-48 bg-slate-800 rounded-full border-4 border-slate-700 flex items-center justify-center shadow-2xl mx-auto relative group">
                                        <div className="absolute inset-0 rounded-full border-4 border-violet-500/30 animate-[spin_4s_linear_infinite]"></div>
                                        <svg className="w-20 h-20 text-violet-400 drop-shadow-[0_0_15px_rgba(167,139,250,0.5)]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" /></svg>
                                    </div>

                                    <div className="space-y-2">
                                        <h2 className="text-2xl font-black tracking-tight">{currentMedia.titulo}</h2>
                                        <p className="text-sm font-medium text-slate-400 uppercase tracking-widest">{currentMedia.categoria || 'Áudio'}</p>
                                    </div>

                                    <audio
                                        ref={audioRef}
                                        src={currentMedia.url_drive}
                                        controls
                                        className="w-full max-w-md mx-auto"
                                        onEnded={handleMediaEnded}
                                    />
                                </div>
                            </div>
                        )}
                        <div className="absolute top-6 right-6 z-20">
                             <a href={currentMedia.url_drive} target="_blank" rel="noopener noreferrer" className="bg-black/50 hover:bg-black/80 text-white p-3 rounded-full backdrop-blur-sm transition-all" title="Abrir no navegador">
                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                             </a>
                        </div>
                    </>
                ) : (
                    <div className="text-center text-slate-500 space-y-4">
                        <div className="w-20 h-20 bg-white/5 rounded-3xl flex items-center justify-center mx-auto mb-4 border border-white/10">
                            <svg className="w-10 h-10 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                        </div>
                        <p className="font-bold text-lg">Selecione uma mídia para reproduzir</p>
                        <p className="text-xs uppercase tracking-widest opacity-50">Escolha na lista ao lado</p>
                    </div>
                )}
            </div>
        </div>
    );
};
