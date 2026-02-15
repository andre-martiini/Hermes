
import React, { useState, useEffect } from 'react';
import { Message, SenderType } from '../types';

interface ChatBubbleProps {
  message: Message;
  onDelete: (id: string) => void;
}

export const ChatBubble: React.FC<ChatBubbleProps> = ({ message, onDelete }) => {
  const isUser = message.sender === SenderType.USER;
  const [copied, setCopied] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(false);

  // Reseta a confirmação de exclusão após 3 segundos se não for clicado novamente
  useEffect(() => {
    let timer: number;
    if (deleteConfirm) {
      timer = window.setTimeout(() => setDeleteConfirm(false), 3000);
    }
    return () => clearTimeout(timer);
  }, [deleteConfirm]);

  const handleCopy = () => {
    if (message.content) {
      navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (deleteConfirm) {
      onDelete(message.id);
    } else {
      setDeleteConfirm(true);
    }
  };

  return (
    <div className={`flex w-full mb-4 ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`group relative max-w-[80%] md:max-w-[70%] rounded-2xl p-4 shadow-sm transition-all ${
        isUser 
          ? 'bg-blue-600 text-white rounded-tr-none' 
          : 'bg-white text-gray-800 rounded-tl-none border border-gray-100'
      }`}>
        {message.audioUrl && (
          <div className="mb-3">
            <audio controls src={message.audioUrl} className={`w-full h-8 ${isUser ? 'filter invert' : ''}`} />
          </div>
        )}
        
        {message.isTranscribing ? (
          <div className="flex items-center space-x-2 text-sm italic opacity-80">
            <div className="w-2 h-2 bg-current rounded-full animate-bounce"></div>
            <div className="w-2 h-2 bg-current rounded-full animate-bounce [animation-delay:-.3s]"></div>
            <div className="w-2 h-2 bg-current rounded-full animate-bounce [animation-delay:-.5s]"></div>
            <span>Transcrevendo...</span>
          </div>
        ) : (
          <div className="relative">
            <p className="text-sm md:text-base whitespace-pre-wrap leading-relaxed">
              {message.content}
            </p>
            
            {/* Action Buttons Container - Positioned to the side */}
            <div className={`absolute -top-4 ${isUser ? '-left-10' : '-right-10'} flex flex-col space-y-2 opacity-0 group-hover:opacity-100 transition-all duration-200 z-10`}>
              {!isUser && message.content && !message.isTranscribing && (
                <button 
                  onClick={handleCopy}
                  className="p-1.5 bg-white border border-gray-200 hover:bg-gray-100 rounded-lg text-gray-500 shadow-sm transition-colors"
                  title="Copiar transcrição"
                >
                  {copied ? (
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  ) : (
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
                    </svg>
                  )}
                </button>
              )}
              
              <button 
                onClick={handleDelete}
                className={`p-1.5 rounded-lg border shadow-sm transition-all duration-200 ${
                  deleteConfirm 
                    ? 'bg-red-500 border-red-600 text-white animate-pulse' 
                    : 'bg-white border-gray-200 hover:bg-red-50 hover:border-red-100 text-gray-400 hover:text-red-500'
                }`}
                title={deleteConfirm ? "Clique novamente para apagar" : "Apagar esta mensagem"}
              >
                {deleteConfirm ? (
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                ) : (
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                )}
              </button>
            </div>
          </div>
        )}
        
        <div className={`text-[10px] mt-2 opacity-60 flex ${isUser ? 'justify-end' : 'justify-start'}`}>
          {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </div>
      </div>
    </div>
  );
};
