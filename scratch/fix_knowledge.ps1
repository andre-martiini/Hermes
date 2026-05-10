$path = "KnowledgeView.tsx"
$content = [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8)

# 1. Industrialize Chip
$chipPattern = '(?s)className={`px-3 py-1\.5 rounded-full text-\[10px\] font-black uppercase tracking-widest transition-all active:scale-95 \$\{\s*active\s*\?\s*''bg-slate-900 text-white shadow-lg''\s*:\s*''bg-white text-slate-600 border border-slate-200 hover:border-slate-400''\s*\}`}'
$newChip = 'className={`px-4 py-2 rounded-none text-[10px] font-mono font-black uppercase tracking-[0.2em] transition-all active:scale-95 border-2 ${active ? ''bg-slate-900 text-white border-slate-900 shadow-[2px_2px_0px_rgba(15,23,42,1)]'' : ''bg-white text-slate-900 border-slate-900 hover:bg-slate-100 shadow-none''}`}'
$content = [regex]::Replace($content, $chipPattern, $newChip)

# 2. Industrialize Input and Button in search area
# Input: rounded-2xl bg-white border border-slate-200 text-sm md:text-base font-medium tracking-tight text-slate-900 placeholder-slate-400 shadow-sm focus:outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-900/10 transition-all
$inputPattern = 'rounded-2xl bg-white border border-slate-200 text-sm md:text-base font-medium tracking-tight text-slate-900 placeholder-slate-400 shadow-sm focus:outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-900/10 transition-all'
$newInput = 'rounded-none bg-white border-4 border-slate-900 text-sm md:text-base font-mono font-bold tracking-tight text-slate-900 placeholder-slate-400 shadow-[4px_4px_0px_rgba(15,23,42,1)] focus:outline-none focus:bg-slate-50 transition-all'
$content = [regex]::Replace($content, $inputPattern, $newInput)

# Button: rounded-xl bg-slate-900 text-white text-[10px] font-black uppercase tracking-widest hover:bg-slate-800
$buttonPattern = 'rounded-xl bg-slate-900 text-white text-\[10px\] font-black uppercase tracking-widest hover:bg-slate-800'
$newButton = 'rounded-none bg-primary-tactile border-2 border-slate-900 text-white text-[10px] font-mono font-black uppercase tracking-[0.2em] hover:bg-slate-900 shadow-[2px_2px_0px_rgba(15,23,42,1)]'
$content = [regex]::Replace($content, $buttonPattern, $newButton)

# 3. Small Date inputs: px-3 py-1.5 rounded-full bg-white border border-slate-200 text-[10px] font-bold text-slate-700 focus:outline-none focus:border-slate-900
$dateInputPattern = 'rounded-full bg-white border border-slate-200 text-\[10px\] font-bold text-slate-700 focus:outline-none focus:border-slate-900'
$newDateInput = 'rounded-none bg-white border-2 border-slate-900 text-[10px] font-mono font-bold text-slate-900 focus:outline-none focus:bg-slate-50 shadow-[2px_2px_0px_rgba(15,23,42,1)]'
$content = [regex]::Replace($content, $dateInputPattern, $newDateInput)

# 4. Small Add Tag input: px-3 py-1.5 rounded-full bg-white border border-slate-200 text-[10px] font-bold text-slate-700 placeholder-slate-400 focus:outline-none focus:border-slate-900
$tagInputPattern = 'rounded-full bg-white border border-slate-200 text-\[10px\] font-bold text-slate-700 placeholder-slate-400 focus:outline-none focus:border-slate-900'
$newTagInput = 'rounded-none bg-white border-2 border-slate-900 text-[10px] font-mono font-bold text-slate-900 placeholder-slate-400 focus:outline-none focus:bg-slate-50 shadow-[2px_2px_0px_rgba(15,23,42,1)]'
$content = [regex]::Replace($content, $tagInputPattern, $newTagInput)

# Add Tag button: rounded-full bg-slate-900 text-white text-[10px] font-black uppercase tracking-widest
$addTagButtonPattern = 'rounded-full bg-slate-900 text-white text-\[10px\] font-black uppercase tracking-widest'
$newAddTagButton = 'rounded-none bg-primary-tactile border-2 border-slate-900 text-white text-[10px] font-mono font-black uppercase tracking-[0.2em] shadow-[2px_2px_0px_rgba(15,23,42,1)]'
$content = [regex]::Replace($content, $addTagButtonPattern, $newAddTagButton)

# 5. SynthesisBlock UI
$synthesisPattern = 'bg-gradient-to-br from-slate-900 to-slate-800 text-white rounded-2xl p-6 md:p-8 shadow-2xl'
$newSynthesis = 'bg-slate-900 text-white rounded-none border-4 border-slate-900 p-6 md:p-8 relative overflow-hidden font-mono shadow-[8px_8px_0px_rgba(16,185,129,0.5)]'
$content = [regex]::Replace($content, $synthesisPattern, $newSynthesis)

# 6. KnowledgeCard UI
# bg-white rounded-2xl border transition-all p-5 flex flex-col gap-3
$cardPattern = 'bg-white rounded-2xl border transition-all p-5 flex flex-col gap-3'
$newCard = 'bg-white rounded-none border-4 transition-all p-5 flex flex-col gap-3 font-mono shadow-[4px_4px_0px_rgba(15,23,42,1)] hover:shadow-[6px_6px_0px_rgba(15,23,42,1)]'
$content = [regex]::Replace($content, $cardPattern, $newCard)

# focused card border
$focusedPattern = 'border-emerald-500 shadow-\[0_20px_50px_-10px_rgba\(16,185,129,0\.35\)\] ring-2 ring-emerald-300'
$newFocused = 'border-primary-tactile shadow-[8px_8px_0px_rgba(16,185,129,1)] scale-[1.02]'
$content = [regex]::Replace($content, $focusedPattern, $newFocused)

# default card border
$defaultCardBorderPattern = 'border-slate-200 hover:border-slate-400 hover:shadow-xl'
$newDefaultCardBorder = 'border-slate-900 hover:border-primary-tactile hover:-translate-y-1'
$content = [regex]::Replace($content, $defaultCardBorderPattern, $newDefaultCardBorder)

# 7. FileSearchCitationsBlock UI
# mt-4 bg-white rounded-2xl border border-emerald-100 p-5 shadow-sm
$citationsPattern = 'mt-4 bg-white rounded-2xl border border-emerald-100 p-5 shadow-sm'
$newCitations = 'mt-4 bg-slate-50 rounded-none border-4 border-slate-900 p-5 shadow-[4px_4px_0px_rgba(15,23,42,1)] font-mono'
$content = [regex]::Replace($content, $citationsPattern, $newCitations)

# text-left rounded-xl border border-slate-200 bg-slate-50 p-4 hover:border-emerald-300 hover:bg-emerald-50 transition-all
$citationCardPattern = 'text-left rounded-xl border border-slate-200 bg-slate-50 p-4 hover:border-emerald-300 hover:bg-emerald-50 transition-all'
$newCitationCard = 'text-left rounded-none border-2 border-slate-900 bg-white p-4 hover:border-primary-tactile hover:bg-slate-50 transition-all shadow-[2px_2px_0px_rgba(15,23,42,1)]'
$content = [regex]::Replace($content, $citationCardPattern, $newCitationCard)

# 8. Main container background and text styling
# <h1 className="text-2xl md:text-3xl font-black tracking-tight text-slate-900 mb-1">
$h1Pattern = 'text-2xl md:text-3xl font-black tracking-tight text-slate-900 mb-1'
$newH1 = 'text-3xl md:text-4xl font-black tracking-tighter uppercase text-slate-900 mb-2 font-mono'
$content = [regex]::Replace($content, $h1Pattern, $newH1)

# <div className="fixed inset-0 z-[50] bg-slate-50 md:relative md:inset-auto md:z-0 md:bg-transparent">
$bgPattern = 'fixed inset-0 z-\[50\] bg-slate-50 md:relative md:inset-auto md:z-0 md:bg-transparent'
$newBg = 'fixed inset-0 z-[50] bg-surface md:relative md:inset-auto md:z-0 md:bg-transparent font-mono'
$content = [regex]::Replace($content, $bgPattern, $newBg)

# <div className="w-full h-full bg-slate-50 overflow-y-auto">
$bg2Pattern = 'w-full h-full bg-slate-50 overflow-y-auto'
$newBg2 = 'w-full h-full bg-surface overflow-y-auto relative'
$content = [regex]::Replace($content, $bg2Pattern, $newBg2)

[System.IO.File]::WriteAllText($path, $content, [System.Text.Encoding]::UTF8)
