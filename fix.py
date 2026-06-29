import os

file_path = r'c:\Users\T-GAMER\Documents\gestao-Hermes\src\views\StrategyDashboardView.tsx'
with open(file_path, 'r', encoding='utf-8') as f:
    text = f.read()

# Revert my buggy wrappers
text = text.replace('''      {!selectedObjectiveId && (
        <>
          <div className="mb-6 flex justify-end animate-in fade-in duration-300">''', 
'''      <div className="mb-6 flex justify-end">''')

text = text.replace('''      {!selectedObjectiveId && (
        <div className="mt-6 animate-in fade-in duration-300">''',
'''      <div className="mt-6">''')

text = text.replace('''          </div>
        </section>
      </div>
      )}
    </div>
  );
};''',
'''          </div>
        </section>
      </div>
    </div>
  );
};''')

# NOW apply the correct patch!
# 1. Hide the top section (mb-6 and grid) when selectedObjective is present
top_search = '''      <div className="mb-6 flex justify-end">'''
top_replace = '''      {!selectedObjective && (
        <>
          <div className="mb-6 flex justify-end animate-in fade-in duration-300">'''
text = text.replace(top_search, top_replace)

stats_search = '''<strong className="text-3xl">{stats.byPillar.filter(p => p.count > 0).length}</strong></div>
      </div>'''
stats_replace = '''<strong className="text-3xl">{stats.byPillar.filter(p => p.count > 0).length}</strong></div>
      </div>
      </>
      )}'''
text = text.replace(stats_search, stats_replace)

# 2. Change the modal overlay to inline
overlay_search = '''      {selectedObjective && (() => {
        const item = selectedObjective;
        const pillar = PILLARS.find(p => p.id === item.pilar) || PILLARS[0];
        const progress = computeProgress(item);
        const indicators = toIndicatorDrafts(item.indicadoresSucesso).filter(indicator => indicator.descricao.trim());
        const milestones = toMilestoneDrafts(item.marcos).filter(milestone => milestone.descricao.trim());
        const isEditingSelected = Boolean(editingDraft);
        return (
          <div className="fixed inset-0 z-[85] flex items-start justify-center overflow-y-auto bg-slate-950/60 px-4 py-6 backdrop-blur-sm">
            <div className={`w-full max-w-6xl border shadow-xl ${panelClass}`}>'''
overlay_replace = '''      {selectedObjective && (() => {
        const item = selectedObjective;
        const pillar = PILLARS.find(p => p.id === item.pilar) || PILLARS[0];
        const progress = computeProgress(item);
        const indicators = toIndicatorDrafts(item.indicadoresSucesso).filter(indicator => indicator.descricao.trim());
        const milestones = toMilestoneDrafts(item.marcos).filter(milestone => milestone.descricao.trim());
        const isEditingSelected = Boolean(editingDraft);
        return (
          <div className="animate-in slide-in-from-right-8 duration-300">
            <div className={`w-full border ${panelClass}`}>'''
text = text.replace(overlay_search, overlay_replace)

# 3. Hide the list section (mt-6) when selectedObjective is present
list_search = '''      <div className="mt-6">'''
list_replace = '''      {!selectedObjective && (
      <div className="mt-6 animate-in fade-in duration-300">'''
text = text.replace(list_search, list_replace)

end_search = '''          </div>
        </section>
      </div>
    </div>
  );
};'''
end_replace = '''          </div>
        </section>
      </div>
      )}
    </div>
  );
};'''
text = text.replace(end_search, end_replace)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(text)
print('Fixed and patched!')
