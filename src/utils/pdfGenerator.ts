import { jsPDF } from 'jspdf';
import { PerfilPessoa, VinculoProjeto, TipoBolsa, Projeto } from '../../types';

export const generateScholarshipForm = (
  person: PerfilPessoa,
  link: VinculoProjeto,
  project?: Projeto,
  scholarshipType?: TipoBolsa
) => {
  const doc = new jsPDF();
  const pageWidth = doc.internal.pageSize.getWidth();
  const margin = 20;
  const contentWidth = pageWidth - (margin * 2);
  let y = 20;

  // Helper for text wrapping
  const addWrappedText = (text: string, x: number, y: number, maxWidth: number, lineHeight: number = 7) => {
    const lines = doc.splitTextToSize(text, maxWidth);
    doc.text(lines, x, y);
    return lines.length * lineHeight;
  };

  // --- Header ---
  doc.setFontSize(16);
  doc.setFont('helvetica', 'bold');
  doc.text('FICHA DE CADASTRO DE BOLSISTA', pageWidth / 2, y, { align: 'center' });
  y += 15;

  if (project) {
    doc.setFontSize(12);
    doc.setFont('helvetica', 'normal');
    doc.text(`Projeto: ${project.nome}`, margin, y);
    y += 10;
  }

  // --- Personal Data Section ---
  doc.setFillColor(240, 240, 240);
  doc.rect(margin, y, contentWidth, 8, 'F');
  doc.setFontSize(10);
  doc.setFont('helvetica', 'bold');
  doc.text('1. DADOS PESSOAIS', margin + 2, y + 6);
  y += 12;

  doc.setFontSize(10);
  doc.setFont('helvetica', 'normal');

  // Row 1: Name
  doc.setFont('helvetica', 'bold');
  doc.text('Nome Completo:', margin, y);
  doc.setFont('helvetica', 'normal');
  doc.text(person.nome, margin + 35, y);
  y += 8;

  // Row 2: CPF / RG
  doc.setFont('helvetica', 'bold');
  doc.text('CPF:', margin, y);
  doc.setFont('helvetica', 'normal');
  doc.text(person.cpf, margin + 15, y);

  doc.setFont('helvetica', 'bold');
  doc.text('RG:', margin + 80, y);
  doc.setFont('helvetica', 'normal');
  doc.text(person.rg, margin + 90, y);
  y += 8;

  // Row 3: Email / Phone
  doc.setFont('helvetica', 'bold');
  doc.text('E-mail:', margin, y);
  doc.setFont('helvetica', 'normal');
  doc.text(person.email, margin + 15, y);

  doc.setFont('helvetica', 'bold');
  doc.text('Telefone:', margin + 80, y);
  doc.setFont('helvetica', 'normal');
  doc.text(person.telefone, margin + 100, y);
  y += 8;

  // Row 4: Address
  doc.setFont('helvetica', 'bold');
  doc.text('Endereço:', margin, y);
  doc.setFont('helvetica', 'normal');
  y += addWrappedText(person.endereco, margin + 20, y, contentWidth - 20) + 2;

  // Row 5: Lattes
  if (person.lattes) {
    doc.setFont('helvetica', 'bold');
    doc.text('Lattes:', margin, y);
    doc.setFont('helvetica', 'normal');
    doc.text(person.lattes, margin + 15, y);
    y += 8;
  }

  // Row 6: Banking Data
  y += 4;
  doc.setFont('helvetica', 'bold');
  doc.text('Dados Bancários:', margin, y);
  y += 6;
  doc.setFont('helvetica', 'normal');
  const bankInfo = `Banco: ${person.dados_bancarios.banco} | Agência: ${person.dados_bancarios.agencia} | Conta: ${person.dados_bancarios.conta} | PIX: ${person.dados_bancarios.chave_pix || '-'}`;
  doc.text(bankInfo, margin + 5, y);
  y += 10;

  // --- Link Data Section ---
  doc.setFillColor(240, 240, 240);
  doc.rect(margin, y, contentWidth, 8, 'F');
  doc.setFontSize(10);
  doc.setFont('helvetica', 'bold');
  doc.text('2. DADOS DO VÍNCULO', margin + 2, y + 6);
  y += 12;

  doc.setFontSize(10);

  // Type / Function
  doc.setFont('helvetica', 'bold');
  doc.text('Modalidade:', margin, y);
  doc.setFont('helvetica', 'normal');
  doc.text(scholarshipType?.nome_modalidade || 'Não especificada', margin + 25, y);

  doc.setFont('helvetica', 'bold');
  doc.text('Função:', margin + 100, y);
  doc.setFont('helvetica', 'normal');
  doc.text(link.funcao || '-', margin + 120, y);
  y += 8;

  // Dates
  doc.setFont('helvetica', 'bold');
  doc.text('Início:', margin, y);
  doc.setFont('helvetica', 'normal');
  doc.text(new Date(link.data_inicio).toLocaleDateString('pt-BR'), margin + 15, y);

  doc.setFont('helvetica', 'bold');
  doc.text('Previsão Término:', margin + 80, y);
  doc.setFont('helvetica', 'normal');
  doc.text(new Date(link.data_fim_prevista).toLocaleDateString('pt-BR'), margin + 120, y);
  y += 8;

  // Value
  doc.setFont('helvetica', 'bold');
  doc.text('Valor Mensal:', margin, y);
  doc.setFont('helvetica', 'normal');
  doc.text(new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(link.valor_bolsa_mensal_atual), margin + 30, y);

  doc.setFont('helvetica', 'bold');
  doc.text('Carga:', margin + 80, y);
  doc.setFont('helvetica', 'normal');
  doc.text(`${link.percentual_recebimento}%`, margin + 100, y);
  y += 20;

  // --- Terms Section ---
  doc.setFontSize(9);
  doc.setFont('helvetica', 'normal');
  const terms = "Declaro, para os devidos fins, que as informações acima prestadas são verdadeiras e assumo o compromisso de cumprir as atividades previstas no Plano de Trabalho do projeto, bem como comunicar imediatamente qualquer alteração nos meus dados cadastrais ou impedimento para a continuidade das atividades.";
  y += addWrappedText(terms, margin, y, contentWidth, 5) + 15;

  // --- Signatures ---
  y = Math.max(y, 220); // Push signatures to bottom if space allows

  doc.setLineWidth(0.5);

  // Beneficiary Signature
  doc.line(margin, y, margin + 70, y);
  doc.setFontSize(8);
  doc.text('Assinatura do Bolsista', margin, y + 5);
  doc.text(`CPF: ${person.cpf}`, margin, y + 9);

  // Coordinator Signature
  doc.line(pageWidth - margin - 70, y, pageWidth - margin, y);
  doc.text('Assinatura do Coordenador', pageWidth - margin - 70, y + 5);

  // Footer
  const dateStr = new Date().toLocaleDateString('pt-BR');
  doc.setFontSize(8);
  doc.text(`Gerado em: ${dateStr}`, margin, pageWidth - 10); // Using pageWidth as height proxy if simple A4, actually pageHeight
  const pageHeight = doc.internal.pageSize.getHeight();
  doc.text(`Gerado por Hermes System`, margin, pageHeight - 10);

  // Save
  doc.save(`Ficha_Cadastro_${person.nome.replace(/\s+/g, '_')}.pdf`);
};
