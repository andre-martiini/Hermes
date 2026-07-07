import React, { useState, useRef, useEffect } from 'react';
import { httpsCallable } from 'firebase/functions';
import { functions, db } from '../../../firebase';
import { collection, getDocs, query, orderBy, limit } from 'firebase/firestore';
import type { MeetingHistoryEntry } from '../tools/MeetingTranscriptionTool';
import {
  Tarefa, Status, Categoria, EntregaInstitucional,
  AppSettings, HermesModalProps, CustomNotification, TipoAcao, ActionPlanItem, ConhecimentoItem
} from '../../../types';
import { formatDate, formatDateLocalISO } from '../../../types';
import { detectAreaFromTitle, callScrapeSipac } from '../../utils/helpers';
import { isOperationalArea, STRATEGIC_AREA_OPTIONS } from '../../utils/strategicAreas';
import { WysiwygEditor } from '../ui/UIComponents';

type ThemeMode = 'system' | 'dark' | 'light';

export const HermesModal = ({ isOpen, title, message, type, onConfirm, onCancel, confirmLabel, cancelLabel }: HermesModalProps) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[500] flex items-center justify-center p-4 bg-slate-950/90 animate-in fade-in duration-300">
      <div className="bg-white w-full max-w-sm rounded-lg shadow-lg overflow-hidden animate-in zoom-in-95 duration-300 border-2 border-slate-900">
        <div className="p-8 space-y-6">
          <div className="space-y-2">
            <h3 className="text-xl font-black text-slate-900 tracking-tight font-sans uppercase">{title}</h3>
            <p className="text-xs font-bold text-slate-500 leading-relaxed font-sans">{message}</p>
          </div>
          <div className="flex gap-3">
            {type === 'confirm' && (
              <button
                onClick={onCancel}
                className="flex-1 py-4 rounded-lg text-[10px] font-bold uppercase tracking-wider text-slate-500 hover:bg-slate-100 transition-colors font-sans border border-[#e5e7eb] dark:border-white/10"
              >
                {cancelLabel || 'Cancelar'}
              </button>
            )}
            <button
              onClick={onConfirm}
              className="flex-1 bg-slate-900 text-white py-4 rounded-lg text-[10px] font-bold uppercase tracking-wider shadow-lg hover:bg-blue-600 transition-all font-sans"
            >
              {confirmLabel || (type === 'alert' ? 'OK' : 'Confirmar')}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
export const SettingsModal = ({
  settings,
  unidades,
  onSave,
  onClose,
  onAddUnidade,
  onDeleteUnidade,
  onUpdateUnidade,
  onEmitNotification,
  initialTab,
  themeMode,
  onThemeModeChange
}: {
  settings: AppSettings,
  unidades: { id: string, nome: string, palavras_chave?: string[], peso_gravidade?: number }[],
  onSave: (settings: AppSettings) => void,
  onClose: () => void,
  onAddUnidade: (nome: string) => void,
  onDeleteUnidade: (id: string) => void,
  onUpdateUnidade: (id: string, updates: any) => void,
  onEmitNotification: (title: string, message: string, type: 'info' | 'warning' | 'success' | 'error') => void,
  initialTab?: 'notifications' | 'context' | 'google',
  themeMode: ThemeMode,
  onThemeModeChange: (mode: ThemeMode) => void,
  showConfirm: (title: string, message: string, onConfirm: () => void, onCancel?: () => void) => void
}) => {
  const [localSettings, setLocalSettings] = useState<AppSettings>(settings);
  const [activeTab, setActiveTab] = useState<'notifications' | 'context' | 'google'>(initialTab || 'notifications');
  const [newUnidadeNome, setNewUnidadeNome] = useState('');
  const [newKeywordMap, setNewKeywordMap] = useState<{ [key: string]: string }>({});
  const [newCustom, setNewCustom] = useState<Partial<CustomNotification>>({
    frequency: 'daily',
    time: '09:00',
    enabled: true,
    daysOfWeek: [],
    dayOfMonth: 1
  });
  const [isAddingCustom, setIsAddingCustom] = useState(false);
  const [pendingDeleteUnidadeId, setPendingDeleteUnidadeId] = useState<string | null>(null);

  // Check for protected units only for deletion logic, not for hiding them
  // We process all units from the 'unidades' prop.

  const isDarkTheme = themeMode === 'dark';

  const handleAddKeyword = (uId: string, current: string[]) => {
    const val = newKeywordMap[uId]?.trim();
    if (!val) return;
    const updated = Array.from(new Set([...current, val]));
    onUpdateUnidade(uId, { palavras_chave: updated });
    setNewKeywordMap({ ...newKeywordMap, [uId]: '' });
  };

  const handleRemoveKeyword = (uId: string, current: string[], kw: string) => {
    const updated = current.filter(k => k !== kw);
    onUpdateUnidade(uId, { palavras_chave: updated });
  };

  return (
    <div className="fixed inset-0 z-[150] flex items-center justify-center p-0 md:p-4 bg-slate-950/90 animate-in fade-in duration-300">
      <div className={`${isDarkTheme ? 'bg-slate-950 border-slate-700' : 'bg-white border-slate-900'} w-full h-full md:h-auto md:max-w-2xl rounded-lg shadow-lg overflow-hidden animate-in zoom-in-95 duration-300 flex flex-col max-h-[90vh] border-2`}>
        <div className={`p-8 border-b ${isDarkTheme ? 'border-slate-800 bg-slate-950' : 'border-[#e5e7eb] dark:border-white/10 bg-slate-50'} flex flex-col gap-6 flex-shrink-0`}>
          <div className="flex items-center justify-between">
            <div>
              <h3 className={`text-2xl font-black ${isDarkTheme ? 'text-white' : 'text-slate-900'} tracking-tight font-sans uppercase`}>Configurações</h3>
              <p className="text-slate-400 text-[9px] font-black uppercase tracking-[0.2em] font-sans">Painel de Preferências :: System_Admin</p>
            </div>
            <button onClick={onClose} className={`p-2 rounded-lg transition-colors border border-transparent ${isDarkTheme ? 'hover:bg-slate-800 hover:border-slate-700' : 'hover:bg-slate-200 hover:border-[#e5e7eb] dark:border-white/10'}`}>
              <svg className={`w-6 h-6 ${isDarkTheme ? 'text-slate-400' : 'text-slate-500'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          </div>

          <div className={`flex ${isDarkTheme ? 'bg-slate-800 border-slate-700' : 'bg-slate-200 border-[#e5e7eb] dark:border-white/10'} p-1 rounded-lg gap-1 border`}>
            <button
              onClick={() => setActiveTab('notifications')}
              className={`flex-1 py-4 rounded-lg flex items-center justify-center transition-all ${activeTab === 'notifications' ? 'bg-slate-900 text-white border border-slate-900' : (isDarkTheme ? 'text-slate-500 hover:text-slate-300 hover:bg-slate-700/50' : 'text-slate-500 hover:text-slate-700 hover:bg-white/50')}`}
              title="Notificações"
            >
              <svg className="w-6 h-6 md:w-8 md:h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" /></svg>
            </button>
            <button
              onClick={() => setActiveTab('context')}
              className={`flex-1 py-4 rounded-lg flex items-center justify-center transition-all ${activeTab === 'context' ? 'bg-slate-900 text-white border border-slate-900' : (isDarkTheme ? 'text-slate-500 hover:text-slate-300 hover:bg-slate-700/50' : 'text-slate-500 hover:text-slate-700 hover:bg-white/50')}`}
              title="Contexto & Áreas"
            >
              <svg className="w-6 h-6 md:w-8 md:h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" /></svg>
            </button>
            <button
              onClick={() => setActiveTab('google')}
              className={`flex-1 py-4 rounded-lg flex items-center justify-center transition-all ${activeTab === 'google' ? 'bg-slate-900 text-white border border-slate-900' : (isDarkTheme ? 'text-slate-500 hover:text-slate-300 hover:bg-slate-700/50' : 'text-slate-500 hover:text-slate-700 hover:bg-white/50')}`}
              title="Google"
            >
              <svg className="w-6 h-6 md:w-8 md:h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z" /></svg>
            </button>

        </div>
      </div>

        <div className={`p-8 space-y-10 overflow-y-auto custom-scrollbar flex-1 ${isDarkTheme ? 'bg-slate-950' : ''}`}>
          <div className="space-y-4 animate-in slide-in-from-bottom-4 duration-500">
            <h4 className={`text-[10px] font-black ${isDarkTheme ? 'text-slate-100 border-slate-800' : 'text-slate-900 border-slate-100'} uppercase tracking-[0.2em] border-b pb-2 flex items-center gap-2`}>
              <span className={`w-2 h-2 ${isDarkTheme ? 'bg-slate-100' : 'bg-slate-950'} rounded-full`}></span>
              Aparência
            </h4>
            <div className={`p-5 ${isDarkTheme ? 'bg-slate-800 border-slate-700' : 'bg-slate-50 border-slate-100'} rounded-lg border`}>
              <div className="grid grid-cols-3 gap-2">
                {[
                  { mode: 'light' as ThemeMode, label: 'Claro', desc: 'Interface clara' },
                  { mode: 'dark' as ThemeMode, label: 'Escuro', desc: 'Interface escura' },
                  { mode: 'system' as ThemeMode, label: 'Sistema', desc: 'Segue o aparelho' },
                ].map(option => (
                  <button
                    key={option.mode}
                    onClick={() => onThemeModeChange(option.mode)}
                    className={`min-h-[72px] rounded-lg border px-3 py-3 text-left transition-all font-sans ${themeMode === option.mode
                      ? 'bg-slate-900 text-white border-slate-900'
                      : (isDarkTheme ? 'bg-slate-950 text-slate-400 border-slate-700 hover:border-slate-500' : 'bg-white text-slate-500 border-slate-200 hover:border-slate-400')
                      }`}
                  >
                    <p className="text-[10px] font-bold uppercase tracking-wider leading-none">{option.label}</p>
                    <p className={`text-[8px] font-bold uppercase tracking-wider mt-2 leading-tight ${themeMode === option.mode ? 'text-white/70' : (isDarkTheme ? 'text-slate-500' : 'text-slate-400')}`}>{option.desc}</p>
                  </button>
                ))}
              </div>
            </div>
          </div>
          {activeTab === 'notifications' ? (
            <>


              {/* Geral / Saúde Section */}
              <div className="space-y-4 animate-in slide-in-from-bottom-4 duration-500">
                <h4 className={`text-[10px] font-black ${isDarkTheme ? 'text-slate-100 border-slate-800' : 'text-slate-900 border-slate-100'} uppercase tracking-[0.2em] border-b pb-2 flex items-center gap-2`}>
                  <span className="w-2 h-2 bg-blue-500 rounded-full"></span>
                  Geral / Saúde
                </h4>

                <div className={`flex flex-col p-6 ${isDarkTheme ? 'bg-slate-800 border-slate-700 hover:border-rose-500/50' : 'bg-slate-50 border-slate-100 hover:border-rose-200'} rounded-lg border group transition-all gap-4`}>
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <p className={`text-sm font-bold ${isDarkTheme ? 'text-white' : 'text-slate-900'} mb-1`}>Lembrete de Pesagem</p>
                      <p className={`text-[11px] ${isDarkTheme ? 'text-slate-400' : 'text-slate-500'} font-medium`}>Registrar peso na balança</p>
                    </div>
                    <button
                      onClick={() => setLocalSettings({
                        ...localSettings,
                        notifications: {
                          ...localSettings.notifications,
                          weighInReminder: { ...localSettings.notifications.weighInReminder, enabled: !localSettings.notifications.weighInReminder.enabled }
                        }
                      })}
                      className={`w-12 h-6 rounded-full transition-all relative ${localSettings.notifications.weighInReminder.enabled ? 'bg-rose-600' : 'bg-slate-300'}`}
                    >
                      <div className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all ${localSettings.notifications.weighInReminder.enabled ? 'left-7' : 'left-1'}`} />
                    </button>
                  </div>
                  {localSettings.notifications.weighInReminder.enabled && (
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                      <select
                        value={localSettings.notifications.weighInReminder.frequency}
                        onChange={(e) => setLocalSettings({
                          ...localSettings,
                          notifications: {
                            ...localSettings.notifications,
                            weighInReminder: { ...localSettings.notifications.weighInReminder, frequency: e.target.value as any }
                          }
                        })}
                        className={`border rounded-lg px-3 py-1.5 text-[10px] font-black uppercase focus:ring-2 focus:ring-rose-500 ${isDarkTheme ? 'bg-slate-700 border-slate-600 text-white' : 'bg-white border-slate-200 text-slate-900'}`}
                      >
                        <option value="weekly">Semanal</option>
                        <option value="biweekly">Quinzenal</option>
                        <option value="monthly">Mensal</option>
                      </select>
                      <select
                        value={localSettings.notifications.weighInReminder.dayOfWeek}
                        onChange={(e) => setLocalSettings({
                          ...localSettings,
                          notifications: {
                            ...localSettings.notifications,
                            weighInReminder: { ...localSettings.notifications.weighInReminder, dayOfWeek: Number(e.target.value) }
                          }
                        })}
                        className={`border rounded-lg px-3 py-1.5 text-[10px] font-black uppercase focus:ring-2 focus:ring-rose-500 ${isDarkTheme ? 'bg-slate-700 border-slate-600 text-white' : 'bg-white border-slate-200 text-slate-900'}`}
                      >
                        <option value={0}>Domingo</option>
                        <option value={1}>Segunda</option>
                        <option value={2}>Terça</option>
                        <option value={3}>Quarta</option>
                        <option value={4}>Quinta</option>
                        <option value={5}>Sexta</option>
                        <option value={6}>Sábado</option>
                      </select>
                      <input
                        type="time"
                        value={localSettings.notifications.weighInReminder.time}
                        onChange={(e) => setLocalSettings({
                          ...localSettings,
                          notifications: {
                            ...localSettings.notifications,
                            weighInReminder: { ...localSettings.notifications.weighInReminder, time: e.target.value }
                          }
                        })}
                        className={`border rounded-lg px-3 py-1.5 text-xs font-bold focus:ring-2 focus:ring-rose-500 ${isDarkTheme ? 'bg-slate-700 border-slate-600 text-white' : 'bg-white border-slate-200 text-slate-900'}`}
                      />
                    </div>
                  )}
                </div>
              </div>

              {/* Financeiro / ações Section */}
              <div className="space-y-4 animate-in slide-in-from-bottom-4 duration-500 delay-100">
                <h4 className={`text-[10px] font-black ${isDarkTheme ? 'text-slate-100 border-slate-800' : 'text-slate-900 border-slate-100'} uppercase tracking-[0.2em] border-b pb-2 flex items-center gap-2`}>
                  <span className="w-2 h-2 bg-emerald-500 rounded-full"></span>
                  Financeiro / Ações
                </h4>

                <div className={`flex items-center justify-between p-6 ${isDarkTheme ? 'bg-slate-800 border-slate-700 hover:border-emerald-500/50' : 'bg-slate-50 border-slate-100 hover:border-emerald-200'} rounded-lg border group transition-all`}>
                  <div className="flex-1">
                    <p className={`text-sm font-bold ${isDarkTheme ? 'text-white' : 'text-slate-900'} mb-1`}>Risco Orçamentário</p>
                    <p className={`text-[11px] ${isDarkTheme ? 'text-slate-400' : 'text-slate-500'} font-medium`}>Avisar se gastos estiverem acima do esperado</p>
                  </div>
                  <button
                    onClick={() => setLocalSettings({
                      ...localSettings,
                      notifications: {
                        ...localSettings.notifications,
                        budgetRisk: { ...localSettings.notifications.budgetRisk, enabled: !localSettings.notifications.budgetRisk.enabled }
                      }
                    })}
                    className={`w-12 h-6 rounded-full transition-all relative ${localSettings.notifications.budgetRisk.enabled ? 'bg-emerald-600' : 'bg-slate-300'}`}
                  >
                    <div className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all ${localSettings.notifications.budgetRisk.enabled ? 'left-7' : 'left-1'}`} />
                  </button>
                </div>

                <div className={`flex items-center justify-between p-6 ${isDarkTheme ? 'bg-slate-800 border-slate-700 hover:border-blue-500/50' : 'bg-slate-50 border-slate-100 hover:border-blue-200'} rounded-lg border group transition-all`}>
                  <div className="flex-1">
                    <p className={`text-sm font-bold ${isDarkTheme ? 'text-white' : 'text-slate-900'} mb-1`}>Ações Vencidas</p>
                    <p className={`text-[11px] ${isDarkTheme ? 'text-slate-400' : 'text-slate-500'} font-medium`}>Alertar sobre tarefas fora do prazo</p>
                  </div>
                  <button
                    onClick={() => setLocalSettings({
                      ...localSettings,
                      notifications: {
                        ...localSettings.notifications,
                        overdueTasks: { ...localSettings.notifications.overdueTasks, enabled: !localSettings.notifications.overdueTasks.enabled }
                      }
                    })}
                    className={`w-12 h-6 rounded-full transition-all relative ${localSettings.notifications.overdueTasks.enabled ? 'bg-blue-600' : 'bg-slate-300'}`}
                  >
                    <div className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all ${localSettings.notifications.overdueTasks.enabled ? 'left-7' : 'left-1'}`} />
                  </button>
                </div>

                <div className={`flex flex-col p-6 ${isDarkTheme ? 'bg-slate-800 border-slate-700 hover:border-amber-500/50' : 'bg-slate-50 border-slate-100 hover:border-amber-200'} rounded-lg border group transition-all gap-4`}>
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <p className={`text-sm font-bold ${isDarkTheme ? 'text-white' : 'text-slate-900'} mb-1`}>Audit PGD</p>
                      <p className={`text-[11px] ${isDarkTheme ? 'text-slate-400' : 'text-slate-500'} font-medium`}>Verificar vínculos antes do fim do mês</p>
                    </div>
                    <button
                      onClick={() => setLocalSettings({
                        ...localSettings,
                        notifications: {
                          ...localSettings.notifications,
                          pgcAudit: { ...localSettings.notifications.pgcAudit, enabled: !localSettings.notifications.pgcAudit.enabled }
                        }
                      })}
                      className={`w-12 h-6 rounded-full transition-all relative ${localSettings.notifications.pgcAudit.enabled ? 'bg-amber-600' : 'bg-slate-300'}`}
                    >
                      <div className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all ${localSettings.notifications.pgcAudit.enabled ? 'left-7' : 'left-1'}`} />
                    </button>
                  </div>
                  {localSettings.notifications.pgcAudit.enabled && (
                    <div className="flex items-center gap-3">
                      <span className={`text-[10px] font-black ${isDarkTheme ? 'text-slate-400' : 'text-slate-400'} uppercase`}>Avisar</span>
                      <input
                        type="number"
                        min="1"
                        max="28"
                        value={localSettings.notifications.pgcAudit.daysBeforeEnd}
                        onChange={(e) => setLocalSettings({
                          ...localSettings,
                          notifications: {
                            ...localSettings.notifications,
                            pgcAudit: { ...localSettings.notifications.pgcAudit, daysBeforeEnd: Number(e.target.value) }
                          }
                        })}
                        className={`w-16 border-2 rounded-lg px-3 py-1.5 text-xs font-bold focus:ring-2 focus:ring-amber-500 outline-none ${isDarkTheme ? 'bg-slate-700 border-slate-600 text-white' : 'bg-white border-slate-100 text-slate-900'}`}
                      />
                      <span className="text-[10px] font-black text-slate-400 uppercase">dias antes</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Notificações Personalizadas Section */}
              <div className="space-y-4 animate-in slide-in-from-bottom-4 duration-500 delay-150">
                <div className={`flex items-center justify-between border-b ${isDarkTheme ? 'border-slate-800' : 'border-slate-100'} pb-2`}>
                  <h4 className={`text-[10px] font-black ${isDarkTheme ? 'text-slate-100' : 'text-slate-900'} uppercase tracking-[0.2em] flex items-center gap-2`}>
                    <span className="w-2 h-2 bg-purple-500 rounded-full"></span>
                    Personalizadas
                  </h4>
                  <button
                    onClick={() => setIsAddingCustom(!isAddingCustom)}
                    className={`text-[10px] font-black uppercase text-blue-500 ${isDarkTheme ? 'hover:bg-slate-800' : 'hover:bg-blue-50'} px-2 py-1 rounded-lg transition-colors`}
                  >
                    {isAddingCustom ? 'Cancelar' : '+ Nova'}
                  </button>
                </div>

                {/* Form de Adição */}
                {isAddingCustom && (
                  <div className={`${isDarkTheme ? 'bg-slate-800 border-slate-700' : 'bg-slate-50 border-blue-100'} p-4 rounded-lg border flex flex-col gap-3 animate-in fade-in slide-in-from-top-2`}>
                    <input
                      type="text"
                      placeholder="Mensagem da notificação..."
                      className={`w-full border rounded-lg px-3 py-2 text-xs font-bold focus:ring-2 focus:ring-blue-500 outline-none ${isDarkTheme ? 'bg-slate-700 border-slate-600 text-white placeholder:text-slate-500' : 'bg-white border-slate-200 text-slate-900'}`}
                      value={newCustom.message || ''}
                      onChange={e => setNewCustom({ ...newCustom, message: e.target.value })}
                    />
                    <div className="flex gap-2">
                      <select
                        className={`border rounded-lg px-3 py-2 text-[10px] font-black uppercase outline-none focus:ring-2 focus:ring-blue-500 ${isDarkTheme ? 'bg-slate-700 border-slate-600 text-white' : 'bg-white border-slate-200 text-slate-700'}`}
                        value={newCustom.frequency}
                        onChange={e => setNewCustom({ ...newCustom, frequency: e.target.value as any })}
                      >
                        <option value="daily">Diária</option>
                        <option value="weekly">Semanal</option>
                        <option value="monthly">Mensal</option>
                      </select>
                      <input
                        type="time"
                        className={`border rounded-lg px-3 py-2 text-xs font-bold outline-none focus:ring-2 focus:ring-blue-500 ${isDarkTheme ? 'bg-slate-700 border-slate-600 text-white' : 'bg-white border-slate-200 text-slate-900'}`}
                        value={newCustom.time || ''}
                        onChange={e => setNewCustom({ ...newCustom, time: e.target.value })}
                      />
                    </div>

                    {/* Conditional Frequency Inputs */}
                    {newCustom.frequency === 'weekly' && (
                      <div className="flex gap-1 flex-wrap">
                        {['D', 'S', 'T', 'Q', 'Q', 'S', 'S'].map((d, i) => (
                          <button
                            key={i}
                            onClick={() => {
                              const current = newCustom.daysOfWeek || [];
                              const updated = current.includes(i) ? current.filter(x => x !== i) : [...current, i];
                              setNewCustom({ ...newCustom, daysOfWeek: updated });
                            }}
                            className={`w-6 h-6 rounded text-[9px] font-black ${newCustom.daysOfWeek?.includes(i) ? 'bg-blue-600 text-white' : 'bg-white border border-slate-200 text-slate-400'}`}
                          >
                            {d}
                          </button>
                        ))}
                      </div>
                    )}

                    {newCustom.frequency === 'monthly' && (
                      <div className="flex items-center gap-2">
                        <span className={`text-[10px] font-black ${isDarkTheme ? 'text-slate-400' : 'text-slate-400'} uppercase`}>Dia do mês:</span>
                        <input
                          type="number"
                          min="1"
                          max="31"
                          className={`w-12 border rounded-lg px-2 py-1 text-xs font-bold outline-none focus:ring-2 focus:ring-blue-500 ${isDarkTheme ? 'bg-slate-700 border-slate-600 text-white' : 'bg-white border-slate-200 text-slate-900'}`}
                          value={newCustom.dayOfMonth || 1}
                          onChange={e => setNewCustom({ ...newCustom, dayOfMonth: Number(e.target.value) })}
                        />
                      </div>
                    )}

                    <button
                      disabled={!newCustom.message || !newCustom.time}
                      onClick={() => {
                        const notif: CustomNotification = {
                          id: Math.random().toString(36).substr(2, 9),
                          message: newCustom.message!,
                          frequency: newCustom.frequency as any,
                          time: newCustom.time!,
                          enabled: true,
                          daysOfWeek: newCustom.daysOfWeek || [],
                          dayOfMonth: newCustom.dayOfMonth || 1
                        };
                        setLocalSettings({
                          ...localSettings,
                          notifications: {
                            ...localSettings.notifications,
                            custom: [...(localSettings.notifications.custom || []), notif]
                          }
                        });
                        setIsAddingCustom(false);
                        setNewCustom({ frequency: 'daily', time: '09:00', enabled: true, daysOfWeek: [], dayOfMonth: 1 });
                      }}
                      className="bg-slate-900 text-white py-2 rounded-lg text-[10px] font-bold uppercase tracking-wider hover:bg-blue-600 transition-colors disabled:opacity-50 font-sans"
                    >
                      Salvar Notificação
                    </button>
                  </div>
                )}

                {/* Lista de Notificações Custom */}
                <div className="grid grid-cols-1 gap-3">
                  {(localSettings.notifications.custom || []).map(notif => (
                    <div key={notif.id} className={`p-4 ${isDarkTheme ? 'bg-slate-800 border-slate-700 hover:border-purple-500/50' : 'bg-white border-slate-100 hover:border-purple-200'} border rounded-lg flex items-center justify-between group transition-all`}>
                      <div>
                        <p className={`text-xs font-bold ${isDarkTheme ? 'text-white' : 'text-slate-900'} line-clamp-1`}>{notif.message}</p>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-[9px] font-black text-purple-600 bg-purple-50 px-1.5 py-0.5 rounded uppercase">
                            {notif.time}
                          </span>
                          <span className="text-[9px] font-black text-slate-400 uppercase">
                            {notif.frequency === 'daily' ? 'Diária' :
                              notif.frequency === 'weekly' ? `Semanal (${notif.daysOfWeek?.length} dias)` :
                                `Mensal (Dia ${notif.dayOfMonth})`}
                          </span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => {
                            const updated = (localSettings.notifications.custom || []).map(n =>
                              n.id === notif.id ? { ...n, enabled: !n.enabled } : n
                            );
                            setLocalSettings({ ...localSettings, notifications: { ...localSettings.notifications, custom: updated } });
                          }}
                          className={`w-8 h-4 rounded-full transition-all relative ${notif.enabled ? 'bg-purple-600' : 'bg-slate-300'}`}
                        >
                          <div className={`absolute top-0.5 w-3 h-3 bg-white rounded-full transition-all ${notif.enabled ? 'left-4.5' : 'left-0.5'}`} />
                        </button>
                        <button
                          onClick={() => {
                            const updated = (localSettings.notifications.custom || []).filter(n => n.id !== notif.id);
                            setLocalSettings({ ...localSettings, notifications: { ...localSettings.notifications, custom: updated } });
                          }}
                          className="text-slate-300 hover:text-rose-500 p-1 transition-colors"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                        </button>
                      </div>
                    </div>
                  ))}
                  {(localSettings.notifications.custom || []).length === 0 && !isAddingCustom && (
                    <div className={`text-center py-6 text-[10px] font-bold uppercase tracking-wider font-sans border-2 border-dashed rounded-lg ${isDarkTheme ? 'text-slate-600 border-slate-800' : 'text-slate-300 border-slate-100'}`}>
                      Nenhuma notificação personalizada
                    </div>
                  )}
                </div>
              </div>

            </>
          ) : activeTab === 'context' ? (
            /* Unidades / áreas e Palavras-Chave TAB */
            <div className="space-y-6 animate-in slide-in-from-right-4 duration-500">
              <h4 className={`text-[10px] font-black ${isDarkTheme ? "text-slate-100 border-slate-800" : "text-slate-900 border-slate-100"} uppercase tracking-[0.2em] border-b pb-2 flex items-center gap-2`}>
                <span className="w-2 h-2 bg-amber-500 rounded-full"></span>
                Áreas e Palavras-Chave
              </h4>

              <div className="space-y-4">
                {unidades.map((u) => {
                  const isProtected = isOperationalArea(u.nome) || u.nome.toUpperCase() === 'ASSISTÊNCIA';
                  return (
                    <div key={u.id} className={`p-6 rounded-lg border space-y-4 ${isProtected ? (isDarkTheme ? 'border-amber-700/50 bg-amber-950/20' : 'border-amber-200 bg-amber-50/30') : (isDarkTheme ? 'bg-slate-800 border-slate-700' : 'bg-slate-50 border-slate-100')}`}>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <h5 className={`text-xs font-black ${isDarkTheme ? 'text-white' : 'text-slate-900'} uppercase tracking-widest`}>{u.nome}</h5>
                          {isProtected && <span className={`${isDarkTheme ? 'bg-amber-900/40 text-amber-400 border border-amber-700/50' : 'bg-amber-100 text-amber-700'} px-2 py-0.5 rounded-lg text-[8px] font-bold uppercase tracking-wider`}>Protegido</span>}
                        </div>

                        {!isProtected && (
                          <button
                            onClick={() => { if (pendingDeleteUnidadeId !== u.id) { setPendingDeleteUnidadeId(u.id); window.setTimeout(() => setPendingDeleteUnidadeId((current) => (current === u.id ? null : current)), 3500); return; } setPendingDeleteUnidadeId(null); onDeleteUnidade(u.id); }}
                            className={`p-2 rounded-lg transition-all ${pendingDeleteUnidadeId === u.id ? 'bg-rose-500 text-white' : (isDarkTheme ? 'text-rose-400 hover:text-rose-300 hover:bg-rose-950/30' : 'text-rose-300 hover:text-rose-600 hover:bg-rose-50')}`}
                            title={pendingDeleteUnidadeId === u.id ? "Confirmar remoção" : "Remover Área"}
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                          </button>
                        )}
                      </div>

                      {/* Peso de Gravidade (G) do Score GUT — 1 a 5 */}
                      <div className={`flex items-center justify-between gap-3 border rounded-lg px-3 py-2 ${isDarkTheme ? 'bg-slate-700 border-slate-600' : 'bg-white border-slate-200'}`}>
                        <span className={`text-[9px] font-black uppercase tracking-[0.2em] ${isDarkTheme ? 'text-slate-400' : 'text-slate-500'}`}>Gravidade (G)</span>
                        <div className="flex items-center gap-1">
                          {[1, 2, 3, 4, 5].map((n) => {
                            const current = Number(u.peso_gravidade) || 1;
                            const active = current === n;
                            return (
                              <button
                                key={n}
                                type="button"
                                onClick={() => onUpdateUnidade(u.id, { peso_gravidade: n })}
                                className={`w-7 h-7 rounded-lg text-[10px] font-black transition-all ${active ? 'bg-slate-900 text-white scale-110' : (isDarkTheme ? 'bg-slate-600 text-slate-400 hover:bg-slate-500' : 'bg-slate-100 text-slate-400 hover:bg-slate-200')}`}
                                title={`Definir gravidade ${n}`}
                              >
                                {n}
                              </button>
                            );
                          })}
                        </div>
                      </div>

                      <div className="flex flex-wrap gap-2">
                        {(u.palavras_chave || []).map((kw, i) => (
                          <span key={i} className={`inline-flex items-center gap-1 px-3 py-1 border rounded-lg text-[9px] font-black uppercase group/kw ${isDarkTheme ? 'bg-slate-700 border-slate-600 text-slate-300' : 'bg-white border-slate-200 text-slate-600'}`}>
                            {kw}
                            <button onClick={() => handleRemoveKeyword(u.id, u.palavras_chave || [], kw)} className="text-slate-300 hover:text-rose-500 transition-colors">
                              <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                            </button>
                          </span>
                        ))}
                        {(u.palavras_chave || []).length === 0 && (
                          <p className="text-[10px] text-slate-400 italic">Sem palavras-chave definidas</p>
                        )}
                      </div>

                      <div className="flex gap-2">
                        <input
                          type="text"
                          placeholder="Nova palavra-chave..."
                          value={newKeywordMap[u.id] || ''}
                          onChange={(e) => setNewKeywordMap({ ...newKeywordMap, [u.id]: e.target.value })}
                          onKeyDown={(e) => e.key === 'Enter' && handleAddKeyword(u.id, u.palavras_chave || [])}
                          className={`flex-1 border rounded-lg px-4 py-2 text-[10px] font-bold focus:ring-2 focus:ring-blue-500 outline-none font-sans ${isDarkTheme ? 'bg-slate-700 border-slate-600 text-white placeholder:text-slate-500' : 'bg-white border-slate-200 text-slate-900'}`}
                        />
                        <button
                          onClick={() => handleAddKeyword(u.id, u.palavras_chave || [])}
                          className="bg-slate-900 text-white px-4 rounded-lg text-[10px] font-bold uppercase tracking-wider hover:bg-blue-600 transition-all font-sans"
                        >
                          Add
                        </button>
                      </div>
                    </div>
                  );
                })}

                <div className={`p-6 rounded-lg border-2 border-dashed flex flex-col gap-4 ${isDarkTheme ? 'bg-slate-800/50 border-slate-700' : 'bg-blue-50/50 border-blue-200'}`}>
                  <p className={`text-[10px] font-bold uppercase tracking-wider text-center font-sans ${isDarkTheme ? 'text-slate-400' : 'text-blue-600'}`}>Cadastrar Nova Área de Contexto</p>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      placeholder="Nome da Unidade (ex: DEV, MARKETING)"
                      value={newUnidadeNome}
                      onChange={(e) => setNewUnidadeNome(e.target.value)}
                      className={`flex-1 border rounded-lg px-4 py-3 text-xs font-bold focus:ring-2 focus:ring-blue-500 outline-none font-sans ${isDarkTheme ? 'bg-slate-700 border-slate-600 text-white placeholder:text-slate-500' : 'bg-white border-blue-100 text-slate-900'}`}
                    />
                    <button
                      onClick={() => {
                        if (newUnidadeNome.trim()) {
                          onAddUnidade(newUnidadeNome.trim().toUpperCase());
                          setNewUnidadeNome('');
                        }
                      }}
                      className="bg-slate-900 text-white px-6 py-3 rounded-lg text-[10px] font-bold uppercase tracking-wider hover:bg-blue-600 transition-all font-sans"
                    >
                      Criar
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ) : activeTab === 'google' ? (
            <div className="space-y-6 animate-in slide-in-from-right-4 duration-500">
              <h4 className="text-[10px] font-black text-slate-900 uppercase tracking-[0.2em] border-b border-slate-100 pb-2 flex items-center gap-2">
                <span className="w-2 h-2 bg-blue-500 rounded-full"></span>
                Integração Google Drive
              </h4>

              <div className={`p-6 rounded-lg border space-y-4 ${isDarkTheme ? 'bg-slate-800 border-slate-700' : 'bg-slate-50 border-slate-100'}`}>
                <p className={`text-xs font-medium ${isDarkTheme ? 'text-slate-400' : 'text-slate-500'}`}>
                  Configure a pasta do Google Drive onde os arquivos do Pool de Dados serão armazenados.
                </p>

                <div className="space-y-2">
                  <label className={`text-[10px] font-bold uppercase tracking-wider pl-1 ${isDarkTheme ? 'text-slate-500' : 'text-slate-400'}`}>ID da Pasta no Drive</label>
                  <input
                    type="text"
                    value={localSettings.googleDriveFolderId || ''}
                    onChange={(e) => setLocalSettings({ ...localSettings, googleDriveFolderId: e.target.value })}
                    placeholder="Ex: 1a2b3c4d5e6f7g8h9i0j..."
                    className={`w-full border rounded-lg px-4 py-3 text-xs font-sans focus:ring-2 focus:ring-blue-500 outline-none ${isDarkTheme ? 'bg-slate-700 border-slate-600 text-white placeholder:text-slate-500' : 'bg-white border-slate-200 text-slate-900'}`}
                  />
                  <p className={`text-[9px] italic ${isDarkTheme ? 'text-slate-500' : 'text-slate-400'}`}>
                    O ID da pasta é a parte final da URL da pasta no Google Drive.
                  </p>
                </div>
              </div>

              <div className={`p-6 rounded-lg border ${isDarkTheme ? 'bg-amber-950/20 border-amber-800/40' : 'bg-amber-50 border-amber-100'}`}>
                <div className="flex gap-3">
                  <svg className="w-5 h-5 text-amber-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
                  <div>
                    <p className={`text-xs font-bold uppercase tracking-wider mb-1 ${isDarkTheme ? 'text-amber-300' : 'text-amber-800'}`}>Nota sobre Permissões</p>
                    <p className={`text-[10px] leading-relaxed ${isDarkTheme ? 'text-amber-400' : 'text-amber-700'}`}>
                      Ao adicionar novos escopos (como Google Drive), pode ser necessário re-autenticar o sistema usando o <strong>setup_credentials.bat</strong> para que o Hermes tenha permissão de escrita.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          ) : null}
        </div>

        <div className={`p-8 border-t flex gap-4 flex-shrink-0 ${isDarkTheme ? 'bg-slate-950 border-slate-800' : 'bg-slate-50 border-slate-100'}`}>
          <button onClick={onClose} className={`flex-1 px-8 py-4 rounded-lg text-[10px] font-bold uppercase tracking-wider transition-all font-sans border ${isDarkTheme ? 'text-slate-400 hover:bg-slate-800 border-slate-700' : 'text-slate-500 hover:bg-slate-200 border-[#e5e7eb] dark:border-white/10'}`}>Cancelar</button>
          <button
            onClick={() => {
              onSave(localSettings);
              onClose();
            }}
            className="flex-1 bg-slate-900 text-white px-8 py-4 rounded-lg text-[10px] font-bold uppercase tracking-wider shadow-lg hover:bg-blue-600 transition-all font-sans"
          >
            Salvar Alterações
          </button>
        </div>
      </div>
    </div >
  );
};
const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

export const TaskCreateModal = ({ unidades, knowledgeBases = [], knowledgeItems = [], onSave, onClose, showAlert, initialData, existingTags = [] }: { unidades: { id: string, nome: string }[], knowledgeBases?: { id: string, nome: string, tipo?: string, sistema_id?: string }[], knowledgeItems?: ConhecimentoItem[], onSave: (data: Partial<Tarefa>) => void, onClose: () => void, showAlert: (title: string, message: string) => void, initialData?: Partial<Tarefa>, existingTags?: string[] }) => {
  const [tipoAcao, setTipoAcao] = useState<TipoAcao>('fast');
  const [origemIngestao, setOrigemIngestao] = useState<'manual' | 'audio'>('manual');
  const [isExtraContextOpen, setIsExtraContextOpen] = useState(false);
  const [extraContext, setExtraContext] = useState('');
  const [extraContextId] = useState<string>(() => crypto.randomUUID());
  const [extraContextFiles, setExtraContextFiles] = useState<{ id: string; name: string; status: 'uploading' | 'ready' | 'error' }[]>([]);
  const [inputText, setInputText] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [reunioes, setReunioes] = useState<MeetingHistoryEntry[]>([]);
  const [selectedReuniao, setSelectedReuniao] = useState<MeetingHistoryEntry | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const [isTranscriptionSelectorOpen, setIsTranscriptionSelectorOpen] = useState(false);
  const [transcriptionSearch, setTranscriptionSearch] = useState('');

  const [formData, setFormData] = useState({
    titulo: initialData?.titulo || '',
    data_limite: initialData?.data_limite || initialData?.data_inicio || formatDateLocalISO(new Date()),
    data_criacao: new Date().toISOString(),
    status: initialData?.status || 'em andamento' as Status,
    area_tematica: initialData?.area_tematica || 'GERAL' as Categoria,
    notas: initialData?.notas || '',
    descricao: initialData?.descricao || '',
    horario_inicio: initialData?.horario_inicio || '',
    horario_fim: initialData?.horario_fim || '',
    origem: 'manual' as any
  });

  const [planoAcao, setPlanoAcao] = useState<ActionPlanItem[]>([]);
  const [newChecklistItem, setNewChecklistItem] = useState('');
  const [autoClassified, setAutoClassified] = useState(false);
  const [tags, setTags] = useState<string[]>(initialData?.tags || []);
  const [tagInput, setTagInput] = useState('');
  const [recorrenciaMensal, setRecorrenciaMensal] = useState(false);
  const [diaDoMesRecorrencia, setDiaDoMesRecorrencia] = useState<number>(new Date().getDate());
  const [emailTriggerEnabled, setEmailTriggerEnabled] = useState(initialData?.email_trigger?.enabled || false);
  const [emailSender, setEmailSender] = useState(initialData?.email_trigger?.sender || '');
  const [emailSubjectKeywords, setEmailSubjectKeywords] = useState(initialData?.email_trigger?.subjectKeywords || '');
  const [emailBodyKeywords, setEmailBodyKeywords] = useState(initialData?.email_trigger?.bodyKeywords || '');
  const [emailActionToTake, setEmailActionToTake] = useState<'status_to_andamento' | 'run_ai_analysis'>(initialData?.email_trigger?.action_to_take || 'status_to_andamento');
  const [emailAiInstructions, setEmailAiInstructions] = useState(initialData?.email_trigger?.ai_instructions || '');
  const [emailTelegramAlert, setEmailTelegramAlert] = useState(initialData?.email_trigger?.telegram_alert ?? true);

  const recognitionRef = useRef<any>(null);

  const handleUploadExtraFile = async (file: File) => {
    const tempId = Math.random().toString(36).substring(2, 9);
    setExtraContextFiles(prev => [...prev, { id: tempId, name: file.name, status: 'uploading' }]);
    try {
      const base64 = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve((reader.result as string).split(',')[1]);
        reader.onerror = reject;
        reader.readAsDataURL(file);
      });
      const fn = httpsCallable(functions, 'processExtraContextFile');
      const result = await fn({ fileBase64: base64, filename: file.name, mimeType: file.type, extraContextId });
      const docId = (result.data as any).docId;
      setExtraContextFiles(prev => prev.map(f => f.id === tempId ? { ...f, id: docId, status: 'ready' } : f));
    } catch {
      setExtraContextFiles(prev => prev.map(f => f.id === tempId ? { ...f, status: 'error' } : f));
    }
  };

  // Load recent meetings from Firestore for linking
  useEffect(() => {
    const loadReunioes = async () => {
      try {
        const q = query(collection(db, 'reunioes'), orderBy('startedAt', 'desc'), limit(10));
        const snapshot = await getDocs(q);
        const entries: MeetingHistoryEntry[] = snapshot.docs.map(doc => ({
          id: doc.data().startedAt as string,
          titulo: (doc.data().titulo as string) || 'Reunião sem título',
          startedAt: doc.data().startedAt as string,
          endedAt: doc.data().endedAt as string,
          transcriptCount: (doc.data().transcriptCount as number) || 0,
          chatCount: (doc.data().chatCount as number) || 0,
          transcripts: (doc.data().transcripts as MeetingHistoryEntry['transcripts']) || [],
          chats: (doc.data().chats as MeetingHistoryEntry['chats']) || [],
          firestoreId: doc.id,
        }));
        setReunioes(entries);
      } catch (e) {
        console.error('Erro ao carregar reuniões:', e);
      }
    };
    loadReunioes();
  }, []);

  // Cleanup for audio recording on unmount
  useEffect(() => {
    return () => {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
        streamRef.current = null;
      }
    };
  }, []);

  // STT for titulo field only (browser native, short dictation)
  const startTranscription = (targetField: 'titulo') => {
    if (!SpeechRecognition) {
      showAlert("Não suportado", "Seu navegador não suporta reconhecimento de voz.");
      return;
    }
    if (isRecording) {
      recognitionRef.current?.stop();
      setIsRecording(false);
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.lang = 'pt-BR';
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.onstart = () => setIsRecording(true);
    recognition.onend = () => setIsRecording(false);
    recognition.onerror = (event: any) => { console.error("Erro STT:", event.error); setIsRecording(false); };
    recognition.onresult = (event: any) => {
      let transcript = '';
      for (let i = event.resultIndex; i < event.results.length; ++i) transcript += event.results[i][0].transcript;
      setFormData(prev => ({ ...prev, titulo: transcript }));
    };
    recognition.start();
    recognitionRef.current = recognition;
  };

  // MediaRecorder-based toggle for audio ingestion mode
  const handleAudioToggle = async () => {
    if (isRecording) {
      mediaRecorderRef.current?.stop();
      setIsRecording(false);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mr = new MediaRecorder(stream);
      mediaRecorderRef.current = mr;
      audioChunksRef.current = [];
      mr.ondataavailable = e => { if (e.data.size > 0) audioChunksRef.current.push(e.data); };
      mr.onstop = async () => {
        if (stream) stream.getTracks().forEach(t => t.stop());
        streamRef.current = null;
        const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        setIsTranscribing(true);
        try {
          const reader = new FileReader();
          reader.readAsDataURL(blob);
          reader.onloadend = async () => {
            try {
              const b64 = (reader.result as string).split(',')[1];
              const fn = httpsCallable(functions, 'transcreverAudio');
              const res = await fn({ audioBase64: b64 });
              const data = res.data as { raw: string; refined: string };
              if (data.refined) setInputText(prev => (prev ? prev + ' ' : '') + data.refined);
            } catch { showAlert('Erro', 'Erro ao transcrever o áudio.'); }
            finally { setIsTranscribing(false); }
          };
        } catch { setIsTranscribing(false); }
      };
      mr.start();
      setIsRecording(true);
    } catch { showAlert('Erro', 'Não foi possível acessar o microfone.'); }
  };

  const handleGenerateWithIA = async () => {
    if (!inputText.trim()) {
      showAlert("Atenção", "Forneça algum conteúdo para processar.");
      return;
    }

    setIsGenerating(true);
    try {
      const generateFunc = httpsCallable(functions, 'generate_task_with_ia');
      const meetingContext = selectedReuniao
        ? `\n\n=== CONTEXTO DE REUNIÃO: ${selectedReuniao.titulo} ===\n` +
        selectedReuniao.transcripts.map(t => `${t.speaker}: ${t.text}`).join('\n')
        : '';

      const tagsDisponiveis = [
        'GERAL',
        'NÃO CLASSIFICADA',
        ...STRATEGIC_AREA_OPTIONS.map(option => option.value),
        ...unidades.filter(u => isOperationalArea(u.nome)).map(u => u.nome.toUpperCase())
      ];

      const unit = formData.area_tematica && formData.area_tematica !== 'GERAL' && formData.area_tematica !== 'NÃO CLASSIFICADA'
        ? unidades.find(u => u.nome.toUpperCase() === formData.area_tematica)
        : null;
      const computedRagContext = unit ? (knowledgeBases.find(b => b.sistema_id === unit.id)?.id || 'Nenhum') : 'Nenhum';

      const response = await generateFunc({
        content: inputText,
        origin: origemIngestao,
        ragContext: computedRagContext,
        extraContext: extraContext + meetingContext,
        availableTags: tagsDisponiveis,
        ...(extraContextFiles.some(f => f.status === 'ready') ? {
          extraContextId: extraContextId,
          knowledgeItemIds: extraContextFiles.filter(f => f.status === 'ready').map(f => f.id)
        } : {})
      });

      const data = response.data as any;
      if (data) {
        setAutoClassified(true);
        setFormData(prev => ({
          ...prev,
          titulo: data.titulo || prev.titulo,
          descricao: data.descricao || prev.descricao,
          area_tematica: (data.categoria as Categoria) || prev.area_tematica,
          status: (data.status as Status) || prev.status,
          data_limite: data.data_limite || prev.data_limite
        }));
        if (data.plano_acao) {
          setPlanoAcao(data.plano_acao.map((item: any) => ({
            id: Math.random().toString(36).substring(2, 9),
            text: item,
            completed: false
          })));
        }
        if (data.tags && Array.isArray(data.tags)) {
          setTags(prev => Array.from(new Set([...prev, ...data.tags])));
        }
        showAlert("Sucesso", "Demanda gerada com sucesso pela IA!");
      }
    } catch (error) {
      console.error("Erro ao gerar com IA:", error);
      showAlert("Erro", "Falha ao processar conteúdo com IA.");
    } finally {
      setIsGenerating(false);
    }
  };

  const addChecklistItem = () => {
    if (!newChecklistItem.trim()) return;
    const newItem: ActionPlanItem = {
      id: Math.random().toString(36).substring(2, 9),
      text: newChecklistItem.trim(),
      completed: false
    };
    setPlanoAcao([...planoAcao, newItem]);
    setNewChecklistItem('');
  };

  const removeChecklistItem = (id: string) => {
    setPlanoAcao(planoAcao.filter(item => item.id !== id));
  };

  const toggleChecklistItem = (id: string) => {
    setPlanoAcao(planoAcao.map(item => item.id === id ? { ...item, completed: !item.completed } : item));
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-2 md:p-4 bg-slate-950/90 animate-in fade-in duration-300">
      <div className={`bg-white w-full h-auto max-h-[95vh] rounded-lg shadow-lg overflow-hidden animate-in zoom-in-95 duration-300 flex flex-col transition-all duration-500 border-2 border-slate-900 ${tipoAcao === 'deep' ? 'md:max-w-4xl' : 'md:max-w-md'}`}>
        {/* Header with Type Selector */}
        <div className="p-4 border-b border-[#e5e7eb] dark:border-white/10 bg-slate-50 flex flex-col gap-4 flex-shrink-0">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-black text-slate-900 tracking-tight font-sans uppercase">Nova Ação</h3>
            <button onClick={onClose} className="p-1.5 hover:bg-slate-200 rounded-lg transition-colors">
              <svg className="w-5 h-5 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          </div>

          <div className="flex bg-slate-200 p-1 rounded-lg border border-[#e5e7eb] dark:border-white/10">
            <button
              onClick={() => setTipoAcao('fast')}
              className={`flex-1 flex items-center justify-center gap-2 py-2 text-[10px] font-bold uppercase tracking-wider rounded-lg transition-all font-sans ${tipoAcao === 'fast' ? 'bg-white text-slate-900 border border-[#e5e7eb] dark:border-white/10 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
            >
              Fast Track
            </button>
            <button
              onClick={() => setTipoAcao('deep')}
              className={`flex-1 flex items-center justify-center gap-2 py-2 text-[10px] font-bold uppercase tracking-wider rounded-lg transition-all font-sans ${tipoAcao === 'deep' ? 'bg-white text-slate-900 border border-[#e5e7eb] dark:border-white/10 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
            >
              Deep Work
            </button>
          </div>
        </div>

        <div className="p-4 space-y-4 overflow-y-auto custom-scrollbar flex-1">
          {/* Seção de Ingestão para Deep Work */}
          {tipoAcao === 'deep' && (
            <div className="space-y-4 animate-in slide-in-from-top-4 duration-300 border-b-2 border-[#e5e7eb] dark:border-white/10 pb-6">
              <div className="flex bg-slate-100 p-1 rounded-lg gap-1 border border-[#e5e7eb] dark:border-white/10">
                {(['manual', 'audio'] as const).map((o) => (
                  <button
                    key={o}
                    onClick={() => setOrigemIngestao(o)}
                    className={`flex-1 py-3 text-[10px] font-bold uppercase tracking-wider rounded-lg transition-all font-sans ${origemIngestao === o ? 'bg-slate-900 text-white border border-slate-900 shadow-sm' : 'text-slate-400 hover:text-slate-600'}`}
                  >
                    {o === 'manual' ? 'Modo Manual' : 'Captura de Áudio'}
                  </button>
                ))}
              </div>

              <div className="flex items-end gap-2">
                <button
                  onClick={() => setIsExtraContextOpen(!isExtraContextOpen)}
                  className={`h-11 flex-1 rounded-lg text-[9px] font-bold uppercase tracking-wider transition-all font-sans border-2 ${isExtraContextOpen ? 'bg-slate-900 text-white border-slate-900' : 'bg-slate-100 text-slate-600 border-[#e5e7eb] dark:border-white/10 hover:bg-slate-200'}`}
                >
                  Contexto IA
                </button>
                <button
                  onClick={() => setIsTranscriptionSelectorOpen(!isTranscriptionSelectorOpen)}
                  className={`h-11 flex-1 rounded-lg text-[9px] font-bold uppercase tracking-wider transition-all font-sans border-2 ${isTranscriptionSelectorOpen ? 'bg-slate-900 text-white border-slate-900' : 'bg-white text-slate-900 border-[#e5e7eb] dark:border-white/10 hover:bg-slate-100'}`}
                >
                  Vincular Atas
                </button>
              </div>

              {isTranscriptionSelectorOpen && (
                <div className="p-6 bg-slate-950 rounded-lg border border-slate-800 space-y-4 animate-in slide-in-from-top-2">
                  <div className="flex items-center justify-between">
                    <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest font-sans">Selecionar Histórico de Transcrição</p>
                    <button onClick={() => setIsTranscriptionSelectorOpen(false)} className="text-slate-500 hover:text-white">
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                    </button>
                  </div>
                  <input
                    type="text"
                    placeholder="Buscar atas ou reuniões..."
                    value={transcriptionSearch}
                    onChange={e => setTranscriptionSearch(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-3 text-xs font-bold text-white focus:ring-1 focus:ring-blue-500 outline-none font-sans"
                  />
                  <div className="max-h-[200px] overflow-y-auto space-y-2 custom-scrollbar pr-2">
                    {knowledgeItems
                      ?.filter(item =>
                        (item.area_tematica === 'REUNIÕES' || item.tipo_arquivo === 'transcription') &&
                        item.titulo.toLowerCase().includes(transcriptionSearch.toLowerCase()) &&
                        !extraContextFiles.some(f => f.id === item.id)
                      )
                      .map(item => (
                        <button
                          key={item.id}
                          onClick={() => {
                            setExtraContextFiles(prev => [...prev, { id: item.id, name: `[Transcrição] ${item.titulo}`, status: 'ready' }]);
                            setIsTranscriptionSelectorOpen(false);
                            setTranscriptionSearch('');
                            if (!isExtraContextOpen) setIsExtraContextOpen(true);
                          }}
                          className="w-full text-left p-4 bg-slate-800 border border-slate-700 rounded-lg hover:border-blue-500 transition-all group"
                        >
                          <p className="text-[10px] font-black text-slate-300 group-hover:text-white transition-colors font-sans uppercase tracking-widest">{item.titulo}</p>
                          <p className="text-[8px] text-slate-500 font-bold uppercase mt-1 font-sans">{formatDate(item.data_criacao)}</p>
                        </button>
                      ))}
                  </div>
                </div>
              )}

              {isExtraContextOpen && (
                <div className="space-y-3 animate-in slide-in-from-top-2">
                  <div
                    className="border-2 border-dashed border-[#e5e7eb] dark:border-white/10 rounded-lg p-6 text-center cursor-pointer hover:border-slate-900 transition-colors bg-slate-50"
                    onClick={() => (document.getElementById('extra-ctx-file-input') as HTMLInputElement)?.click()}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => { e.preventDefault(); Array.from(e.dataTransfer.files).forEach(handleUploadExtraFile); }}
                  >
                    <input
                      id="extra-ctx-file-input"
                      type="file"
                      className="hidden"
                      accept=".pdf,.txt,.md,.csv,text/plain,application/pdf"
                      multiple
                      onChange={(e) => Array.from(e.target.files || []).forEach(handleUploadExtraFile)}
                    />
                    <svg className="w-6 h-6 mx-auto text-slate-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                    </svg>
                    <p className="text-[9px] font-black text-slate-500 uppercase tracking-[0.2em] font-sans">CARREGAR DOCUMENTAÇÃO TÉCNICA (PDF, TXT, MD)</p>
                  </div>

                  {extraContextFiles.length > 0 && (
                    <div className="space-y-1">
                      {extraContextFiles.map(f => (
                        <div key={f.id} className="flex items-center gap-3 bg-slate-50 rounded-lg px-4 py-3 border border-[#e5e7eb] dark:border-white/10">
                          <span className={`w-2 h-2 rounded-lg flex-shrink-0 ${f.status === 'ready' ? 'bg-emerald-500' : f.status === 'uploading' ? 'bg-amber-500 animate-pulse' : 'bg-rose-500'}`} />
                          <span className="text-[10px] font-black text-slate-700 flex-1 truncate font-sans uppercase">{f.name}</span>
                          {f.status !== 'uploading' && (
                            <button
                              onClick={() => setExtraContextFiles(prev => prev.filter(x => x.id !== f.id))}
                              className="text-slate-400 hover:text-rose-600 transition-colors"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
                            </button>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  <textarea
                    value={extraContext}
                    onChange={e => setExtraContext(e.target.value)}
                    className="w-full bg-slate-50 border border-[#e5e7eb] dark:border-white/10 rounded-lg px-4 py-4 text-xs font-bold text-slate-700 min-h-[80px] resize-none font-sans focus:ring-1 focus:ring-slate-900 outline-none"
                    placeholder="Instruções adicionais ou contexto específico para a IA..."
                  />
                </div>
              )}

              {origemIngestao !== 'manual' && (
                <div className="space-y-4 p-6 bg-slate-950 rounded-lg border border-slate-800">
                  <div className="flex flex-col items-center justify-center gap-6 py-4">
                    <button
                      onClick={handleAudioToggle}
                      disabled={isTranscribing}
                      className={`w-20 h-20 rounded-lg flex items-center justify-center transition-all disabled:opacity-60 border-2 ${isRecording ? 'bg-rose-600 border-rose-500 scale-105 shadow-lg animate-pulse' : isTranscribing ? 'bg-slate-800 border-blue-500' : 'bg-slate-800 border-slate-700 text-slate-500 hover:border-white hover:text-white'}`}
                    >
                      {isTranscribing ? (
                        <svg className="w-8 h-8 animate-spin text-blue-500" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
                      ) : isRecording ? (
                        <svg className="w-8 h-8 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h12v12H6z" /></svg>
                      ) : (
                        <svg className="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
                      )}
                    </button>
                    <div className="text-center">
                      <p className="text-[11px] font-black text-white uppercase tracking-[0.3em] font-sans">
                        {isTranscribing ? 'TRANSCREVENDO FLUXO...' : isRecording ? 'CAPTURA ATIVA' : 'INICIAR CAPTURA'}
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={handleGenerateWithIA}
                    disabled={isGenerating || !inputText.trim()}
                    className={`w-full py-5 rounded-lg text-[11px] font-black uppercase tracking-[0.2em] transition-all border-2 ${isGenerating ? 'bg-slate-800 border-slate-700 text-slate-500' : 'bg-white text-slate-900 border-white hover:bg-transparent hover:text-white shadow-xl'} font-sans`}
                  >
                    {isGenerating ? 'ANALISANDO COM STITCH CORE...' : 'GERAR ESTRUTURA COM IA'}
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Área de Revisão - Título (Com Transcrição no Fast) */}
          <div className="space-y-1">
            <label htmlFor="task-title-input" className="text-[9px] font-black text-slate-400 uppercase tracking-widest pl-1">Título da Tarefa</label>
            <div className="relative group">
              <input
                id="task-title-input"
                type="text"
                autoFocus
                value={formData.titulo}
                onChange={e => {
                  const newTitulo = e.target.value;
                  const detectedArea = detectAreaFromTitle(newTitulo);
                  setFormData({ ...formData, titulo: newTitulo, area_tematica: autoClassified ? formData.area_tematica : detectedArea });
                }}
                className="w-full bg-slate-100 border-none rounded-xl px-4 py-3 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-sans pr-12"
                placeholder={tipoAcao === 'fast' ? "O que precisa ser feito agora?" : "Título da demanda profunda..."}
              />
              {tipoAcao === 'fast' && (
                <button
                  onClick={() => startTranscription('titulo')}
                  className={`absolute right-3 top-1/2 -translate-y-1/2 p-1.5 rounded-lg transition-all ${isRecording ? 'bg-rose-100 text-rose-600' : 'text-slate-400 hover:bg-slate-200'}`}
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
                </button>
              )}
            </div>
          </div>

          {/* Demais campos de Revisão (Deep Work) */}
          {(tipoAcao === 'deep' || (tipoAcao === 'fast' && formData.titulo)) && (
            <div className={`space-y-4 ${tipoAcao === 'fast' ? 'opacity-40 hover:opacity-100 transition-opacity' : ''}`}>
              {tipoAcao === 'deep' && (
                <>
                  <div className="space-y-1">
                    <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest pl-1">Descritivo / Contexto</label>
                    <textarea
                      value={formData.descricao}
                      onChange={e => setFormData({ ...formData, descricao: e.target.value })}
                      className="w-full bg-slate-100 border-none rounded-xl px-4 py-3 text-xs font-medium text-slate-700 focus:ring-2 focus:ring-slate-900 transition-all font-sans min-h-[80px] resize-none"
                      placeholder="Detone o contexto desta ação..."
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1">
                      <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest pl-1">Status</label>
                      <select
                        value={formData.status}
                        onChange={e => setFormData({ ...formData, status: e.target.value as Status })}
                        className="w-full bg-slate-100 border-none rounded-xl px-4 py-2 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-sans"
                      >
                        <option value="em andamento">Em Andamento</option>
                        <option value="stand-by">Stand-by</option>
                        <option value="concluído">Concluído</option>
                      </select>
                    </div>
                    <div className="space-y-1">
                      <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest pl-1">Área Temática</label>
                      <select
                        value={formData.area_tematica}
                        onChange={e => {
                          setFormData({ ...formData, area_tematica: e.target.value as Categoria });
                          setAutoClassified(true);
                        }}
                        className="w-full bg-slate-100 border-none rounded-xl px-4 py-2 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-black uppercase text-[9px] tracking-widest"
                      >
                        <option value="GERAL">Geral</option>
                        <option value="NÃO CLASSIFICADA">Não Classificada</option>
                        <optgroup label="Estratégicas">
                          {STRATEGIC_AREA_OPTIONS.map(option => (
                            <option key={option.value} value={option.value}>{option.label}</option>
                          ))}
                        </optgroup>
                        <optgroup label="Operacionais">
                          {unidades.filter(u => isOperationalArea(u.nome)).map(u => (
                            <option key={u.id} value={u.nome.toUpperCase()}>{u.nome}</option>
                          ))}
                        </optgroup>
                      </select>
                    </div>
                  </div>

                  {/* Tags Dinâmicas */}
                  <div className="space-y-2">
                    <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest pl-1">Tags Dinâmicas</label>
                    <div className="flex flex-wrap gap-2 mb-2">
                      {tags.map(tag => (
                        <span key={tag} className="flex items-center gap-1 bg-indigo-50 text-indigo-600 px-2.5 py-1 rounded-lg text-[10px] font-bold border border-indigo-100">
                          #{tag}
                          <button onClick={(e) => { e.preventDefault(); setTags(tags.filter(t => t !== tag)); }} className="text-indigo-400 hover:text-rose-500 scale-125 ml-1 transition-colors">&times;</button>
                        </span>
                      ))}
                    </div>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={tagInput}
                        onChange={e => setTagInput(e.target.value)}
                        onKeyDown={e => {
                          if (e.key === 'Enter') {
                            e.preventDefault();
                            if (tagInput.trim() && !tags.includes(tagInput.trim())) {
                              setTags([...tags, tagInput.trim()]);
                              setTagInput('');
                            }
                          }
                        }}
                        className="flex-1 bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-[11px] font-medium text-slate-700 focus:ring-1 focus:ring-indigo-500 outline-none"
                        placeholder="Adicionar nova tag (Enter)..."
                      />
                      <button
                        onClick={(e) => {
                          e.preventDefault();
                          if (tagInput.trim() && !tags.includes(tagInput.trim())) {
                            setTags([...tags, tagInput.trim()]);
                            setTagInput('');
                          }
                        }}
                        className="bg-slate-100 text-slate-600 px-3 py-1.5 rounded-lg hover:bg-slate-200 transition-all text-[10px] font-bold border border-slate-200"
                      >
                        Add
                      </button>
                    </div>
                  </div>

                  {/* Plano de Ação */}
                  <div className="space-y-2">
                    <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest pl-1">Plano de Ação (Checklist)</label>
                    <div className="space-y-2">
                      {planoAcao.map((item) => (
                        <div key={item.id} className="flex items-center gap-2 bg-slate-50 p-2 rounded-lg border border-slate-100 group animate-in slide-in-from-left-2 transition-all">
                          <button
                            onClick={() => toggleChecklistItem(item.id)}
                            className={`w-4 h-4 rounded border transition-all flex items-center justify-center ${item.completed ? 'bg-emerald-500 border-emerald-500 text-white' : 'bg-white border-slate-300'}`}
                          >
                            {item.completed && <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="4" d="M5 13l4 4L19 7" /></svg>}
                          </button>
                          <span className={`text-[11px] font-bold flex-1 ${item.completed ? 'text-slate-400 line-through' : 'text-slate-700'}`}>{item.text}</span>
                          <button onClick={() => removeChecklistItem(item.id)} className="opacity-0 group-hover:opacity-100 p-1 text-slate-300 hover:text-rose-500 transition-all">
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                          </button>
                        </div>
                      ))}
                      <div className="flex gap-2">
                        <input
                          type="text"
                          value={newChecklistItem}
                          onChange={e => setNewChecklistItem(e.target.value)}
                          onKeyDown={e => e.key === 'Enter' && addChecklistItem()}
                          className="flex-1 bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-[11px] font-medium text-slate-700 focus:ring-1 focus:ring-purple-500 outline-none"
                          placeholder="Novo passo no plano..."
                        />
                        <button onClick={addChecklistItem} className="bg-purple-100 text-purple-600 p-1.5 rounded-lg hover:bg-purple-200 transition-all">
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" /></svg>
                        </button>
                      </div>
                    </div>
                  </div>
                </>
              )}

              {/* Prazo (Comum) */}
              <div className="space-y-1 border-t border-slate-100 pt-3">
                <div className="flex items-center justify-between gap-3 pl-1">
                  <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Prazo Final</label>
                  {formData.status === 'stand-by' && (
                    <button type="button" onClick={() => setFormData({ ...formData, data_limite: '' })} className="text-[9px] font-bold uppercase tracking-wider text-slate-500 hover:text-slate-900">Sem prazo</button>
                  )}
                </div>
                <input
                  type="date"
                  min={formatDateLocalISO(new Date())}
                  value={formData.data_limite}
                  onChange={e => setFormData({ ...formData, data_limite: e.target.value })}
                  className="w-full bg-slate-100 border-none rounded-xl px-4 py-2.5 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-sans"
                />
              </div>

              {/* Recorrência Mensal */}
              <div className="space-y-2 border-t border-slate-100 pt-3">
                <label className="flex items-center gap-2 pl-1 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={recorrenciaMensal}
                    onChange={e => setRecorrenciaMensal(e.target.checked)}
                    className="w-4 h-4 rounded border-slate-300 text-slate-900 focus:ring-slate-900"
                  />
                  <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Repetir mensalmente</span>
                </label>
                {recorrenciaMensal && (
                  <div className="flex items-center gap-2 pl-1">
                    <span className="text-[11px] font-bold text-slate-500">Todo dia</span>
                    <input
                      type="number"
                      min={1}
                      max={31}
                      value={diaDoMesRecorrencia}
                      onChange={e => setDiaDoMesRecorrencia(Math.min(31, Math.max(1, Number(e.target.value) || 1)))}
                      className="w-16 bg-slate-100 border-none rounded-xl px-3 py-1.5 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-sans"
                    />
                    <span className="text-[11px] font-bold text-slate-500">do mês, uma nova ação será criada automaticamente.</span>
                  </div>
                )}
              </div>

              {/* Gatilho de E-mail */}
              <div className="space-y-2 border-t border-slate-100 pt-3">
                <label className="flex items-center gap-2 pl-1 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={emailTriggerEnabled}
                    onChange={e => setEmailTriggerEnabled(e.target.checked)}
                    className="w-4 h-4 rounded border-slate-300 text-slate-900 focus:ring-slate-900"
                  />
                  <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Gatilho de E-mail (Stand-by)</span>
                </label>
                {emailTriggerEnabled && (
                  <div className="space-y-3 pl-1 pt-1 border-l-2 border-slate-200 ml-1.5 pl-3 transition-all animate-in slide-in-from-top-2 duration-200">
                    <div className="space-y-1">
                      <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Remetente do E-mail</label>
                      <input
                        type="text"
                        value={emailSender}
                        onChange={e => setEmailSender(e.target.value)}
                        placeholder="Ex: professor@ifes.edu.br (opcional)"
                        className="w-full bg-slate-100 border-none rounded-xl px-4 py-2 text-xs font-medium text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-sans"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Palavras no Assunto</label>
                      <input
                        type="text"
                        value={emailSubjectKeywords}
                        onChange={e => setEmailSubjectKeywords(e.target.value)}
                        placeholder="Ex: fatura, relatório (separe por vírgula)"
                        className="w-full bg-slate-100 border-none rounded-xl px-4 py-2 text-xs font-medium text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-sans"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Palavras no Corpo</label>
                      <input
                        type="text"
                        value={emailBodyKeywords}
                        onChange={e => setEmailBodyKeywords(e.target.value)}
                        placeholder="Ex: aprovado, concluído (separe por vírgula)"
                        className="w-full bg-slate-100 border-none rounded-xl px-4 py-2 text-xs font-medium text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-sans"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Ação ao Receber</label>
                      <select
                        value={emailActionToTake}
                        onChange={e => setEmailActionToTake(e.target.value as any)}
                        className="w-full bg-slate-100 border-none rounded-xl px-4 py-2 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all"
                      >
                        <option value="status_to_andamento">Mover para 'Em Andamento'</option>
                        <option value="run_ai_analysis">Análise de IA + Atualizar notas/checklist</option>
                      </select>
                    </div>
                    {emailActionToTake === 'run_ai_analysis' && (
                      <div className="space-y-1 animate-in slide-in-from-top-2 duration-200">
                        <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Instruções para a IA</label>
                        <textarea
                          value={emailAiInstructions}
                          onChange={e => setEmailAiInstructions(e.target.value)}
                          placeholder="Ex: Extraia o valor aprovado do orçamento e anote nas notas. Marque o primeiro passo do checklist se a resposta for afirmativa."
                          className="w-full bg-slate-100 border-none rounded-xl px-4 py-3 text-xs font-medium text-slate-700 focus:ring-2 focus:ring-slate-900 transition-all font-sans min-h-[60px] resize-none"
                        />
                      </div>
                    )}
                    <label className="flex items-center gap-2 cursor-pointer select-none">
                      <input
                        type="checkbox"
                        checked={emailTelegramAlert}
                        onChange={e => setEmailTelegramAlert(e.target.checked)}
                        className="w-4 h-4 rounded border-slate-300 text-slate-900 focus:ring-slate-900"
                      />
                      <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Notificar no Telegram</span>
                    </label>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="p-6 bg-slate-50 border-t border-[#e5e7eb] dark:border-white/10 flex gap-4 flex-shrink-0">
          <button onClick={onClose} className="flex-1 px-8 py-4 rounded-lg text-[10px] font-black uppercase tracking-[0.2em] text-slate-500 hover:bg-slate-200 transition-all border border-[#e5e7eb] dark:border-white/10 font-sans">Cancelar</button>
          <button
            onClick={() => {
              if (!formData.titulo || (!formData.data_limite && formData.status !== 'stand-by')) {
                showAlert("Atenção", "Preencha o título e o prazo final.");
                return;
              }
              if (formData.data_limite && formData.data_limite < formatDateLocalISO(new Date())) {
                showAlert("Atenção", "A data de execução não pode ser no passado.");
                return;
              }

              onSave({
                ...formData,
                tags,
                tipo_acao: tipoAcao,
                plano_acao: planoAcao,
                data_inicio: formData.data_limite || '',
                origem: tipoAcao === 'deep' ? origemIngestao : 'manual',
                base_conhecimento: (() => {
                  const unit = formData.area_tematica && formData.area_tematica !== 'GERAL' && formData.area_tematica !== 'NÃO CLASSIFICADA'
                    ? unidades.find(u => u.nome.toUpperCase() === formData.area_tematica)
                    : null;
                  return unit ? (knowledgeBases.find(b => b.sistema_id === unit.id)?.id || undefined) : undefined;
                })(),
                ...(extraContextFiles.some(f => f.status === 'ready') ? {
                  extra_context_id: extraContextId,
                  knowledge_item_ids: extraContextFiles.filter(f => f.status === 'ready').map(f => f.id)
                } : {}),
                ...(selectedReuniao?.firestoreId ? { reuniao_vinculada_id: selectedReuniao.firestoreId } : {}),
                ...(initialData?.estrategia_indicador_id ? { estrategia_indicador_id: initialData.estrategia_indicador_id } : {}),
                ...(initialData?.estrategia_objetivo_id ? { estrategia_objetivo_id: initialData.estrategia_objetivo_id } : {}),
                ...(recorrenciaMensal ? { recorrencia: { ativo: true, dia_do_mes: diaDoMesRecorrencia } } : {}),
                email_trigger: {
                  enabled: emailTriggerEnabled,
                  sender: emailSender.trim() || undefined,
                  subjectKeywords: emailSubjectKeywords.trim() || undefined,
                  bodyKeywords: emailBodyKeywords.trim() || undefined,
                  action_to_take: emailActionToTake,
                  ai_instructions: emailAiInstructions.trim() || undefined,
                  telegram_alert: emailTelegramAlert
                }
              });
              onClose();
            }}
            className={`flex-1 ${tipoAcao === 'fast' ? 'bg-slate-950 hover:bg-blue-600' : 'bg-slate-950 hover:bg-purple-600'} text-white px-8 py-4 rounded-lg text-[10px] font-black uppercase tracking-[0.2em] shadow-lg transition-all font-sans`}
          >
            {tipoAcao === 'fast' ? 'Criar Fast Action' : 'Iniciar Deep Work'}
          </button>
        </div>
      </div>
    </div>
  );
};
export const TaskEditModal = ({ unidades, task, onSave, onDelete, onClose, showAlert, showConfirm, pgcEntregas = [], existingTags = [] }: { unidades: { id: string, nome: string }[], task: Tarefa, onSave: (id: string, updates: Partial<Tarefa>) => void, onDelete: (id: string) => void, onClose: () => void, showAlert: (title: string, message: string) => void, showConfirm: (title: string, message: string, onConfirm: () => void) => void, pgcEntregas?: EntregaInstitucional[], existingTags?: string[] }) => {
  const [tipoAcao, setTipoAcao] = useState<TipoAcao>(task.tipo_acao || 'fast');
  const [formData, setFormData] = useState({
    titulo: task.titulo,
    data_limite: task.data_limite === '-' ? (task.data_inicio || '') : (task.data_limite || task.data_inicio || ''),
    data_criacao: task.data_criacao,
    status: task.status,
    area_tematica: task.area_tematica || 'NÃO CLASSIFICADA',
    notas: task.notas || '',
    descricao: task.descricao || '',
    entregas_relacionadas: task.entregas_relacionadas || [],
    horario_inicio: task.horario_inicio || '',
    horario_fim: task.horario_fim || ''
  });

  const [planoAcao, setPlanoAcao] = useState<ActionPlanItem[]>(task.plano_acao || []);
  const [newChecklistItem, setNewChecklistItem] = useState('');
  const [tags, setTags] = useState<string[]>(task.tags || []);
  const [tagInput, setTagInput] = useState('');
  const [recorrenciaMensal, setRecorrenciaMensal] = useState(task.recorrencia?.ativo || false);
  const [diaDoMesRecorrencia, setDiaDoMesRecorrencia] = useState<number>(task.recorrencia?.dia_do_mes || new Date().getDate());
  const [emailTriggerEnabled, setEmailTriggerEnabled] = useState(task.email_trigger?.enabled || false);
  const [emailSender, setEmailSender] = useState(task.email_trigger?.sender || '');
  const [emailSubjectKeywords, setEmailSubjectKeywords] = useState(task.email_trigger?.subjectKeywords || '');
  const [emailBodyKeywords, setEmailBodyKeywords] = useState(task.email_trigger?.bodyKeywords || '');
  const [emailActionToTake, setEmailActionToTake] = useState<'status_to_andamento' | 'run_ai_analysis'>(task.email_trigger?.action_to_take || 'status_to_andamento');
  const [emailAiInstructions, setEmailAiInstructions] = useState(task.email_trigger?.ai_instructions || '');
  const [emailTelegramAlert, setEmailTelegramAlert] = useState(task.email_trigger?.telegram_alert ?? true);

  const addChecklistItem = () => {
    if (!newChecklistItem.trim()) return;
    const newItem: ActionPlanItem = {
      id: Math.random().toString(36).substring(2, 9),
      text: newChecklistItem.trim(),
      completed: false
    };
    setPlanoAcao([...planoAcao, newItem]);
    setNewChecklistItem('');
  };

  const removeChecklistItem = (id: string) => {
    setPlanoAcao(planoAcao.filter(item => item.id !== id));
  };

  const toggleChecklistItem = (id: string) => {
    setPlanoAcao(planoAcao.map(item => item.id === id ? { ...item, completed: !item.completed } : item));
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-2 md:p-4 bg-slate-950/90 animate-in fade-in duration-300">
      <div className="bg-white w-full h-auto max-h-[95vh] md:max-w-md flex flex-col rounded-lg shadow-lg overflow-hidden animate-in zoom-in-95 duration-300 border-2 border-slate-900">
        <div className="p-4 border-b border-[#e5e7eb] dark:border-white/10 bg-slate-50 flex flex-col gap-4 flex-shrink-0">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-black text-slate-900 tracking-tight font-sans uppercase">Editar Ação</h3>
            <button onClick={onClose} className="p-1.5 hover:bg-slate-200 rounded-lg transition-colors border border-transparent hover:border-[#e5e7eb] dark:border-white/10">
              <svg className="w-5 h-5 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          </div>

          <div className="flex bg-slate-200 p-1 rounded-lg border border-[#e5e7eb] dark:border-white/10">
            <button
              onClick={() => setTipoAcao('fast')}
              className={`flex-1 flex items-center justify-center gap-2 py-3 text-[10px] font-bold uppercase tracking-wider rounded-lg transition-all font-sans ${tipoAcao === 'fast' ? 'bg-slate-900 text-white shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
            >
              Fast Track
            </button>
            <button
              onClick={() => setTipoAcao('deep')}
              className={`flex-1 flex items-center justify-center gap-2 py-3 text-[10px] font-bold uppercase tracking-wider rounded-lg transition-all font-sans ${tipoAcao === 'deep' ? 'bg-slate-900 text-white shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
            >
              Deep Work
            </button>
          </div>
        </div>

        <div className="p-4 space-y-4 overflow-y-auto custom-scrollbar flex-1">
          <div className="space-y-1">
            <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest pl-1">Título da Tarefa</label>
            <input
              type="text"
              value={formData.titulo}
              onChange={e => setFormData({ ...formData, titulo: e.target.value })}
              className="w-full bg-slate-100 border-none rounded-xl px-4 py-2.5 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-sans"
              placeholder="Título da demanda..."
            />
          </div>

          {tipoAcao === 'deep' && (
            <div className="space-y-4 animate-in slide-in-from-top-4 duration-300">
              <div className="space-y-1">
                <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest pl-1">Descritivo / Contexto</label>
                <textarea
                  value={formData.descricao}
                  onChange={e => setFormData({ ...formData, descricao: e.target.value })}
                  className="w-full bg-slate-100 border-none rounded-xl px-4 py-3 text-xs font-medium text-slate-700 focus:ring-2 focus:ring-slate-900 transition-all font-sans min-h-[80px] resize-none"
                  placeholder="Detone o contexto desta ação..."
                />
              </div>

              {/* Tags Dinâmicas */}
              <div className="space-y-2">
                <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest pl-1">Tags Dinâmicas</label>
                <div className="flex flex-wrap gap-2 mb-2">
                  {tags.map(tag => (
                    <span key={tag} className="flex items-center gap-1 bg-indigo-50 text-indigo-600 px-2.5 py-1 rounded-lg text-[10px] font-bold border border-indigo-100">
                      #{tag}
                      <button onClick={(e) => { e.preventDefault(); setTags(tags.filter(t => t !== tag)); }} className="text-indigo-400 hover:text-rose-500 scale-125 ml-1 transition-colors">&times;</button>
                    </span>
                  ))}
                </div>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={tagInput}
                    onChange={e => setTagInput(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        if (tagInput.trim() && !tags.includes(tagInput.trim())) {
                          setTags([...tags, tagInput.trim()]);
                          setTagInput('');
                        }
                      }
                    }}
                    className="flex-1 bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-[11px] font-medium text-slate-700 focus:ring-1 focus:ring-indigo-500 outline-none"
                    placeholder="Adicionar nova tag (Enter)..."
                  />
                  <button
                    onClick={(e) => {
                      e.preventDefault();
                      if (tagInput.trim() && !tags.includes(tagInput.trim())) {
                        setTags([...tags, tagInput.trim()]);
                        setTagInput('');
                      }
                    }}
                    className="bg-slate-100 text-slate-600 px-3 py-1.5 rounded-lg hover:bg-slate-200 transition-all text-[10px] font-bold border border-slate-200"
                  >
                    Add
                  </button>
                </div>
              </div>

              {/* Plano de Ação (Checklist) */}
              <div className="space-y-2">
                <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest pl-1">Plano de Ação (Checklist)</label>
                <div className="space-y-2">
                  {planoAcao.map((item) => (
                    <div key={item.id} className="flex items-center gap-2 bg-slate-50 p-2 rounded-lg border border-slate-100 group">
                      <button
                        onClick={() => toggleChecklistItem(item.id)}
                        className={`w-4 h-4 rounded border transition-all flex items-center justify-center ${item.completed ? 'bg-emerald-500 border-emerald-500 text-white' : 'bg-white border-slate-300'}`}
                      >
                        {item.completed && <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="4" d="M5 13l4 4L19 7" /></svg>}
                      </button>
                      <span className={`text-[11px] font-bold flex-1 ${item.completed ? 'text-slate-400 line-through' : 'text-slate-700'}`}>{item.text}</span>
                      <button
                        onClick={() => removeChecklistItem(item.id)}
                        className="opacity-0 group-hover:opacity-100 p-1 text-slate-300 hover:text-rose-500 transition-all"
                      >
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                      </button>
                    </div>
                  ))}
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={newChecklistItem}
                      onChange={e => setNewChecklistItem(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && addChecklistItem()}
                      className="flex-1 bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-[11px] font-medium text-slate-700 focus:ring-1 focus:ring-purple-500 outline-none"
                      placeholder="Novo passo no plano..."
                    />
                    <button
                      onClick={addChecklistItem}
                      className="bg-purple-100 text-purple-600 p-1.5 rounded-lg hover:bg-purple-200 transition-all"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" /></svg>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          <div className="space-y-1">
            <div className="flex items-center justify-between gap-3 pl-1">
              <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Prazo</label>
              {formData.status === 'stand-by' && (
                <button type="button" onClick={() => setFormData({ ...formData, data_limite: '' })} className="text-[9px] font-bold uppercase tracking-wider text-slate-500 hover:text-slate-900">Sem prazo</button>
              )}
            </div>
            <input
              type="date"
              min={formatDateLocalISO(new Date())}
              value={formData.data_limite}
              onChange={e => setFormData({ ...formData, data_limite: e.target.value })}
              className="w-full bg-slate-100 border-none rounded-xl px-4 py-2 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-sans"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest pl-1">Status</label>
              <select
                value={formData.status}
                onChange={e => setFormData({ ...formData, status: e.target.value as Status })}
                className="w-full bg-slate-100 border-none rounded-xl px-4 py-2 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all"
              >
                <option value="em andamento">Em Andamento</option>
                <option value="stand-by">Stand-by</option>
                <option value="concluído">Concluído</option>
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest pl-1">Área Temática</label>
              <select
                value={formData.area_tematica}
                onChange={e => setFormData({ ...formData, area_tematica: e.target.value as Categoria })}
                className="w-full bg-slate-100 border-none rounded-xl px-4 py-2 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-black uppercase text-[9px] tracking-widest"
              >
                <option value="GERAL">Geral</option>
                <option value="NÃO CLASSIFICADA">Não Classificada</option>
                <optgroup label="Estratégicas">
                  {STRATEGIC_AREA_OPTIONS.map(option => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </optgroup>
                <optgroup label="Operacionais">
                  {unidades.filter(u => isOperationalArea(u.nome)).map(u => (
                    <option key={u.id} value={u.nome.toUpperCase()}>{u.nome}</option>
                  ))}
                </optgroup>
              </select>
            </div>
          </div>

          {/* Recorrência Mensal */}
          <div className="space-y-2 border-t border-slate-100 pt-3">
            <label className="flex items-center gap-2 pl-1 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={recorrenciaMensal}
                onChange={e => setRecorrenciaMensal(e.target.checked)}
                className="w-4 h-4 rounded border-slate-300 text-slate-900 focus:ring-slate-900"
              />
              <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Repetir mensalmente</span>
            </label>
            {recorrenciaMensal && (
              <div className="flex items-center gap-2 pl-1">
                <span className="text-[11px] font-bold text-slate-500">Todo dia</span>
                <input
                  type="number"
                  min={1}
                  max={31}
                  value={diaDoMesRecorrencia}
                  onChange={e => setDiaDoMesRecorrencia(Math.min(31, Math.max(1, Number(e.target.value) || 1)))}
                  className="w-16 bg-slate-100 border-none rounded-xl px-3 py-1.5 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-sans"
                />
                <span className="text-[11px] font-bold text-slate-500">do mês, uma nova ação será criada automaticamente.</span>
              </div>
            )}
          </div>

          {/* Gatilho de E-mail */}
          <div className="space-y-2 border-t border-slate-100 pt-3">
            <label className="flex items-center gap-2 pl-1 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={emailTriggerEnabled}
                onChange={e => setEmailTriggerEnabled(e.target.checked)}
                className="w-4 h-4 rounded border-slate-300 text-slate-900 focus:ring-slate-900"
              />
              <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Gatilho de E-mail (Stand-by)</span>
            </label>
            {emailTriggerEnabled && (
              <div className="space-y-3 pl-1 pt-1 border-l-2 border-slate-200 ml-1.5 pl-3 transition-all animate-in slide-in-from-top-2 duration-200">
                <div className="space-y-1">
                  <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Remetente do E-mail</label>
                  <input
                    type="text"
                    value={emailSender}
                    onChange={e => setEmailSender(e.target.value)}
                    placeholder="Ex: professor@ifes.edu.br (opcional)"
                    className="w-full bg-slate-100 border-none rounded-xl px-4 py-2 text-xs font-medium text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-sans"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Palavras no Assunto</label>
                  <input
                    type="text"
                    value={emailSubjectKeywords}
                    onChange={e => setEmailSubjectKeywords(e.target.value)}
                    placeholder="Ex: fatura, relatório (separe por vírgula)"
                    className="w-full bg-slate-100 border-none rounded-xl px-4 py-2 text-xs font-medium text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-sans"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Palavras no Corpo</label>
                  <input
                    type="text"
                    value={emailBodyKeywords}
                    onChange={e => setEmailBodyKeywords(e.target.value)}
                    placeholder="Ex: aprovado, concluído (separe por vírgula)"
                    className="w-full bg-slate-100 border-none rounded-xl px-4 py-2 text-xs font-medium text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-sans"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Ação ao Receber</label>
                  <select
                    value={emailActionToTake}
                    onChange={e => setEmailActionToTake(e.target.value as any)}
                    className="w-full bg-slate-100 border-none rounded-xl px-4 py-2 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all"
                  >
                    <option value="status_to_andamento">Mover para 'Em Andamento'</option>
                    <option value="run_ai_analysis">Análise de IA + Atualizar notas/checklist</option>
                  </select>
                </div>
                {emailActionToTake === 'run_ai_analysis' && (
                  <div className="space-y-1 animate-in slide-in-from-top-2 duration-200">
                    <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Instruções para a IA</label>
                    <textarea
                      value={emailAiInstructions}
                      onChange={e => setEmailAiInstructions(e.target.value)}
                      placeholder="Ex: Extraia o valor aprovado do orçamento e anote nas notas. Marque o primeiro passo do checklist se a resposta for afirmativa."
                      className="w-full bg-slate-100 border-none rounded-xl px-4 py-3 text-xs font-medium text-slate-700 focus:ring-2 focus:ring-slate-900 transition-all font-sans min-h-[60px] resize-none"
                    />
                  </div>
                )}
                <label className="flex items-center gap-2 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={emailTelegramAlert}
                    onChange={e => setEmailTelegramAlert(e.target.checked)}
                    className="w-4 h-4 rounded border-slate-300 text-slate-900 focus:ring-slate-900"
                  />
                  <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Notificar no Telegram</span>
                </label>
              </div>
            )}
          </div>
        </div>

        <div className="p-6 bg-slate-50 border-t border-[#e5e7eb] dark:border-white/10 flex flex-col md:flex-row gap-3 flex-shrink-0">
          <button
            onClick={() => {
              if (!formData.titulo || (!formData.data_limite && formData.status !== 'stand-by')) {
                showAlert("Atenção", "Preencha o título e o prazo final.");
                return;
              }
              if (formData.data_limite && formData.data_limite < formatDateLocalISO(new Date())) {
                showAlert("Atenção", "A data de execução não pode ser no passado.");
                return;
              }
              onSave(task.id, {
                ...formData,
                tags,
                tipo_acao: tipoAcao,
                plano_acao: planoAcao,
                data_inicio: formData.data_limite || '',
                ...(recorrenciaMensal
                  ? { recorrencia: { ativo: true, dia_do_mes: diaDoMesRecorrencia, ...(task.recorrencia?.ultima_geracao ? { ultima_geracao: task.recorrencia.ultima_geracao } : {}) } }
                  : (task.recorrencia ? { recorrencia: { ...task.recorrencia, ativo: false } } : {})),
                email_trigger: {
                  enabled: emailTriggerEnabled,
                  sender: emailSender.trim() || undefined,
                  subjectKeywords: emailSubjectKeywords.trim() || undefined,
                  bodyKeywords: emailBodyKeywords.trim() || undefined,
                  action_to_take: emailActionToTake,
                  ai_instructions: emailAiInstructions.trim() || undefined,
                  telegram_alert: emailTelegramAlert,
                  last_triggered_email_id: task.email_trigger?.last_triggered_email_id || undefined
                }
              });
              onClose();
            }}
            className={`w-full md:flex-1 ${tipoAcao === 'fast' ? 'bg-slate-950 hover:bg-blue-600' : 'bg-slate-950 hover:bg-purple-600'} text-white px-8 py-4 rounded-lg text-[10px] font-black uppercase tracking-[0.2em] shadow-lg transition-all order-1 md:order-2 font-sans`}
          >
            Salvar Alterações
          </button>

          <div className="flex gap-3 order-2">
            <button
              onClick={() => {
                showConfirm("Confirmar Exclusão", "Deseja realmente excluir esta tarefa?", () => {
                  onDelete(task.id);
                  onClose();
                });
              }}
              className="flex-1 md:flex-none px-6 py-4 rounded-lg text-[10px] font-bold uppercase tracking-wider transition-all border flex items-center justify-center gap-2 text-rose-600 hover:bg-rose-50 border-rose-100 font-sans"
            >
              Excluir
            </button>
            <button
              onClick={onClose}
              className="flex-1 md:px-8 py-4 rounded-lg text-[10px] font-bold uppercase tracking-wider text-slate-500 hover:bg-slate-200 transition-all border border-[#e5e7eb] dark:border-white/10 font-sans"
            >
              Cancelar
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};






