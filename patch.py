import os

file_path = r'c:\Users\T-GAMER\Documents\gestao-Hermes\src\views\StrategyDashboardView.tsx'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Hide the top section when selectedObjectiveId is present
search1 = '''      <div className="mb-6 flex justify-end">'''
replace1 = '''      {!selectedObjectiveId && (
        <>
          <div className="mb-6 flex justify-end animate-in fade-in duration-300">'''
content = content.replace(search1, replace1)

search2 = '''      <div className="grid gap-3 md:grid-cols-4">'''
replace2 = '''          <div className="grid gap-3 md:grid-cols-4 mb-6">'''
content = content.replace(search2, replace2)

search3 = '''<strong className="text-3xl">{stats.byPillar.filter(p => p.count > 0).length}</strong></div>
      </div>'''
replace3 = '''<strong className="text-3xl">{stats.byPillar.filter(p => p.count > 0).length}</strong></div>
          </div>
        </>
      )}'''
content = content.replace(search3, replace3)

# 2. Make the selectedObjective modal inline
search4 = '''      {selectedObjectiveId && (
        <div className="fixed inset-0 z-[85] flex items-start justify-center overflow-y-auto bg-slate-950/60 px-4 py-6 backdrop-blur-sm">
          <div className={`w-full max-w-5xl border shadow-2xl ${panelClass}`}>'''
replace4 = '''      {selectedObjectiveId && (
        <div className="animate-in slide-in-from-right-8 duration-300">
          <div className={`w-full border ${panelClass}`}>'''
content = content.replace(search4, replace4)

# 3. Hide the main list section when selectedObjectiveId is present
search5 = '''      <div className="mt-8 flex flex-col gap-6 md:flex-row">'''
replace5 = '''      {!selectedObjectiveId && (
        <div className="mt-8 flex flex-col gap-6 md:flex-row animate-in fade-in duration-300">'''
content = content.replace(search5, replace5)

search6 = '''          </div>
        </section>
      </div>
    </div>
  );
};'''
replace6 = '''          </div>
        </section>
      </div>
      )}
    </div>
  );
};'''
content = content.replace(search6, replace6)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Patched!")
