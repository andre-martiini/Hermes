import sys

with open('src/views/DiarioBordoUI.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. ADD import EmojiPicker
if "import EmojiPicker from 'emoji-picker-react';" not in content:
    content = content.replace("import { ensureHttpUrl, parseDiaryRichNote } from '../utils/diaryEntries';", "import { ensureHttpUrl, parseDiaryRichNote } from '../utils/diaryEntries';\nimport EmojiPicker from 'emoji-picker-react';")

# 2. Add showEmojiPicker State
old_state = """const DiarioBordoUI = ({
  task, currentTaskData, newFollowUp, setNewFollowUp, handleAddFollowUp, handleCopyMessage, handleCopyAllHistory,
  isRecording, startRecording, stopRecording, isProcessingTranscription, showAttachMenu, setShowAttachMenu,
  fileInputRef, handleFileUploadInput, setModalConfig, applyFormatting, isTimerRunning,
  diaryEndRef, handleDiaryScroll, handleEditDiaryEntry, handleDeleteDiaryEntry, isUploading,
  notifications = []
}: DiarioBordoUIProps) => {"""

new_state = old_state + "\n  const [showEmojiPicker, setShowEmojiPicker] = React.useState(false);\n"

if "const [showEmojiPicker, setShowEmojiPicker] = React.useState(false);" not in content:
    content = content.replace(old_state, new_state)

# 3. Add onPaste Handler to AutoExpandingTextarea
old_textarea = """              onKeyDown={(e: React.KeyboardEvent<HTMLTextAreaElement>) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleAddFollowUp();
                }
              }}
              placeholder="Descreva o que foi feito agora...\""""

new_textarea = """              onKeyDown={(e: React.KeyboardEvent<HTMLTextAreaElement>) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleAddFollowUp();
                }
              }}
              onPaste={(e: React.ClipboardEvent<HTMLTextAreaElement>) => {
                const pastedText = e.clipboardData.getData('text');
                if (pastedText && /\[\d{2}:\d{2}, \d{2}\/\d{2}\/\d{4}\]/.test(pastedText)) {
                  e.preventDefault();
                  const formatted = formatWhatsAppText(pastedText);
                  setNewFollowUp(newFollowUp ? newFollowUp + '\\n' + formatted : formatted);
                  return;
                }
                
                if (e.clipboardData.files && e.clipboardData.files.length > 0) {
                  e.preventDefault();
                  if (fileInputRef.current) {
                    try {
                        const dataTransfer = new DataTransfer();
                        Array.from(e.clipboardData.files).forEach(file => dataTransfer.items.add(file));
                        fileInputRef.current.files = dataTransfer.files;
                        const event = new Event('change', { bubbles: true });
                        fileInputRef.current.dispatchEvent(event);
                    } catch (err) {
                        console.error('Erro ao processar ficheiros:', err);
                    }
                  }
                }
              }}
              placeholder="Descreva o que foi feito agora...\""""

if "const pastedText = e.clipboardData.getData('text');" not in content:
    content = content.replace(old_textarea, new_textarea)

# 4. Add emoji button
old_buttons = """              <button onClick={() => applyFormatting('`')} className={`w-[20px] h-[20px] flex items-center justify-center rounded text-[8px] font-mono transition-colors ${isTimerRunning ? 'text-white/30 hover:text-white/70 hover:bg-white/10' : 'text-slate-400 hover:bg-slate-200 hover:text-slate-600'}`}>{'</>'}</button>
            </div>"""

new_buttons = """              <button onClick={() => applyFormatting('`')} className={`w-[20px] h-[20px] flex items-center justify-center rounded text-[8px] font-mono transition-colors ${isTimerRunning ? 'text-white/30 hover:text-white/70 hover:bg-white/10' : 'text-slate-400 hover:bg-slate-200 hover:text-slate-600'}`}>{'</>'}</button>

              <div className="relative">
                <button
                  onClick={() => setShowEmojiPicker(!showEmojiPicker)}
                  className={`w-[20px] h-[20px] flex items-center justify-center rounded transition-colors ${isTimerRunning ? 'text-white/30 hover:text-white/70 hover:bg-white/10' : 'text-slate-400 hover:bg-slate-200 hover:text-slate-600'}`}
                  title="Emojis"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M14.828 14.828a4 4 0 01-5.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                </button>
                {showEmojiPicker && (
                  <div className="absolute bottom-8 left-0 z-[100] shadow-2xl rounded-xl">
                    <EmojiPicker 
                      onEmojiClick={(emojiData) => {
                        setNewFollowUp(newFollowUp + emojiData.emoji);
                        setShowEmojiPicker(false);
                      }}
                      theme={isTimerRunning ? 'dark' as any : 'light' as any}
                    />
                  </div>
                )}
              </div>
            </div>"""

if "setShowEmojiPicker(!showEmojiPicker)" not in content:
    content = content.replace(old_buttons, new_buttons)


with open('src/views/DiarioBordoUI.tsx', 'w', encoding='utf-8', newline='') as f:
    f.write(content)

print("Updates DiarioBordoUI OK")
