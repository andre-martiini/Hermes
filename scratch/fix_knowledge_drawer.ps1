$path = "KnowledgeView.tsx"
$content = [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8)

# Drawer container
$drawerPattern = 'className="fixed top-0 right-0 h-full w-full md:w-\[45%\] min-w-\[320px\] max-w-\[720px\] bg-white z-\[71\] shadow-\[0_0_60px_rgba\(0,0,0,0\.25\)\] flex flex-col animate-in slide-in-from-right duration-300"'
$newDrawer = 'className="fixed top-0 right-0 h-full w-full md:w-[45%] min-w-[320px] max-w-[720px] bg-white z-[71] border-l-4 border-slate-900 shadow-[-8px_0px_0px_rgba(15,23,42,1)] flex flex-col animate-in slide-in-from-right duration-300 font-mono"'
$content = [regex]::Replace($content, $drawerPattern, $newDrawer)

# Drawer header
$drawerHeaderPattern = 'className="px-6 py-4 border-b border-slate-200 flex items-start justify-between gap-4"'
$newDrawerHeader = 'className="px-6 py-4 border-b-4 border-slate-900 bg-slate-50 flex items-start justify-between gap-4"'
$content = [regex]::Replace($content, $drawerHeaderPattern, $newDrawerHeader)

# Close button
$closeBtnPattern = 'className="flex-shrink-0 w-9 h-9 rounded-lg bg-slate-100 hover:bg-slate-200 flex items-center justify-center transition-all active:scale-95"'
$newCloseBtn = 'className="flex-shrink-0 w-9 h-9 rounded-none border-2 border-slate-900 bg-white hover:bg-primary-tactile hover:text-white flex items-center justify-center transition-all active:scale-95 shadow-[2px_2px_0px_rgba(15,23,42,1)]"'
$content = [regex]::Replace($content, $closeBtnPattern, $newCloseBtn)

# Tabs container
$tabsPattern = 'className="flex border-b border-slate-200 px-6"'
$newTabs = 'className="flex border-b-4 border-slate-900 bg-slate-50 px-6 pt-2"'
$content = [regex]::Replace($content, $tabsPattern, $newTabs)

# Active tab
$activeTabPattern = 'text-slate-900 border-b-2 border-slate-900'
$newActiveTab = 'text-white bg-slate-900 border-t-2 border-l-2 border-r-2 border-slate-900'
$content = [regex]::Replace($content, $activeTabPattern, $newActiveTab)

# Inactive tab
$inactiveTabPattern = 'text-slate-400 hover:text-slate-600'
$newInactiveTab = 'text-slate-500 hover:bg-slate-200 border-t-2 border-l-2 border-r-2 border-transparent hover:border-slate-300'
$content = [regex]::Replace($content, $inactiveTabPattern, $newInactiveTab)

# Task item in Node Conceptual view
$taskItemPattern = 'className="group flex items-center justify-between gap-3 px-4 py-3 rounded-xl border border-slate-200 hover:border-emerald-400 hover:bg-emerald-50 transition-all text-left"'
$newTaskItem = 'className="group flex items-center justify-between gap-3 px-4 py-3 rounded-none border-2 border-slate-900 bg-white hover:border-primary-tactile hover:bg-slate-50 transition-all text-left shadow-[2px_2px_0px_rgba(15,23,42,1)]"'
$content = [regex]::Replace($content, $taskItemPattern, $newTaskItem)

[System.IO.File]::WriteAllText($path, $content, [System.Text.Encoding]::UTF8)
