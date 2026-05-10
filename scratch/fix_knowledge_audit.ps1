$path = "KnowledgeView.tsx"
$content = [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8)

# 1. Loading State
$loadingPattern = 'className="bg-white rounded-2xl border border-slate-200 p-8 mb-6 flex items-center gap-4 shadow-sm"'
$newLoading = 'className="bg-slate-50 border-4 border-slate-900 rounded-none p-8 mb-6 flex items-center gap-4 shadow-[4px_4px_0px_rgba(15,23,42,1)] font-mono"'
$content = [regex]::Replace($content, $loadingPattern, $newLoading)

# 2. Error State
$errorPattern = 'className="bg-rose-50 border border-rose-200 rounded-2xl p-5 mb-6"'
$newError = 'className="bg-rose-50 border-4 border-rose-600 rounded-none p-5 mb-6 shadow-[4px_4px_0px_rgba(225,29,72,1)] font-mono"'
$content = [regex]::Replace($content, $errorPattern, $newError)

# 3. Empty State Icon
$emptyIconPattern = 'className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-slate-100 flex items-center justify-center"'
$newEmptyIcon = 'className="w-16 h-16 mx-auto mb-4 rounded-none border-2 border-slate-900 bg-slate-50 flex items-center justify-center shadow-[4px_4px_0px_rgba(15,23,42,1)]"'
$content = [regex]::Replace($content, $emptyIconPattern, $newEmptyIcon)

# 4. Auditoria Mode Sidebar (mode === 'audit')
$auditSidebarPattern = 'className="bg-white rounded-3xl border border-slate-200 p-4 shadow-sm"'
$newAuditSidebar = 'className="bg-white border-4 border-slate-900 rounded-none p-4 shadow-[8px_8px_0px_rgba(15,23,42,1)] font-mono"'
$content = [regex]::Replace($content, $auditSidebarPattern, $newAuditSidebar)

# 5. Auditoria Mode Memory Item
$memoryItemPattern = 'className="w-full text-left p-3 rounded-2xl hover:bg-slate-50 transition-colors border border-transparent hover:border-slate-200"'
$newMemoryItem = 'className="w-full text-left p-3 rounded-none border-2 transition-colors border-transparent hover:border-slate-900 hover:bg-slate-50 hover:shadow-[2px_2px_0px_rgba(15,23,42,1)]"'
$content = [regex]::Replace($content, $memoryItemPattern, $newMemoryItem)

$memoryActiveItemPattern = 'className="w-full text-left p-3 rounded-2xl transition-colors bg-slate-900 text-white shadow-lg"'
$newMemoryActiveItem = 'className="w-full text-left p-3 rounded-none transition-colors bg-slate-900 text-white border-2 border-slate-900 shadow-[2px_2px_0px_rgba(15,23,42,1)]"'
$content = [regex]::Replace($content, $memoryActiveItemPattern, $newMemoryActiveItem)

# 6. Auditoria Mode Textarea
$textareaPattern = 'className="w-full h-\[300px\] md:h-\[400px\] p-5 rounded-3xl border border-slate-200 bg-slate-50 text-slate-700 font-medium leading-relaxed resize-none focus:outline-none focus:border-slate-400 focus:bg-white transition-all"'
$newTextarea = 'className="w-full h-[300px] md:h-[400px] p-5 rounded-none border-4 border-slate-900 bg-slate-50 text-slate-900 font-mono text-sm leading-relaxed resize-none focus:outline-none focus:bg-white shadow-[inset_2px_2px_4px_rgba(0,0,0,0.05)] focus:shadow-[inset_2px_2px_4px_rgba(0,0,0,0.05)]"'
$content = [regex]::Replace($content, $textareaPattern, $newTextarea)

# 7. Audit Buttons
$auditBtnSavePattern = 'className="px-6 py-3 rounded-xl bg-slate-900 text-white text-\[10px\] font-black uppercase tracking-widest hover:bg-slate-800 disabled:opacity-50 transition-all active:scale-95 shadow-sm"'
$newAuditBtnSave = 'className="px-6 py-3 rounded-none bg-primary-tactile text-white border-2 border-slate-900 text-[10px] font-mono font-black uppercase tracking-[0.2em] hover:bg-slate-900 disabled:opacity-50 transition-all active:scale-95 shadow-[4px_4px_0px_rgba(15,23,42,1)]"'
$content = [regex]::Replace($content, $auditBtnSavePattern, $newAuditBtnSave)

$auditBtnDelPattern = 'className="px-6 py-3 rounded-xl bg-rose-50 text-rose-700 text-\[10px\] font-black uppercase tracking-widest hover:bg-rose-100 disabled:opacity-50 transition-all active:scale-95"'
$newAuditBtnDel = 'className="px-6 py-3 rounded-none bg-white text-rose-600 border-2 border-rose-600 text-[10px] font-mono font-black uppercase tracking-[0.2em] hover:bg-rose-50 hover:shadow-[4px_4px_0px_rgba(225,29,72,1)] disabled:opacity-50 transition-all active:scale-95"'
$content = [regex]::Replace($content, $auditBtnDelPattern, $newAuditBtnDel)

[System.IO.File]::WriteAllText($path, $content, [System.Text.Encoding]::UTF8)
