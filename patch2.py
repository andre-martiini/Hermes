import os

file_path = r'c:\Users\T-GAMER\Documents\gestao-Hermes\src\views\StrategyDashboardView.tsx'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

search5 = '''      <div className="mt-6">'''
replace5 = '''      {!selectedObjectiveId && (
        <div className="mt-6 animate-in fade-in duration-300">'''
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
