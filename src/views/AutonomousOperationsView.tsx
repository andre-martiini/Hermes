import React, { useEffect, useMemo, useRef, useState } from 'react';
import { httpsCallable } from 'firebase/functions';
import mammoth from 'mammoth';
import { getDocument, GlobalWorkerOptions } from 'pdfjs-dist';
import { functions } from '@/firebase';

GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString();

declare global {
  interface Window {
    gapi: any;
    google: any;
  }
}

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined;
const GOOGLE_PICKER_API_KEY = import.meta.env.VITE_GOOGLE_PICKER_API_KEY as string | undefined;
const DRIVE_SCOPE = 'https://www.googleapis.com/auth/drive.readonly';

type ToastType = 'success' | 'error' | 'info';

interface AutonomousOperationsViewProps {
  showToast?: (message: string, type: ToastType) => void;
}

interface ProspectDraft {
  id: string;
  title: string;
  createdAt: string;
  status: 'processing';
  urgent: boolean;
  sourceSummary: string;
}

interface UploadedTranscriptFile {
  id: string;
  file: File;
  extractedText: string;
}

const ACCEPTED_EXTENSIONS = ['txt', 'docx', 'pdf', 'md', 'markdown'];
const ACCEPTED_TYPES = '.txt,.docx,.pdf,.md,.markdown,text/plain,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/markdown';
const MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024;

const formatBytes = (value: number) => {
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`;
  return `${(value / 1024 / 1024).toFixed(2)} MB`;
};

const getExtension = (fileName: string) => fileName.split('.').pop()?.toLowerCase() ?? '';

const getFileKindLabel = (file: File) => {
  const extension = getExtension(file.name);
  if (extension === 'pdf') return 'PDF';
  if (extension === 'docx') return 'DOCX';
  if (extension === 'txt') return 'TXT';
  return 'MD';
};

const inferProspectTitle = (text: string) => {
  const clean = text.replace(/\s+/g, ' ').trim();
  if (!clean) return 'Nova Prospecção';
  return clean.slice(0, 56) + (clean.length > 56 ? '...' : '');
};

const extractTextFromPdf = async (file: File) => {
  const buffer = await file.arrayBuffer();
  const pdf = await getDocument({ data: buffer }).promise;
  const pages: string[] = [];

  for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
    const page = await pdf.getPage(pageNumber);
    const content = await page.getTextContent();
    const pageText = content.items
      .map(item => ('str' in item ? item.str : ''))
      .join(' ')
      .replace(/\s+/g, ' ')
      .trim();
    if (pageText) pages.push(pageText);
  }

  return pages.join('\n\n');
};

const extractTextFromFile = async (file: File) => {
  const extension = getExtension(file.name);

  if (!ACCEPTED_EXTENSIONS.includes(extension)) {
    throw new Error('Formato não suportado. Use TXT, DOCX, PDF ou Markdown.');
  }

  if (extension === 'txt' || extension === 'md' || extension === 'markdown') {
    return (await file.text()).trim();
  }

  if (extension === 'docx') {
    const buffer = await file.arrayBuffer();
    const result = await mammoth.extractRawText({ arrayBuffer: buffer });
    return result.value.trim();
  }

  if (extension === 'pdf') {
    return extractTextFromPdf(file);
  }

  return '';
};

export function AutonomousOperationsView({ showToast }: AutonomousOperationsViewProps) {
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [brainDump, setBrainDump] = useState('');
  const [isUrgent, setIsUrgent] = useState(false);
  const [isDraggingFile, setIsDraggingFile] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState<UploadedTranscriptFile[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [prospects, setProspects] = useState<ProspectDraft[]>([]);
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribingAudio, setIsTranscribingAudio] = useState(false);
  const [audioSeconds, setAudioSeconds] = useState(0);

  const [isDriveLoading, setIsDriveLoading] = useState(false);

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const audioStreamRef = useRef<MediaStream | null>(null);
  const audioIntervalRef = useRef<number | null>(null);
  const audioTimeoutRef = useRef<number | null>(null);

  const totalExtractedCharacters = useMemo(
    () => uploadedFiles.reduce((acc, item) => acc + item.extractedText.length, 0),
    [uploadedFiles]
  );

  useEffect(() => {
    return () => {
      if (audioIntervalRef.current) window.clearInterval(audioIntervalRef.current);
      if (audioTimeoutRef.current) window.clearTimeout(audioTimeoutRef.current);
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
      if (audioStreamRef.current) {
        audioStreamRef.current.getTracks().forEach(track => track.stop());
      }
    };
  }, []);

  const resetDrawer = () => {
    setBrainDump('');
    setUploadedFiles([]);
    setIsUrgent(false);
    setIsDraggingFile(false);
    setIsRecording(false);
    setIsTranscribingAudio(false);
    setAudioSeconds(0);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const closeDrawer = () => {
    setIsDrawerOpen(false);
    resetDrawer();
  };

  const mergeExtractedTextIntoBrainDump = (text: string) => {
    const normalized = text.trim();
    if (!normalized) return;
    setBrainDump(current => (current.trim() ? `${current.trim()}\n\n${normalized}` : normalized));
  };

  const handleFileSelection = async (fileList: FileList | File[]) => {
    const files = Array.from(fileList);
    if (files.length === 0) return;

    for (const file of files) {
      const extension = getExtension(file.name);

      if (!ACCEPTED_EXTENSIONS.includes(extension)) {
        showToast?.(`"${file.name}" não é um formato aceito.`, 'error');
        continue;
      }

      if (file.size > MAX_FILE_SIZE_BYTES) {
        showToast?.(`"${file.name}" excede o limite de 15 MB.`, 'error');
        continue;
      }

      try {
        const extractedText = await extractTextFromFile(file);
        if (!extractedText.trim()) {
          showToast?.(`Não encontrei texto legível em "${file.name}".`, 'error');
          continue;
        }

        setUploadedFiles(current => [
          ...current,
          {
            id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
            file,
            extractedText,
          },
        ]);
        mergeExtractedTextIntoBrainDump(extractedText);
        showToast?.(`"${file.name}" foi carregado para a prospecção.`, 'success');
      } catch (error) {
        console.error('Erro ao carregar arquivo de prospecção:', error);
        showToast?.(`Não foi possível ler "${file.name}".`, 'error');
      }
    }
  };

  const removeUploadedFile = (id: string) => {
    setUploadedFiles(current => current.filter(item => item.id !== id));
  };

  const stopRecording = () => {
    if (audioIntervalRef.current) window.clearInterval(audioIntervalRef.current);
    if (audioTimeoutRef.current) window.clearTimeout(audioTimeoutRef.current);
    audioIntervalRef.current = null;
    audioTimeoutRef.current = null;

    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
  };

  const handleProcessAudio = async (audioBlob: Blob) => {
    setIsTranscribingAudio(true);
    try {
      const reader = new FileReader();
      reader.readAsDataURL(audioBlob);
      reader.onloadend = async () => {
        try {
          const base64String = (reader.result as string).split(',')[1];
          const transcribeFunc = httpsCallable(functions, 'transcreverAudio');
          const response = await transcribeFunc({ audioBase64: base64String, extension: '.webm' });
          const data = response.data as { raw?: string; refined?: string };
          const transcript = data.refined?.trim() || data.raw?.trim() || '';

          if (!transcript) {
            showToast?.('O áudio foi recebido, mas não retornou transcrição.', 'error');
            return;
          }

          mergeExtractedTextIntoBrainDump(transcript);
          showToast?.('Áudio transcrito e inserido no briefing.', 'success');
        } catch (error) {
          console.error('Erro ao transcrever áudio da prospecção:', error);
          showToast?.('Não foi possível transcrever o áudio agora.', 'error');
        } finally {
          setIsTranscribingAudio(false);
          setAudioSeconds(0);
        }
      };
      reader.onerror = () => {
        setIsTranscribingAudio(false);
        showToast?.('Falha ao ler o áudio gravado.', 'error');
      };
    } catch (error) {
      console.error('Erro ao preparar áudio da prospecção:', error);
      setIsTranscribingAudio(false);
      showToast?.('Falha ao preparar a gravação.', 'error');
    }
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioStreamRef.current = stream;
      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;
      audioChunksRef.current = [];
      setAudioSeconds(0);

      recorder.ondataavailable = event => {
        if (event.data.size > 0) audioChunksRef.current.push(event.data);
      };

      recorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        if (audioStreamRef.current) {
          audioStreamRef.current.getTracks().forEach(track => track.stop());
          audioStreamRef.current = null;
        }
        await handleProcessAudio(audioBlob);
      };

      recorder.start();
      setIsRecording(true);
      audioIntervalRef.current = window.setInterval(() => {
        setAudioSeconds(current => current + 1);
      }, 1000);
      audioTimeoutRef.current = window.setTimeout(() => {
        stopRecording();
      }, 120000);
    } catch (error) {
      console.error('Erro ao acessar microfone:', error);
      showToast?.('Permissão de microfone negada ou indisponível.', 'error');
    }
  };

  const loadScript = (src: string, readyCheck: () => boolean): Promise<void> =>
    new Promise((resolve, reject) => {
      if (readyCheck()) { resolve(); return; }
      const script = document.createElement('script');
      script.src = src;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error(`Falha ao carregar: ${src}`));
      document.head.appendChild(script);
    });

  const downloadAndProcessDriveFile = async (
    doc: { id: string; name: string; mimeType: string },
    accessToken: string,
  ) => {
    setIsDriveLoading(true);
    try {
      let url: string;
      let fileName = doc.name;

      if (doc.mimeType === 'application/vnd.google-apps.document') {
        url = `https://www.googleapis.com/drive/v3/files/${doc.id}/export?mimeType=text/plain`;
        if (!fileName.endsWith('.txt')) fileName += '.txt';
      } else {
        url = `https://www.googleapis.com/drive/v3/files/${doc.id}?alt=media`;
      }

      const response = await fetch(url, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });

      if (!response.ok) throw new Error(`Drive API ${response.status}`);

      const blob = await response.blob();
      const file = new File([blob], fileName, { type: blob.type || doc.mimeType });
      await handleFileSelection([file]);
    } catch (error) {
      console.error('Erro ao baixar arquivo do Drive:', error);
      showToast?.('Não foi possível baixar o arquivo do Google Drive.', 'error');
    } finally {
      setIsDriveLoading(false);
    }
  };

  const handleDriveImport = async () => {
    if (!GOOGLE_CLIENT_ID || !GOOGLE_PICKER_API_KEY) {
      showToast?.('Configure VITE_GOOGLE_CLIENT_ID e VITE_GOOGLE_PICKER_API_KEY no .env para usar o Drive.', 'error');
      return;
    }

    setIsDriveLoading(true);
    try {
      await Promise.all([
        loadScript('https://apis.google.com/js/api.js', () => !!window.gapi),
        loadScript('https://accounts.google.com/gsi/client', () => !!window.google?.accounts?.oauth2),
      ]);

      await new Promise<void>((resolve, reject) => {
        window.gapi.load('picker', { callback: resolve, onerror: reject });
      });

      const tokenClient = window.google.accounts.oauth2.initTokenClient({
        client_id: GOOGLE_CLIENT_ID,
        scope: DRIVE_SCOPE,
        callback: (tokenResponse: { error?: string; access_token: string }) => {
          if (tokenResponse.error) {
            showToast?.('Autenticação com o Google Drive recusada.', 'error');
            setIsDriveLoading(false);
            return;
          }

          const accessToken = tokenResponse.access_token;

          const picker = new window.google.picker.PickerBuilder()
            .addView(
              new window.google.picker.DocsView()
                .setMimeTypes(
                  [
                    'application/pdf',
                    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    'text/plain',
                    'text/markdown',
                    'application/vnd.google-apps.document',
                  ].join(','),
                )
                .setIncludeFolders(true),
            )
            .setOAuthToken(accessToken)
            .setDeveloperKey(GOOGLE_PICKER_API_KEY!)
            .setCallback(async (data: { action: string; docs?: { id: string; name: string; mimeType: string }[] }) => {
              if (data.action === window.google.picker.Action.PICKED && data.docs?.[0]) {
                await downloadAndProcessDriveFile(data.docs[0], accessToken);
              } else if (data.action === window.google.picker.Action.CANCEL) {
                setIsDriveLoading(false);
              }
            })
            .build();

          picker.setVisible(true);
          setIsDriveLoading(false);
        },
      });

      tokenClient.requestAccessToken({ prompt: '' });
    } catch (error) {
      console.error('Erro ao abrir o Google Drive:', error);
      showToast?.('Não foi possível abrir o Google Drive.', 'error');
      setIsDriveLoading(false);
    }
  };

  const handleSubmit = async () => {
    if (!brainDump.trim() && uploadedFiles.length === 0) {
      showToast?.('Adicione um briefing ou anexo antes de enviar.', 'info');
      return;
    }

    setIsSending(true);

    const sourceSummary =
      uploadedFiles.length > 0
        ? `${uploadedFiles.length} arquivo(s) anexado(s)`
        : 'Entrada manual';

    await new Promise(resolve => window.setTimeout(resolve, 2000));

    setProspects(current => [
      {
        id: `${Date.now()}`,
        title: inferProspectTitle(brainDump),
        createdAt: new Date().toISOString(),
        status: 'processing',
        urgent: isUrgent,
        sourceSummary,
      },
      ...current,
    ]);

    setIsSending(false);
    closeDrawer();
    showToast?.(
      'O Analista está mapeando os requisitos e gerando a Ficha de Etapa 01.',
      'info'
    );
  };

  return (
    <div className="relative min-h-[calc(100vh-12rem)] overflow-hidden rounded-[2rem] border border-slate-200 bg-[radial-gradient(circle_at_top_left,_rgba(59,130,246,0.12),_transparent_32%),linear-gradient(180deg,_#ffffff_0%,_#f8fbff_45%,_#f3f7fb_100%)]">
      <div className="absolute inset-0 bg-[linear-gradient(135deg,rgba(15,23,42,0.02)_25%,transparent_25%,transparent_50%,rgba(15,23,42,0.02)_50%,rgba(15,23,42,0.02)_75%,transparent_75%,transparent)] bg-[length:28px_28px] opacity-40" />

      <div className="relative p-6 md:p-8 lg:p-10">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-3xl">
            <p className="text-[10px] font-black uppercase tracking-[0.32em] text-cyan-700">Ecossistema de Agentes</p>
            <h1 className="mt-3 text-3xl font-black tracking-tight text-slate-950 md:text-5xl">
              Sala de entrada para novas prospecções
            </h1>
            <p className="mt-4 max-w-2xl text-sm font-medium leading-relaxed text-slate-600 md:text-base">
              Este fluxo recebe texto livre, áudio e arquivos brutos para preparar o primeiro briefing
              comercial no Hermes. O agente ainda será modelado depois, mas a captação já fica pronta.
            </p>
          </div>

          <div className="flex justify-end">
            <button
              onClick={() => setIsDrawerOpen(true)}
              className="group inline-flex items-center gap-3 rounded-full bg-gradient-to-r from-blue-700 via-cyan-600 to-sky-500 px-6 py-4 text-sm font-black tracking-wide text-white shadow-[0_20px_50px_rgba(14,116,217,0.28)] transition-all hover:-translate-y-0.5 hover:shadow-[0_24px_60px_rgba(14,116,217,0.35)]"
            >
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-white/16">
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.7" d="M12 5v14m-7-7h14" />
                </svg>
              </span>
              <span className="flex items-center gap-2">
                Nova Prospecção
                <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M12 2l1.7 4.6L18 8.3l-4.3 1.7L12 14.6l-1.7-4.6L6 8.3l4.3-1.7L12 2zm7 10l1 2.7 2.7 1L20 16.7 19 19.4l-1-2.7-2.7-1 2.7-1L19 12zm-14 1l1.1 3 3 1.1-3 1.1L5 21l-1.1-2.8-3-1.1 3-1.1L5 13z" />
                </svg>
              </span>
            </button>
          </div>
        </div>

        <div className="mt-10 grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
          <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-[0_20px_60px_rgba(15,23,42,0.06)] backdrop-blur">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-[10px] font-black uppercase tracking-[0.28em] text-slate-400">Pipeline Inicial</p>
                <h2 className="mt-2 text-xl font-black text-slate-900">Prospecções em processamento</h2>
              </div>
              <span className="rounded-full bg-blue-50 px-3 py-1 text-[10px] font-black uppercase tracking-[0.24em] text-blue-700">
                {prospects.length} itens
              </span>
            </div>

            <div className="mt-6 space-y-4">
              {prospects.length === 0 ? (
                <div className="rounded-[1.75rem] border border-dashed border-slate-200 bg-slate-50/70 px-6 py-10 text-center">
                  <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-900 text-white shadow-lg">
                    <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                  </div>
                  <p className="mt-4 text-base font-black text-slate-800">Nenhuma prospecção enviada ainda</p>
                  <p className="mt-2 text-sm font-medium leading-relaxed text-slate-500">
                    Use o botão no canto superior direito para abrir a gaveta, colar a transcrição ou anexar
                    os arquivos brutos da nova oportunidade.
                  </p>
                </div>
              ) : (
                prospects.map(item => (
                  <article
                    key={item.id}
                    className="rounded-[1.75rem] border border-amber-100 bg-gradient-to-r from-amber-50 via-white to-cyan-50 px-5 py-5 shadow-sm"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="text-base font-black text-slate-900">{item.title}</p>
                        <p className="mt-1 text-sm font-medium text-slate-500">{item.sourceSummary}</p>
                      </div>
                      {item.urgent && (
                        <span className="rounded-full bg-rose-100 px-3 py-1 text-[10px] font-black uppercase tracking-[0.22em] text-rose-600">
                          Imediata
                        </span>
                      )}
                    </div>
                    <div className="mt-4 flex items-center justify-between gap-4">
                      <span className="inline-flex items-center gap-2 rounded-full bg-amber-100 px-3 py-2 text-[10px] font-black uppercase tracking-[0.24em] text-amber-700">
                        <span className="h-2 w-2 rounded-full bg-amber-500 animate-pulse" />
                        Agente Analista Processando...
                      </span>
                      <span className="text-xs font-bold text-slate-400">
                        {new Date(item.createdAt).toLocaleString('pt-BR')}
                      </span>
                    </div>
                  </article>
                ))
              )}
            </div>
          </section>

          <aside className="rounded-[2rem] border border-slate-200/80 bg-slate-950 p-6 text-white shadow-[0_20px_60px_rgba(15,23,42,0.16)]">
            <p className="text-[10px] font-black uppercase tracking-[0.28em] text-cyan-300">Entrada do Analista</p>
            <h2 className="mt-2 text-2xl font-black tracking-tight">O que este botão já cobre</h2>
            <div className="mt-6 space-y-4 text-sm font-medium leading-relaxed text-slate-300">
              <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-4">
                Brain dump livre para briefing cru, ata de reunião ou observações rápidas.
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-4">
                Captura por microfone com transcrição automática e limite de até 2 minutos.
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-4">
                Leitura imediata de arquivos `txt`, `docx`, `pdf`, `md` e `markdown` — local ou via Google Drive.
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-4">
                Sinalizador de urgência e feedback de envio com card de processamento.
              </div>
            </div>
          </aside>
        </div>
      </div>

      <div
        className={`fixed inset-0 z-[240] bg-slate-950/45 backdrop-blur-sm transition-opacity duration-300 ${isDrawerOpen ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0'}`}
        onClick={closeDrawer}
      />

      <aside
        className={`fixed right-0 top-0 z-[250] flex h-full w-full max-w-2xl flex-col overflow-hidden border-l border-white/20 bg-white shadow-[0_30px_90px_rgba(15,23,42,0.25)] transition-transform duration-300 ${isDrawerOpen ? 'translate-x-0' : 'translate-x-full'}`}
      >
        <div className="border-b border-slate-100 bg-gradient-to-br from-blue-50 via-white to-cyan-50 px-6 py-6 md:px-8">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-[10px] font-black uppercase tracking-[0.28em] text-blue-600">Gatilho de Entrada</p>
              <h2 className="mt-2 text-2xl font-black tracking-tight text-slate-950">Nova Prospecção</h2>
              <p className="mt-2 max-w-lg text-sm font-medium leading-relaxed text-slate-500">
                Cole a transcrição, grave um resumo rápido ou anexe os materiais brutos para o Analista.
              </p>
            </div>
            <button
              onClick={closeDrawer}
              className="rounded-2xl p-3 text-slate-400 transition-colors hover:bg-white hover:text-slate-700"
            >
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-6 md:px-8 md:py-8">
          <div className="space-y-6">
            <section className="rounded-[2rem] border border-slate-200 bg-white p-4 shadow-sm">
              <div className="mb-4 flex items-center justify-between gap-4">
                <div>
                  <p className="text-[10px] font-black uppercase tracking-[0.24em] text-slate-400">Brain Dump</p>
                  <h3 className="mt-1 text-lg font-black text-slate-900">Entrada livre</h3>
                </div>
                <button
                  onClick={isRecording ? stopRecording : startRecording}
                  disabled={isTranscribingAudio}
                  className={`inline-flex h-12 w-12 items-center justify-center rounded-2xl border transition-all ${isRecording ? 'border-rose-500 bg-rose-500 text-white shadow-lg shadow-rose-100' : isTranscribingAudio ? 'border-blue-200 bg-blue-50 text-blue-500' : 'border-slate-200 bg-slate-50 text-slate-500 hover:border-blue-300 hover:bg-blue-50 hover:text-blue-600'}`}
                  title={isRecording ? 'Parar gravação' : 'Gravar áudio'}
                >
                  {isTranscribingAudio ? (
                    <div className="h-5 w-5 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
                  ) : isRecording ? (
                    <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M6 6h12v12H6z" />
                    </svg>
                  ) : (
                    <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                    </svg>
                  )}
                </button>
              </div>

              <div className="rounded-[1.5rem] border border-slate-100 bg-slate-50">
                <textarea
                  value={brainDump}
                  onChange={event => setBrainDump(event.target.value)}
                  placeholder="Cole aqui o briefing do cliente, observações da reunião, uma transcrição pronta ou qualquer contexto cru."
                  className="min-h-[260px] w-full resize-none rounded-[1.5rem] bg-transparent px-5 py-5 text-sm font-medium leading-relaxed text-slate-700 outline-none placeholder:text-slate-300"
                />
              </div>

              <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-xs font-bold">
                <span className="text-slate-400">{brainDump.trim().length} caracteres no briefing</span>
                <span className={`${isRecording ? 'text-rose-500' : 'text-slate-400'}`}>
                  {isRecording ? `Gravando ${audioSeconds}s de 120s` : 'Microfone para resumo rápido'}
                </span>
              </div>
            </section>

            <section
              onDragOver={event => {
                event.preventDefault();
                setIsDraggingFile(true);
              }}
              onDragLeave={() => setIsDraggingFile(false)}
              onDrop={async event => {
                event.preventDefault();
                setIsDraggingFile(false);
                await handleFileSelection(event.dataTransfer.files);
              }}
              className={`rounded-[2rem] border-2 border-dashed p-5 transition-all ${isDraggingFile ? 'border-blue-400 bg-blue-50' : 'border-slate-200 bg-slate-50/80'}`}
            >
              <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                <div>
                  <p className="text-[10px] font-black uppercase tracking-[0.24em] text-slate-400">Anexos</p>
                  <h3 className="mt-1 text-lg font-black text-slate-900">Zona de drop</h3>
                  <p className="mt-2 max-w-lg text-sm font-medium leading-relaxed text-slate-500">
                    Arraste aqui o PDF do cliente, o `docx` da reunião, um `.txt` exportado ou um arquivo Markdown.
                  </p>
                </div>
                <div className="flex flex-col gap-2 sm:flex-row">
                  <button
                    onClick={handleDriveImport}
                    disabled={isDriveLoading}
                    className="inline-flex items-center justify-center gap-2 rounded-full border border-slate-200 bg-white px-5 py-3 text-[11px] font-black uppercase tracking-[0.24em] text-slate-700 transition-all hover:border-blue-300 hover:text-blue-600 disabled:opacity-50"
                  >
                    {isDriveLoading ? (
                      <div className="h-3.5 w-3.5 rounded-full border-2 border-current border-t-transparent animate-spin" />
                    ) : (
                      <svg className="h-3.5 w-3.5" viewBox="0 0 87.3 78" fill="currentColor">
                        <path d="M6.6 66.85l3.85 6.65c.8 1.4 1.95 2.5 3.3 3.3L27.5 53H0c0 1.55.4 3.1 1.2 4.5z" fill="#0066da" />
                        <path d="M43.65 25L29.9 0c-1.35.8-2.5 1.9-3.3 3.3L1.2 48.5c-.8 1.4-1.2 2.95-1.2 4.5h27.5z" fill="#00ac47" />
                        <path d="M73.55 76.8c1.35-.8 2.5-1.9 3.3-3.3l1.6-2.75L86.1 57.5c.8-1.4 1.2-2.95 1.2-4.5H59.8l5.85 11.25z" fill="#ea4335" />
                        <path d="M43.65 25L57.4 0H29.9z" fill="#00832d" />
                        <path d="M59.8 53H87.3c0-1.55-.4-3.1-1.2-4.5L60.8 3.3C60 1.9 58.85.8 57.5 0L43.75 25z" fill="#2684fc" />
                        <path d="M43.65 53L27.5 53l-13.65 23.8c1.35.8 2.9 1.2 4.5 1.2h51.25c1.6 0 3.15-.45 4.5-1.2z" fill="#ffba00" />
                      </svg>
                    )}
                    Google Drive
                  </button>
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="inline-flex items-center justify-center rounded-full border border-slate-200 bg-white px-5 py-3 text-[11px] font-black uppercase tracking-[0.24em] text-slate-700 transition-all hover:border-blue-300 hover:text-blue-600"
                  >
                    Selecionar arquivo
                  </button>
                </div>
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept={ACCEPTED_TYPES}
                  className="hidden"
                  onChange={async event => {
                    if (event.target.files) {
                      await handleFileSelection(event.target.files);
                      event.target.value = '';
                    }
                  }}
                />
              </div>

              <div className="mt-5 rounded-[1.5rem] border border-white/80 bg-white/80 px-4 py-4">
                <div className="flex flex-wrap items-center gap-3 text-[11px] font-bold uppercase tracking-[0.2em] text-slate-400">
                  <span>Formatos: TXT, DOCX, PDF, MD</span>
                  <span>Texto extraído: {totalExtractedCharacters.toLocaleString('pt-BR')} caracteres</span>
                </div>

                <div className="mt-4 space-y-3">
                  {uploadedFiles.length === 0 ? (
                    <p className="text-sm font-medium text-slate-400">
                      Nenhum anexo carregado ainda. Ao enviar um arquivo compatível, o conteúdo cai no campo acima.
                    </p>
                  ) : (
                    uploadedFiles.map(item => (
                      <div
                        key={item.id}
                        className="flex items-center justify-between gap-4 rounded-2xl border border-slate-100 bg-slate-50 px-4 py-3"
                      >
                        <div className="min-w-0">
                          <div className="flex items-center gap-3">
                            <span className="rounded-xl bg-slate-900 px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.2em] text-white">
                              {getFileKindLabel(item.file)}
                            </span>
                            <p className="truncate text-sm font-black text-slate-900">{item.file.name}</p>
                          </div>
                          <p className="mt-1 text-xs font-medium text-slate-500">
                            {formatBytes(item.file.size)} • {item.extractedText.length.toLocaleString('pt-BR')} caracteres lidos
                          </p>
                        </div>
                        <button
                          onClick={() => removeUploadedFile(item.id)}
                          className="rounded-xl px-3 py-2 text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 transition-colors hover:bg-rose-50 hover:text-rose-500"
                        >
                          Remover
                        </button>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </section>

            <section className="rounded-[2rem] border border-slate-200 bg-white px-5 py-5 shadow-sm">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-[10px] font-black uppercase tracking-[0.24em] text-slate-400">Prioridade</p>
                  <h3 className="mt-1 text-lg font-black text-slate-900">Análise imediata?</h3>
                  <p className="mt-2 text-sm font-medium leading-relaxed text-slate-500">
                    Se ativado, esta entrada sinaliza prioridade alta quando o agente for modelado.
                  </p>
                </div>

                <button
                  onClick={() => setIsUrgent(current => !current)}
                  className={`relative h-10 w-20 rounded-full transition-all ${isUrgent ? 'bg-blue-600' : 'bg-slate-200'}`}
                  aria-pressed={isUrgent}
                >
                  <span
                    className={`absolute top-1 h-8 w-8 rounded-full bg-white shadow-md transition-all ${isUrgent ? 'left-11' : 'left-1'}`}
                  />
                </button>
              </div>
            </section>
          </div>
        </div>

        <div className="border-t border-slate-100 bg-white px-6 py-5 md:px-8">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div className="text-xs font-medium text-slate-500">
              O agente e o JSON ainda serão modelados. Esta etapa cobre a entrada e o preparo do material bruto.
            </div>
            <div className="flex gap-3">
              <button
                onClick={closeDrawer}
                className="rounded-full px-5 py-3 text-[11px] font-black uppercase tracking-[0.24em] text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
              >
                Cancelar
              </button>
              <button
                onClick={handleSubmit}
                disabled={isSending || isTranscribingAudio}
                className="inline-flex min-w-[220px] items-center justify-center gap-3 rounded-full bg-slate-950 px-6 py-3 text-[11px] font-black uppercase tracking-[0.24em] text-white shadow-[0_18px_40px_rgba(15,23,42,0.16)] transition-all hover:bg-blue-700 disabled:cursor-wait disabled:opacity-70"
              >
                {isSending ? (
                  <>
                    <div className="h-4 w-4 rounded-full border-2 border-white/80 border-t-transparent animate-spin" />
                    Enviando
                  </>
                ) : (
                  <>
                    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M7 11l5-5m0 0l5 5m-5-5v12" />
                    </svg>
                    Enviar para Analista
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      </aside>
    </div>
  );
}
