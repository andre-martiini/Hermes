
import { GoogleGenAI } from "@google/genai";

const MODEL_NAME = 'gemini-3-flash-preview';

export async function transcribeAudio(base64Audio: string, mimeType: string): Promise<string> {
  // Fix: Initializing GoogleGenAI exactly as required by guidelines
  const ai = new GoogleGenAI({ apiKey: process.env.API_KEY });
  
  try {
    const response = await ai.models.generateContent({
      model: MODEL_NAME,
      contents: {
        parts: [
          {
            inlineData: {
              mimeType: mimeType,
              data: base64Audio,
            },
          },
          {
            text: "Transcreva exatamente o que é dito neste áudio. Se não houver fala, retorne 'Nenhuma fala detectada'. Não adicione comentários extras, apenas a transcrição.",
          },
        ],
      },
    });

    // Fix: Accessing .text property directly as per guidelines
    const text = response.text;
    return text || "Não foi possível transcrever o áudio.";
  } catch (error) {
    console.error("Erro na transcrição via Gemini:", error);
    throw new Error("Falha ao processar o áudio. Verifique sua conexão ou tente novamente.");
  }
}
