import sys

with open('src/utils/helpers.tsx', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Update formatWhatsAppText
text = text.replace('export const formatWhatsAppText = (text: string) => {', 'export const formatWhatsAppText = (text: string, isDarkMode: boolean = false) => {')
text = text.replace('{formatInlineWhatsAppText(line.trim().substring(2))}', '{formatInlineWhatsAppText(line.trim().substring(2), isDarkMode)}')

# Blockquote
old_bq = """      if (line.trim().startsWith('>')) {
        processedLines.push(
          <blockquote key={index} className="border-l-4 border-slate-300 pl-4 py-1 my-2 italic text-slate-500 bg-slate-50/50 rounded-r-lg">
            {formatInlineWhatsAppText(line.trim().substring(1).trim())}
          </blockquote>
        );"""

new_bq = """      if (line.trim().startsWith('>')) {
        processedLines.push(
          <blockquote key={index} className={`border-l-4 pl-4 py-1 my-2 italic rounded-r-lg ${isDarkMode ? 'border-white/20 text-white/50 bg-white/5' : 'border-slate-300 text-slate-500 bg-slate-50/50'}`}>
            {formatInlineWhatsAppText(line.trim().substring(1).trim(), isDarkMode)}
          </blockquote>
        );"""

text = text.replace(old_bq, new_bq)

# Other lines
text = text.replace('{formatInlineWhatsAppText(line)}', '{formatInlineWhatsAppText(line, isDarkMode)}')

# 2. Update formatInlineWhatsAppText
text = text.replace('export const formatInlineWhatsAppText = (text: string) => {', 'export const formatInlineWhatsAppText = (text: string, isDarkMode: boolean = false) => {')

# Pre
old_pre = """<pre className="bg-slate-100/80 p-3 rounded-lg font-mono text-[11px] my-2 overflow-x-auto border border-slate-200 text-slate-800">{inner}</pre>"""
new_pre = """<pre className={`p-3 rounded-lg font-mono text-[11px] my-2 overflow-x-auto border ${isDarkMode ? 'bg-black/30 border-white/10 text-white/80' : 'bg-slate-100/80 border-slate-200 text-slate-800'}`}>{inner}</pre>"""
text = text.replace(old_pre, new_pre)

# Code
old_code = """<code className="bg-slate-100 px-1.5 py-0.5 rounded font-mono text-[11px] text-pink-600 border border-slate-200">{inner}</code>"""
new_code = """<code className={`px-1.5 py-0.5 rounded font-mono text-[11px] border ${isDarkMode ? 'bg-black/30 border-white/10 text-pink-400' : 'bg-slate-100 border-slate-200 text-pink-600'}`}>{inner}</code>"""
text = text.replace(old_code, new_code)

# Strong
old_strong = """<strong className="font-black text-slate-900">{inner}</strong>"""
new_strong = """<strong className={`font-black ${isDarkMode ? 'text-white' : 'text-slate-900'}`}>{inner}</strong>"""
text = text.replace(old_strong, new_strong)

with open('src/utils/helpers.tsx', 'w', encoding='utf-8') as f:
    f.write(text)

print('helpers.tsx updated successfully!')
