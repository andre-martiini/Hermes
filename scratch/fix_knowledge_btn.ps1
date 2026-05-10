$path = "index.tsx"
$content = [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8)

$oldBtn = 'className="fixed bottom-8 left-1/2 -translate-x-1/2 bg-slate-900 text-white px-8 py-4 rounded-2xl text-\[10px\] font-black uppercase tracking-widest shadow-2xl md:hidden z-\[60\]"'
$newBtn = 'className="fixed bottom-8 left-1/2 -translate-x-1/2 bg-slate-900 text-white border-2 border-slate-900 px-8 py-4 rounded-none text-[10px] font-mono font-black uppercase tracking-[0.2em] shadow-[4px_4px_0px_rgba(15,23,42,1)] md:hidden z-[60]"'
$content = [regex]::Replace($content, $oldBtn, $newBtn)

[System.IO.File]::WriteAllText($path, $content, [System.Text.Encoding]::UTF8)
