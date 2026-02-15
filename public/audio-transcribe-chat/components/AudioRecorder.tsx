
import React, { useState, useRef, useEffect } from 'react';

interface AudioRecorderProps {
  onAudioReady: (blob: Blob, base64: string, url: string) => void;
  disabled: boolean;
}

export const AudioRecorder: React.FC<AudioRecorderProps> = ({ onAudioReady, disabled }) => {
  const [isRecording, setIsRecording] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  // Fix: Changed NodeJS.Timeout to number to resolve namespace error in browser environment
  const timerRef = useRef<number | null>(null);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data);
        }
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(chunksRef.current, { type: mediaRecorder.mimeType });
        const audioUrl = URL.createObjectURL(audioBlob);
        
        // Convert to base64
        const reader = new FileReader();
        reader.readAsDataURL(audioBlob);
        reader.onloadend = () => {
          const base64String = (reader.result as string).split(',')[1];
          onAudioReady(audioBlob, base64String, audioUrl);
        };
        
        // Stop stream
        stream.getTracks().forEach(track => track.stop());
      };

      mediaRecorder.start();
      setIsRecording(true);
      setRecordingTime(0);
      // Fix: Explicitly use window.setInterval to ensure the return type is number
      timerRef.current = window.setInterval(() => {
        setRecordingTime(prev => prev + 1);
      }, 1000);
    } catch (err) {
      console.error("Falha ao acessar o microfone", err);
      alert("Por favor, permita o acesso ao microfone para gravar áudio.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      // Fix: Safe interval clearing using window.clearInterval
      if (timerRef.current !== null) {
        window.clearInterval(timerRef.current);
        timerRef.current = null;
      }
    }
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="flex items-center space-x-3">
      {isRecording ? (
        <div className="flex items-center space-x-3 bg-red-50 px-4 py-2 rounded-full border border-red-200">
          <div className="w-3 h-3 bg-red-600 rounded-full animate-pulse"></div>
          <span className="text-red-600 font-medium text-sm tabular-nums">
            {formatTime(recordingTime)}
          </span>
          <button
            onClick={stopRecording}
            className="bg-red-600 hover:bg-red-700 text-white rounded-full p-2 transition-colors"
            title="Parar Gravação"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8 7a1 1 0 00-1-1H7a1 1 0 00-1 1v6a1 1 0 001 1h1a1 1 0 001-1V7zm5 0a1 1 0 00-1-1h-1a1 1 0 00-1 1v6a1 1 0 001 1h1a1 1 0 001-1V7z" clipRule="evenodd" />
            </svg>
          </button>
        </div>
      ) : (
        <button
          onClick={startRecording}
          disabled={disabled}
          className={`bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300 text-white rounded-full p-4 shadow-lg transition-all transform hover:scale-105 active:scale-95`}
          title="Gravar Áudio"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
          </svg>
        </button>
      )}
    </div>
  );
};
