
export const generateMarkdown = (
  moduleName: string,
  description: string,
  dictionary: Record<string, string>,
  dataSections: { title: string, data: any[], columns?: string[] }[]
): string => {
  const timestamp = new Date().toLocaleString('pt-BR');
  let md = `# Exportação do Módulo: ${moduleName}\n`;
  md += `**Data da Exportação:** ${timestamp}\n\n`;

  md += `## 1. Introdução\n`;
  md += `${description}\n\n`;

  md += `## 2. Dicionário de Dados\n`;
  md += `| Campo | Significado |\n`;
  md += `|---|---|\n`;
  Object.entries(dictionary).forEach(([key, desc]) => {
    md += `| **${key}** | ${desc} |\n`;
  });
  md += `\n`;

  md += `## 3. Dados Atuais\n`;

  dataSections.forEach((section, idx) => {
    md += `### 3.${idx + 1}. ${section.title}\n`;
    if (!section.data || section.data.length === 0) {
      md += `*Nenhum registro encontrado.*\n\n`;
      return;
    }

    const keys = section.columns || Object.keys(section.data[0]);

    // Header
    md += `| ${keys.join(' | ')} |\n`;
    md += `| ${keys.map(() => '---').join(' | ')} |\n`;

    // Rows
    section.data.forEach(row => {
      md += `| ${keys.map(k => {
        const val = row[k];
        if (val === null || val === undefined) return '-';
        if (typeof val === 'object') return JSON.stringify(val);
        return String(val).replace(/\|/g, '\\|'); // Escape pipes
      }).join(' | ')} |\n`;
    });
    md += `\n`;
  });

  return md;
};

export const downloadMarkdown = (filename: string, content: string) => {
  const blob = new Blob([content], { type: 'text/markdown' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${filename}_${new Date().toISOString().split('T')[0]}.md`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
};
