import { describe, it, expect, vi } from 'vitest';
import * as React from 'react';

// Mock function for logic testing
const pasteProcessLogic = (
  files: File[],
  handleProcessAudio: (blob: Blob) => void,
  handleFileUploadInput: (event: any) => void
) => {
  if (files.length > 0) {
    const oggFile = files.find(f => f.type === 'audio/ogg' || f.name.endsWith('.ogg'));
    if (oggFile && handleProcessAudio) {
        handleProcessAudio(oggFile);
        const remainingFiles = files.filter(f => f !== oggFile);
        if (remainingFiles.length > 0) {
            handleFileUploadInput({ target: { files: remainingFiles }});
        }
    } else {
        handleFileUploadInput({ target: { files: files }});
    }
  }
};

describe('Whatsapp OGG Paste Handler', () => {
    it('should intercept OGG files and pass to Transcricao IA', () => {
        const handleProcessAudio = vi.fn();
        const handleFileUploadInput = vi.fn();

        const fakeOgg = new File(['audio'], 'whatsapp.ogg', { type: 'audio/ogg' });
        const fakeTxt = new File(['text'], 'log.txt', { type: 'text/plain' });

        // User pastes an OGG and a TXT
        pasteProcessLogic([fakeOgg, fakeTxt], handleProcessAudio, handleFileUploadInput);

        // Expect Transcrição IA function to be called with OGG
        expect(handleProcessAudio).toHaveBeenCalledWith(fakeOgg);
        
        // Expect File Upload to be called with remaining files
        expect(handleFileUploadInput).toHaveBeenCalled();
        const callArgs = handleFileUploadInput.mock.calls[0][0];
        expect(callArgs.target.files).toEqual([fakeTxt]);
    });

    it('should ignore non-OGG files and upload directly', () => {
        const handleProcessAudio = vi.fn();
        const handleFileUploadInput = vi.fn();

        const fakeDoc = new File(['doc'], 'work.docx', { type: 'application/msword' });

        pasteProcessLogic([fakeDoc], handleProcessAudio, handleFileUploadInput);

        expect(handleProcessAudio).not.toHaveBeenCalled();
        expect(handleFileUploadInput).toHaveBeenCalled();
    });
});
