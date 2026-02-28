import React, { useState } from 'react';
import {
  Tarefa, Status, Categoria, EntregaInstitucional, DailyHabits,
  AppSettings, HermesModalProps, CustomNotification
} from '@/types';
import { formatDate, formatDateLocalISO } from '@/types';
import { detectAreaFromTitle, callScrapeSipac } from '../../utils/helpers';
import { WysiwygEditor } from '../ui/UIComponents';
export const HermesModal = ({ isOpen, title, message, type, onConfirm, onCancel, confirmLabel, cancelLabel }: HermesModalProps) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[500] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-300">
      <div className="bg-white w-full max-w-sm rounded-[2rem] shadow-2xl overflow-hidden animate-in zoom-in-95 duration-300">
        <div className="p-8 space-y-6">
          <div className="space-y-2">
            <h3 className="text-xl font-black text-slate-900 tracking-tight">{title}</h3>
            <p className="text-sm font-medium text-slate-500 leading-relaxed">{message}</p>
          </div>
          <div className="flex gap-3">
            {type === 'confirm' && (
              <button
                onClick={onCancel}
                className="flex-1 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest text-slate-400 hover:bg-slate-50 transition-colors"
              >
                {cancelLabel || 'Cancelar'}
              </button>
            )}
            <button
              onClick={onConfirm}
              className="flex-1 bg-slate-900 text-white py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg shadow-slate-200 hover:bg-slate-800 transition-all active:scale-95"
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
  initialTab
}: {
  settings: AppSettings,
  unidades: { id: string, nome: string, palavras_chave?: string[] }[],
  onSave: (settings: AppSettings) => void,
  onClose: () => void,
  onAddUnidade: (nome: string) => void,
  onDeleteUnidade: (id: string) => void,
  onUpdateUnidade: (id: string, updates: any) => void,
  onEmitNotification: (title: string, message: string, type: 'info' | 'warning' | 'success' | 'error') => void,
  initialTab?: 'notifications' | 'context' | 'sistemas' | 'google' | 'pomodoro',
  showConfirm: (title: string, message: string, onConfirm: () => void, onCancel?: () => void) => void
}) => {
  const [localSettings, setLocalSettings] = useState<AppSettings>(settings);
  const [activeTab, setActiveTab] = useState<'notifications' | 'context' | 'sistemas' | 'google' | 'pomodoro'>(initialTab || 'notifications');
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
    <div className="fixed inset-0 z-[150] flex items-center justify-center p-0 md:p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-300">
      <div className="bg-white w-full h-full md:h-auto md:max-w-2xl rounded-none md:rounded-[2.5rem] shadow-2xl overflow-hidden animate-in zoom-in-95 duration-300 flex flex-col max-h-[90vh]">
        <div className="p-8 border-b border-slate-100 bg-slate-50/50 flex flex-col gap-6 flex-shrink-0">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-2xl font-black text-slate-900 tracking-tight">ConfiguraÃ§Ãµes</h3>
              <p className="text-slate-400 text-[10px] font-black uppercase tracking-widest">Painel de PreferÃªncias</p>
            </div>
            <button onClick={onClose} className="p-2 hover:bg-slate-200 rounded-full transition-colors">
              <svg className="w-6 h-6 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          </div>

          <div className="flex bg-slate-200/50 p-1 rounded-none md:rounded-2xl gap-1">
            <button
              onClick={() => setActiveTab('notifications')}
              className={`flex-1 py-4 rounded-lg md:rounded-xl flex items-center justify-center transition-all ${activeTab === 'notifications' ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-400 hover:text-slate-600 hover:bg-white/50'}`}
              title="NotificaÃ§Ãµes"
            >
              <svg className="w-6 h-6 md:w-8 md:h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" /></svg>
            </button>
            <button
              onClick={() => setActiveTab('context')}
              className={`flex-1 py-4 rounded-lg md:rounded-xl flex items-center justify-center transition-all ${activeTab === 'context' ? 'bg-white text-emerald-600 shadow-sm' : 'text-slate-400 hover:text-slate-600 hover:bg-white/50'}`}
              title="Contexto & Ãreas"
            >
              <svg className="w-6 h-6 md:w-8 md:h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" /></svg>
            </button>
            <button
              onClick={() => setActiveTab('sistemas')}
              className={`flex-1 py-4 rounded-lg md:rounded-xl flex items-center justify-center transition-all ${activeTab === 'sistemas' ? 'bg-white text-violet-600 shadow-sm' : 'text-slate-400 hover:text-slate-600 hover:bg-white/50'}`}
              title="Sistemas"
            >
              <svg className="w-6 h-6 md:w-8 md:h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" /></svg>
            </button>
            <button
              onClick={() => setActiveTab('google')}
              className={`flex-1 py-4 rounded-lg md:rounded-xl flex items-center justify-center transition-all ${activeTab === 'google' ? 'bg-white text-sky-600 shadow-sm' : 'text-slate-400 hover:text-slate-600 hover:bg-white/50'}`}
              title="Google"
            >
              <svg className="w-6 h-6 md:w-8 md:h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z" /></svg>
            </button>
            <button
              onClick={() => setActiveTab('pomodoro')}
              className={`flex-1 py-4 rounded-lg md:rounded-xl flex items-center justify-center transition-all ${activeTab === 'pomodoro' ? 'bg-white text-rose-600 shadow-sm' : 'text-slate-400 hover:text-slate-600 hover:bg-white/50'}`}
              title="Pomodoro"
            >
              <svg className="w-6 h-6 md:w-8 md:h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
            </button>
          </div>
        </div>

        <div className="p-8 space-y-10 overflow-y-auto custom-scrollbar flex-1">
          {activeTab === 'notifications' ? (
            <>
              {/* Geral / SaÃºde Section */}
              <div className="space-y-4 animate-in slide-in-from-bottom-4 duration-500">
                <h4 className="text-[10px] font-black text-slate-900 uppercase tracking-[0.2em] border-b border-slate-100 pb-2 flex items-center gap-2">
                  <span className="w-2 h-2 bg-blue-500 rounded-full"></span>
                  Geral / SaÃºde
                </h4>

                <div className="flex items-center justify-between p-6 bg-slate-50 rounded-none md:rounded-2xl border border-slate-100 group hover:border-blue-200 transition-all">
                  <div className="flex-1">
                    <p className="text-sm font-bold text-slate-900 mb-1">HÃ¡bitos de Hoje</p>
                    <p className="text-[11px] text-slate-500 font-medium">Abrir lembrete para marcar hÃ¡bitos cumpridos</p>
                  </div>
                  <div className="flex items-center gap-4">
                    <input
                      type="time"
                      value={localSettings.notifications.habitsReminder.time}
                      onChange={(e) => setLocalSettings({
                        ...localSettings,
                        notifications: {
                          ...localSettings.notifications,
                          habitsReminder: { ...localSettings.notifications.habitsReminder, time: e.target.value }
                        }
                      })}
                      className="bg-white border-none rounded-lg px-3 py-1.5 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-blue-500"
                    />
                    <button
                      onClick={() => setLocalSettings({
                        ...localSettings,
                        notifications: {
                          ...localSettings.notifications,
                          habitsReminder: { ...localSettings.notifications.habitsReminder, enabled: !localSettings.notifications.habitsReminder.enabled }
                        }
                      })}
                      className={`w-12 h-6 rounded-full transition-all relative ${localSettings.notifications.habitsReminder.enabled ? 'bg-blue-600' : 'bg-slate-300'}`}
                    >
                      <div className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all ${localSettings.notifications.habitsReminder.enabled ? 'left-7' : 'left-1'}`} />
                    </button>
                  </div>
                </div>

                <div className="flex flex-col p-6 bg-slate-50 rounded-none md:rounded-2xl border border-slate-100 group hover:border-rose-200 transition-all gap-4">
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <p className="text-sm font-bold text-slate-900 mb-1">Lembrete de Pesagem</p>
                      <p className="text-[11px] text-slate-500 font-medium">Registrar peso na balanÃ§a</p>
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
                        className="bg-white border-none rounded-lg px-3 py-1.5 text-[10px] font-black uppercase text-slate-900 focus:ring-2 focus:ring-rose-500"
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
                        className="bg-white border-none rounded-lg px-3 py-1.5 text-[10px] font-black uppercase text-slate-900 focus:ring-2 focus:ring-rose-500"
                      >
                        <option value={0}>Domingo</option>
                        <option value={1}>Segunda</option>
                        <option value={2}>TerÃ§a</option>
                        <option value={3}>Quarta</option>
                        <option value={4}>Quinta</option>
                        <option value={5}>Sexta</option>
                        <option value={6}>SÃ¡bado</option>
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
                        className="bg-white border-none rounded-lg px-3 py-1.5 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-rose-500"
                      />
                    </div>
                  )}
                </div>
              </div>

              {/* Financeiro / AÃ§Ãµes Section */}
              <div className="space-y-4 animate-in slide-in-from-bottom-4 duration-500 delay-100">
                <h4 className="text-[10px] font-black text-slate-900 uppercase tracking-[0.2em] border-b border-slate-100 pb-2 flex items-center gap-2">
                  <span className="w-2 h-2 bg-emerald-500 rounded-full"></span>
                  Financeiro / AÃ§Ãµes
                </h4>

                <div className="flex items-center justify-between p-6 bg-slate-50 rounded-none md:rounded-2xl border border-slate-100 group hover:border-emerald-200 transition-all">
                  <div className="flex-1">
                    <p className="text-sm font-bold text-slate-900 mb-1">Risco OrÃ§amentÃ¡rio</p>
                    <p className="text-[11px] text-slate-500 font-medium">Avisar se gastos estiverem acima do esperado</p>
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

                <div className="flex items-center justify-between p-6 bg-slate-50 rounded-none md:rounded-2xl border border-slate-100 group hover:border-blue-200 transition-all">
                  <div className="flex-1">
                    <p className="text-sm font-bold text-slate-900 mb-1">AÃ§Ãµes Vencidas</p>
                    <p className="text-[11px] text-slate-500 font-medium">Alertar sobre tarefas fora do prazo</p>
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

                <div className="flex flex-col p-6 bg-slate-50 rounded-none md:rounded-2xl border border-slate-100 group hover:border-amber-200 transition-all gap-4">
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <p className="text-sm font-bold text-slate-900 mb-1">Audit PGC</p>
                      <p className="text-[11px] text-slate-500 font-medium">Verificar vÃ­nculos antes do fim do mÃªs</p>
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
                      <span className="text-[10px] font-black text-slate-400 uppercase">Avisar</span>
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
                        className="w-16 bg-white border-2 border-slate-100 rounded-lg px-3 py-1.5 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-amber-500 outline-none"
                      />
                      <span className="text-[10px] font-black text-slate-400 uppercase">dias antes</span>
                    </div>
                  )}
                </div>
              </div>

              {/* NotificaÃ§Ãµes Personalizadas Section */}
              <div className="space-y-4 animate-in slide-in-from-bottom-4 duration-500 delay-150">
                <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                  <h4 className="text-[10px] font-black text-slate-900 uppercase tracking-[0.2em] flex items-center gap-2">
                    <span className="w-2 h-2 bg-purple-500 rounded-full"></span>
                    Personalizadas
                  </h4>
                  <button
                    onClick={() => setIsAddingCustom(!isAddingCustom)}
                    className="text-[10px] font-black uppercase text-blue-600 hover:bg-blue-50 px-2 py-1 rounded transition-colors"
                  >
                    {isAddingCustom ? 'Cancelar' : '+ Nova'}
                  </button>
                </div>

                {/* Form de AdiÃ§Ã£o */}
                {isAddingCustom && (
                  <div className="bg-slate-50 p-4 rounded-xl border border-blue-100 flex flex-col gap-3 animate-in fade-in slide-in-from-top-2">
                    <input
                      type="text"
                      placeholder="Mensagem da notificaÃ§Ã£o..."
                      className="w-full bg-white border border-slate-200 rounded-lg px-3 py-2 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-blue-500 outline-none"
                      value={newCustom.message || ''}
                      onChange={e => setNewCustom({ ...newCustom, message: e.target.value })}
                    />
                    <div className="flex gap-2">
                      <select
                        className="bg-white border border-slate-200 rounded-lg px-3 py-2 text-[10px] font-black uppercase text-slate-700 outline-none focus:ring-2 focus:ring-blue-500"
                        value={newCustom.frequency}
                        onChange={e => setNewCustom({ ...newCustom, frequency: e.target.value as any })}
                      >
                        <option value="daily">DiÃ¡ria</option>
                        <option value="weekly">Semanal</option>
                        <option value="monthly">Mensal</option>
                      </select>
                      <input
                        type="time"
                        className="bg-white border border-slate-200 rounded-lg px-3 py-2 text-xs font-bold text-slate-900 outline-none focus:ring-2 focus:ring-blue-500"
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
                         <span className="text-[10px] font-black text-slate-400 uppercase">Dia do mÃªs:</span>
                         <input
                           type="number"
                           min="1"
                           max="31"
                           className="w-12 bg-white border border-slate-200 rounded-lg px-2 py-1 text-xs font-bold text-slate-900 outline-none focus:ring-2 focus:ring-blue-500"
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
                      className="bg-blue-600 text-white py-2 rounded-lg text-[10px] font-black uppercase tracking-widest hover:bg-blue-700 transition-colors disabled:opacity-50"
                    >
                      Salvar NotificaÃ§Ã£o
                    </button>
                  </div>
                )}

                {/* Lista de NotificaÃ§Ãµes Custom */}
                <div className="grid grid-cols-1 gap-3">
                  {(localSettings.notifications.custom || []).map(notif => (
                    <div key={notif.id} className="p-4 bg-white border border-slate-100 rounded-xl flex items-center justify-between group hover:border-purple-200 transition-all shadow-sm">
                      <div>
                        <p className="text-xs font-bold text-slate-900 line-clamp-1">{notif.message}</p>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-[9px] font-black text-purple-600 bg-purple-50 px-1.5 py-0.5 rounded uppercase">
                            {notif.time}
                          </span>
                          <span className="text-[9px] font-black text-slate-400 uppercase">
                            {notif.frequency === 'daily' ? 'DiÃ¡ria' :
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
                    <div className="text-center py-6 text-slate-300 text-[10px] font-black uppercase tracking-widest italic border-2 border-dashed border-slate-50 rounded-xl">
                      Nenhuma notificaÃ§Ã£o personalizada
                    </div>
                  )}
                </div>
              </div>

              {/* Canal de Teste Section */}
              <div className="space-y-4 animate-in slide-in-from-bottom-4 duration-500 delay-200">
                <h4 className="text-[10px] font-black text-slate-900 uppercase tracking-[0.2em] border-b border-slate-100 pb-2 flex items-center gap-2">
                  <span className="w-2 h-2 bg-indigo-500 rounded-full"></span>
                  Conectividade
                </h4>

                <div className="flex items-center justify-between p-6 bg-slate-50 rounded-none md:rounded-2xl border border-slate-100 group hover:border-indigo-200 transition-all">
                  <div className="flex-1">
                    <p className="text-sm font-bold text-slate-900 mb-1">NotificaÃ§Ãµes Push</p>
                    <p className="text-[11px] text-slate-500 font-medium">Receber alertas no celular (mesmo com app fechado)</p>
                  </div>
                  <button
                    onClick={() => setLocalSettings({
                      ...localSettings,
                      notifications: {
                        ...localSettings.notifications,
                        enablePush: !localSettings.notifications.enablePush
                      }
                    })}
                    className={`w-12 h-6 rounded-full transition-all relative ${localSettings.notifications.enablePush !== false ? 'bg-indigo-600' : 'bg-slate-300'}`}
                  >
                    <div className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all ${localSettings.notifications.enablePush !== false ? 'left-7' : 'left-1'}`} />
                  </button>
                </div>
              </div>

            </>
          ) : activeTab === 'context' ? (
            /* Unidades / Ã¡reas e Palavras-Chave TAB */
            <div className="space-y-6 animate-in slide-in-from-right-4 duration-500">
              <h4 className="text-[10px] font-black text-slate-900 uppercase tracking-[0.2em] border-b border-slate-100 pb-2 flex items-center gap-2">
                <span className="w-2 h-2 bg-amber-500 rounded-full"></span>
                Ãreas e Palavras-Chave
              </h4>

              <div className="space-y-4">
                {unidades.map((u) => {
                  const isProtected = ['CLC', 'ASSISTÃŠNCIA', 'ASSISTÃŠNCIA ESTUDANTIL'].includes(u.nome.toUpperCase());
                  return (
                    <div key={u.id} className={`p-6 bg-slate-50 rounded-none md:rounded-[2rem] border ${isProtected ? 'border-amber-200 bg-amber-50/30' : 'border-slate-100'} space-y-4 shadow-sm`}>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <h5 className="text-xs font-black text-slate-900 uppercase tracking-widest">{u.nome}</h5>
                          {isProtected && <span className="bg-amber-100 text-amber-700 px-2 py-0.5 rounded text-[8px] font-black uppercase tracking-widest">Protegido</span>}
                        </div>

                        {!isProtected && (
                          <button
                            onClick={() => { if (pendingDeleteUnidadeId !== u.id) { setPendingDeleteUnidadeId(u.id); window.setTimeout(() => setPendingDeleteUnidadeId((current) => (current === u.id ? null : current)), 3500); return; } setPendingDeleteUnidadeId(null); onDeleteUnidade(u.id); }}
                            className={`p-2 rounded-full transition-all ${pendingDeleteUnidadeId === u.id ? 'bg-rose-500 text-white' : 'text-rose-300 hover:text-rose-600 hover:bg-rose-50'}`}
                            title={pendingDeleteUnidadeId === u.id ? "Confirmar remoção" : "Remover Área"}
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                          </button>
                        )}
                      </div>

                      <div className="flex flex-wrap gap-2">
                        {(u.palavras_chave || []).map((kw, i) => (
                          <span key={i} className="inline-flex items-center gap-1 px-3 py-1 bg-white border border-slate-200 rounded-full text-[9px] font-black text-slate-600 uppercase group/kw">
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
                          className="flex-1 bg-white border border-slate-200 rounded-lg md:rounded-xl px-4 py-2 text-[10px] font-bold text-slate-900 focus:ring-2 focus:ring-blue-500 outline-none"
                        />
                        <button
                          onClick={() => handleAddKeyword(u.id, u.palavras_chave || [])}
                          className="bg-blue-600 text-white px-4 rounded-lg md:rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-blue-700 transition-all shadow-md shadow-blue-100"
                        >
                          Add
                        </button>
                      </div>
                    </div>
                  );
                })}

                <div className="p-6 bg-blue-50/50 rounded-none md:rounded-[2rem] border-2 border-dashed border-blue-200 flex flex-col gap-4">
                  <p className="text-[10px] font-black text-blue-600 uppercase tracking-widest text-center">Cadastrar Nova Ãrea de Contexto</p>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      placeholder="Nome da Unidade (ex: DEV, MARKETING)"
                      value={newUnidadeNome}
                      onChange={(e) => setNewUnidadeNome(e.target.value)}
                      className="flex-1 bg-white border border-blue-100 rounded-lg md:rounded-xl px-4 py-3 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-blue-500 outline-none shadow-sm"
                    />
                    <button
                      onClick={() => {
                        if (newUnidadeNome.trim()) {
                          onAddUnidade(newUnidadeNome.trim().toUpperCase());
                          setNewUnidadeNome('');
                        }
                      }}
                      className="bg-blue-600 text-white px-6 py-3 rounded-lg md:rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-blue-700 transition-all shadow-lg shadow-blue-200"
                    >
                      Criar
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ) : activeTab === 'sistemas' ? (
            <div className="space-y-6 animate-in slide-in-from-bottom-4 duration-500">
              <div className="space-y-4">
                <h4 className="text-[10px] font-black text-slate-900 uppercase tracking-[0.2em] border-b border-slate-100 pb-2 flex items-center gap-2">
                  <span className="w-2 h-2 bg-violet-500 rounded-full"></span>
                  Sistemas em Desenvolvimento
                </h4>

                <p className="text-xs text-slate-500 font-medium">
                  Cadastre os sistemas que vocÃª estÃ¡ desenvolvendo para gerenciÃ¡-los no mÃ³dulo Sistemas.
                </p>

                {/* Lista de Sistemas */}
                <div className="space-y-3">
                  {unidades.filter(u => u.nome.startsWith('SISTEMA:')).length > 0 ? (
                    unidades.filter(u => u.nome.startsWith('SISTEMA:')).map(sistema => (
                      <div key={sistema.id} className="bg-violet-50 border border-violet-100 rounded-none md:rounded-2xl p-6 group hover:border-violet-300 transition-all">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <div className="w-10 h-10 bg-violet-500 rounded-lg md:rounded-xl flex items-center justify-center">
                              <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
                              </svg>
                            </div>
                            <div>
                              <p className="text-sm font-black text-slate-900">{sistema.nome.replace('SISTEMA:', '').trim()}</p>
                              <p className="text-[10px] text-slate-500 font-medium">Sistema cadastrado</p>
                            </div>
                          </div>
                          <button
                            onClick={() => { if (pendingDeleteUnidadeId !== sistema.id) { setPendingDeleteUnidadeId(sistema.id); window.setTimeout(() => setPendingDeleteUnidadeId((current) => (current === sistema.id ? null : current)), 3500); return; } setPendingDeleteUnidadeId(null); onDeleteUnidade(sistema.id); }}
                            className={`opacity-100 md:opacity-0 md:group-hover:opacity-100 p-2 rounded-lg md:rounded-xl transition-all ${pendingDeleteUnidadeId === sistema.id ? 'bg-rose-500 text-white' : 'hover:bg-rose-100 text-rose-600'}`}
                            title={pendingDeleteUnidadeId === sistema.id ? "Confirmar remoção" : "Remover sistema"}
                          >
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                          </button>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="text-center py-12 bg-slate-50 rounded-none md:rounded-2xl border-2 border-dashed border-slate-200">
                      <div className="w-16 h-16 bg-violet-100 rounded-full flex items-center justify-center mx-auto mb-4">
                        <svg className="w-8 h-8 text-violet-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                        </svg>
                      </div>
                      <p className="text-slate-400 font-bold text-sm">Nenhum sistema cadastrado</p>
                      <p className="text-slate-400 text-xs mt-1">Adicione seu primeiro sistema abaixo</p>
                    </div>
                  )}
                </div>

                {/* FormulÃ¡rio para adicionar novo sistema */}
                <div className="bg-gradient-to-br from-violet-50 to-purple-50 border-2 border-violet-200 rounded-none md:rounded-2xl p-6">
                  <p className="text-[10px] font-black text-violet-600 uppercase tracking-widest text-center mb-4">Cadastrar Novo Sistema</p>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      placeholder="Nome do Sistema (ex: Hermes, Portal Web, API REST)"
                      value={newUnidadeNome}
                      onChange={(e) => setNewUnidadeNome(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && newUnidadeNome.trim()) {
                          onAddUnidade(`SISTEMA: ${newUnidadeNome.trim()}`);
                          setNewUnidadeNome('');
                        }
                      }}
                      className="flex-1 bg-white border border-violet-100 rounded-lg md:rounded-xl px-4 py-3 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-violet-500 outline-none shadow-sm"
                    />
                    <button
                      onClick={() => {
                        if (newUnidadeNome.trim()) {
                          onAddUnidade(`SISTEMA: ${newUnidadeNome.trim()}`);
                          setNewUnidadeNome('');
                        }
                      }}
                      className="bg-violet-600 text-white px-6 py-3 rounded-lg md:rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-violet-700 transition-all shadow-lg shadow-violet-200"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M12 4v16m8-8H4" />
                      </svg>
                    </button>
                  </div>
                  <p className="text-[9px] text-violet-600 font-medium mt-2 text-center">Pressione Enter ou clique no botÃ£o + para adicionar</p>
                </div>
              </div>
            </div>
          ) : activeTab === 'pomodoro' ? (
            <div className="space-y-6 animate-in slide-in-from-right-4 duration-500">
              <h4 className="text-[10px] font-black text-slate-900 uppercase tracking-[0.2em] border-b border-slate-100 pb-2 flex items-center gap-2">
                <span className="w-2 h-2 bg-rose-500 rounded-full"></span>
                ConfiguraÃ§Ãµes do Pomodoro
              </h4>

              <div className="flex items-center justify-between p-6 bg-slate-50 rounded-none md:rounded-2xl border border-slate-100 group hover:border-rose-200 transition-all">
                <div className="flex-1">
                  <p className="text-sm font-bold text-slate-900 mb-1">Ativar Pomodoro</p>
                  <p className="text-[11px] text-slate-500 font-medium">Habilitar ciclos de trabalho e descanso na execuÃ§Ã£o</p>
                </div>
                <button
                  onClick={() => setLocalSettings({
                    ...localSettings,
                    pomodoro: { ...localSettings.pomodoro!, enabled: !localSettings.pomodoro?.enabled }
                  })}
                  className={`w-12 h-6 rounded-full transition-all relative ${localSettings.pomodoro?.enabled ? 'bg-rose-600' : 'bg-slate-300'}`}
                >
                  <div className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all ${localSettings.pomodoro?.enabled ? 'left-7' : 'left-1'}`} />
                </button>
              </div>

              {localSettings.pomodoro?.enabled && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="p-6 bg-slate-50 rounded-none md:rounded-2xl border border-slate-100 space-y-3">
                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Tempo de Foco (minutos)</label>
                    <input
                      type="number"
                      min="1"
                      max="60"
                      value={localSettings.pomodoro?.focusTime || 10}
                      onChange={(e) => setLocalSettings({
                        ...localSettings,
                        pomodoro: { ...localSettings.pomodoro!, focusTime: Number(e.target.value) }
                      })}
                      className="w-full bg-white border border-slate-200 rounded-lg md:rounded-xl px-4 py-3 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-rose-500 outline-none"
                    />
                  </div>
                  <div className="p-6 bg-slate-50 rounded-none md:rounded-2xl border border-slate-100 space-y-3">
                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Tempo de Descanso (minutos)</label>
                    <input
                      type="number"
                      min="1"
                      max="30"
                      value={localSettings.pomodoro?.breakTime || 5}
                      onChange={(e) => setLocalSettings({
                        ...localSettings,
                        pomodoro: { ...localSettings.pomodoro!, breakTime: Number(e.target.value) }
                      })}
                      className="w-full bg-white border border-slate-200 rounded-lg md:rounded-xl px-4 py-3 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-rose-500 outline-none"
                    />
                  </div>
                </div>
              )}

              <div className="flex items-center justify-between p-6 bg-slate-50 rounded-none md:rounded-2xl border border-slate-100 group hover:border-amber-200 transition-all">
                <div className="flex-1">
                  <p className="text-sm font-bold text-slate-900 mb-1">Alertas Sonoros</p>
                  <p className="text-[11px] text-slate-500 font-medium">Emitir bipes discretos nos Ãºltimos 3 segundos</p>
                </div>
                <button
                  onClick={() => setLocalSettings({
                    ...localSettings,
                    pomodoro: { ...localSettings.pomodoro!, enableBeep: !localSettings.pomodoro?.enableBeep }
                  })}
                  className={`w-12 h-6 rounded-full transition-all relative ${localSettings.pomodoro?.enableBeep ? 'bg-amber-600' : 'bg-slate-300'}`}
                >
                  <div className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all ${localSettings.pomodoro?.enableBeep ? 'left-7' : 'left-1'}`} />
                </button>
              </div>
            </div>
          ) : activeTab === 'google' ? (
            <div className="space-y-6 animate-in slide-in-from-right-4 duration-500">
              <h4 className="text-[10px] font-black text-slate-900 uppercase tracking-[0.2em] border-b border-slate-100 pb-2 flex items-center gap-2">
                <span className="w-2 h-2 bg-blue-500 rounded-full"></span>
                IntegraÃ§Ã£o Google Drive
              </h4>

              <div className="p-6 bg-slate-50 rounded-none md:rounded-[2rem] border border-slate-100 space-y-4 shadow-sm">
                <p className="text-xs text-slate-500 font-medium">
                  Configure a pasta do Google Drive onde os arquivos do Pool de Dados serÃ£o armazenados.
                </p>

                <div className="space-y-2">
                  <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">ID da Pasta no Drive</label>
                  <input
                    type="text"
                    value={localSettings.googleDriveFolderId || ''}
                    onChange={(e) => setLocalSettings({ ...localSettings, googleDriveFolderId: e.target.value })}
                    placeholder="Ex: 1a2b3c4d5e6f7g8h9i0j..."
                    className="w-full bg-white border border-slate-200 rounded-lg md:rounded-xl px-4 py-3 text-xs font-mono text-slate-900 focus:ring-2 focus:ring-blue-500 outline-none"
                  />
                  <p className="text-[9px] text-slate-400 italic">
                    O ID da pasta Ã© a parte final da URL da pasta no Google Drive.
                  </p>
                </div>
              </div>

              <div className="p-6 bg-amber-50 rounded-none md:rounded-[2rem] border border-amber-100">
                <div className="flex gap-3">
                  <svg className="w-5 h-5 text-amber-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
                  <div>
                    <p className="text-xs font-bold text-amber-800 uppercase tracking-wider mb-1">Nota sobre PermissÃµes</p>
                    <p className="text-[10px] text-amber-700 leading-relaxed">
                      Ao adicionar novos escopos (como Google Drive), pode ser necessÃ¡rio re-autenticar o sistema usando o <strong>setup_credentials.bat</strong> para que o Hermes tenha permissÃ£o de escrita.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          ) : null}
        </div>

        <div className="p-8 bg-slate-50 border-t border-slate-100 flex gap-4 flex-shrink-0">
          <button onClick={onClose} className="flex-1 px-8 py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest text-slate-500 hover:bg-slate-200 transition-all">Cancelar</button>
          <button
            onClick={() => {
              onSave(localSettings);
              onClose();
            }}
            className="flex-1 bg-blue-600 text-white px-8 py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-blue-700 transition-all"
          >
            Salvar AlteraÃ§Ãµes
          </button>
        </div>
      </div>
    </div >
  );
};
export const DailyHabitsModal = ({
  habits,
  onUpdateHabits,
  onClose
}: {
  habits: DailyHabits,
  onUpdateHabits: (date: string, updates: Partial<DailyHabits>) => void,
  onClose: () => void
}) => {
  const todayStr = formatDateLocalISO(new Date());

  const handleHabitToggle = (habitKey: keyof DailyHabits) => {
    if (habitKey === 'id') return;
    onUpdateHabits(todayStr, { [habitKey]: !habits[habitKey] });
  };

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center p-0 md:p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-300">
      <div className="bg-white w-full h-full md:h-auto md:max-w-md rounded-none md:rounded-[2.5rem] shadow-2xl overflow-hidden animate-in zoom-in-95 duration-300">
        <div className="p-8 border-b border-slate-100 bg-amber-500/5 flex items-center justify-between">
          <div>
            <h3 className="text-xl font-black text-slate-900 tracking-tight flex items-center gap-3">
              <span className="w-2 h-8 bg-amber-500 rounded-full"></span>
              HÃ¡bitos de Hoje
            </h3>
            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mt-1">Lembrete DiÃ¡rio</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-200 rounded-full transition-colors">
            <svg className="w-6 h-6 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        <div className="p-8 space-y-3">
          {[
            { id: 'noSugar', label: 'Sem AÃ§Ãºcar', color: 'rose' },
            { id: 'noAlcohol', label: 'Sem Ãlcool', color: 'purple' },
            { id: 'noSnacks', label: 'Sem Lanches/Delivery', color: 'orange' },
            { id: 'workout', label: 'Treino do Dia', color: 'emerald' },
            { id: 'eatUntil18', label: 'Comer atÃ© as 18h', color: 'blue' },
            { id: 'eatSlowly', label: 'Comer Devagar', color: 'indigo' }
          ].map((habit) => {
            const colorMap: Record<string, { bg: string, border: string, text: string, dot: string }> = {
              rose: { bg: 'bg-rose-50', border: 'border-rose-200', text: 'text-rose-700', dot: 'bg-rose-500' },
              purple: { bg: 'bg-purple-50', border: 'border-purple-200', text: 'text-purple-700', dot: 'bg-purple-500' },
              orange: { bg: 'bg-orange-50', border: 'border-orange-200', text: 'text-orange-700', dot: 'bg-orange-500' },
              emerald: { bg: 'bg-emerald-50', border: 'border-emerald-200', text: 'text-emerald-700', dot: 'bg-emerald-500' },
              blue: { bg: 'bg-blue-50', border: 'border-blue-200', text: 'text-blue-700', dot: 'bg-blue-500' },
              indigo: { bg: 'bg-indigo-50', border: 'border-indigo-200', text: 'text-indigo-700', dot: 'bg-indigo-500' }
            };
            const colors = colorMap[habit.color] || colorMap.rose;
            const isActive = !!habits[habit.id as keyof DailyHabits];

            return (
              <button
                key={habit.id}
                onClick={() => handleHabitToggle(habit.id as keyof DailyHabits)}
                className={`w-full flex items-center justify-between p-4 rounded-none md:rounded-2xl border-2 transition-all duration-300 ${isActive
                  ? `${colors.bg} ${colors.border} shadow-sm`
                  : 'bg-white border-slate-100 hover:border-slate-200'
                  }`}
              >
                <span className={`text-sm font-bold ${isActive ? colors.text : 'text-slate-600'}`}>
                  {habit.label}
                </span>
                <div className={`w-6 h-6 rounded-full flex items-center justify-center transition-all ${isActive
                  ? `${colors.dot} text-white scale-110`
                  : 'border-2 border-slate-200'
                  }`}>
                  {isActive && (
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="4" d="M5 13l4 4L19 7" /></svg>
                  )}
                </div>
              </button>
            );
          })}
        </div>

        <div className="p-8 bg-slate-50 border-t border-slate-100">
          <button
            onClick={onClose}
            className="w-full bg-slate-900 text-white px-8 py-4 rounded-none md:rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all"
          >
            Concluir Registro
          </button>
        </div>
      </div>
    </div>
  );
};
export const TaskCreateModal = ({ unidades, onSave, onClose, showAlert, initialData }: { unidades: { id: string, nome: string }[], onSave: (data: Partial<Tarefa>) => void, onClose: () => void, showAlert: (title: string, message: string) => void, initialData?: Partial<Tarefa> }) => {
  const [formData, setFormData] = useState({
    titulo: initialData?.titulo || '',
    data_inicio: initialData?.data_inicio || formatDateLocalISO(new Date()),
    data_limite: initialData?.data_limite || '',
    data_criacao: new Date().toISOString(), // Actual creation timestamp
    status: initialData?.status || 'em andamento' as Status,
    categoria: initialData?.categoria || 'NÃƒO CLASSIFICADA' as Categoria,
    notas: initialData?.notas || '',
    is_single_day: !!initialData?.is_single_day,
    horario_inicio: initialData?.horario_inicio || '',
    horario_fim: initialData?.horario_fim || ''
  });

  const [autoClassified, setAutoClassified] = useState(false);

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-2 md:p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-300">
      <div className="bg-white w-full h-auto max-h-[95vh] md:max-w-md rounded-2xl md:rounded-[2rem] shadow-2xl overflow-hidden animate-in zoom-in-95 duration-300 flex flex-col">
        <div className="p-4 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between flex-shrink-0">
          <h3 className="text-lg font-black text-slate-900 tracking-tight">Nova AÃ§Ã£o</h3>
          <button onClick={onClose} className="p-1.5 hover:bg-slate-200 rounded-full transition-colors">
            <svg className="w-5 h-5 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        <div className="p-4 space-y-3 overflow-y-auto custom-scrollbar flex-1">
          <div className="space-y-1">
            <label htmlFor="task-title-input" className="text-[9px] font-black text-slate-400 uppercase tracking-widest pl-1">TÃ­tulo da Tarefa</label>
            <input
              id="task-title-input"
              type="text"
              autoFocus
              value={formData.titulo}
              onChange={e => {
                const newTitulo = e.target.value;
                const detectedArea = detectAreaFromTitle(newTitulo);

                setFormData({
                  ...formData,
                  titulo: newTitulo,
                  // SÃ³ atualiza a categoria automaticamente se ainda nÃ£o foi manualmente alterada
                  categoria: autoClassified ? formData.categoria : detectedArea
                });
              }}
              className="w-full bg-slate-100 border-none rounded-xl px-4 py-2.5 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-sans"
              placeholder="O que precisa ser feito?"
            />
            {formData.categoria !== 'NÃƒO CLASSIFICADA' && formData.categoria !== 'GERAL' && !autoClassified && (
              <p className="text-[8px] font-bold text-blue-600 pl-1 flex items-center gap-1">
                <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                Ãrea detectada automaticamente.
              </p>
            )}
          </div>

          <div className="flex items-center gap-3 bg-slate-50 p-2.5 rounded-xl border border-slate-100">
            <input
              type="checkbox"
              id="single-day"
              checked={formData.is_single_day}
              onChange={e => {
                const checked = e.target.checked;
                setFormData(prev => ({
                  ...prev,
                  is_single_day: checked,
                  data_inicio: checked ? prev.data_limite || prev.data_inicio : prev.data_inicio
                }));
              }}
              className="w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500 transition-all cursor-pointer"
            />
            <label htmlFor="single-day" className="text-[11px] font-bold text-slate-700 cursor-pointer select-none">Tarefa de um dia sÃ³ (Apenas Prazo Final)</label>
          </div>

          <div className="grid grid-cols-2 gap-3">
            {!formData.is_single_day && (
              <div className="space-y-1">
                <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest pl-1">InÃ­cio</label>
                <input
                  type="date"
                  value={formData.data_inicio}
                  onChange={e => setFormData({ ...formData, data_inicio: e.target.value })}
                  className="w-full bg-slate-100 border-none rounded-xl px-4 py-2 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-sans"
                />
              </div>
            )}
            <div className={`space-y-1 ${formData.is_single_day ? 'col-span-2' : ''}`}>
              <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest pl-1">Prazo Final</label>
              <input
                type="date"
                value={formData.data_limite}
                onChange={e => {
                  const newLimit = e.target.value;
                  setFormData(prev => ({
                    ...prev,
                    data_limite: newLimit,
                    data_inicio: prev.is_single_day ? newLimit : prev.data_inicio
                  }));
                }}
                className="w-full bg-slate-100 border-none rounded-xl px-4 py-2 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-sans"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest pl-1">Hora InÃ­cio</label>
              <input
                type="time"
                value={formData.horario_inicio}
                onChange={e => setFormData({ ...formData, horario_inicio: e.target.value })}
                className="w-full bg-slate-100 border-none rounded-xl px-4 py-2 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all"
              />
            </div>
            <div className="space-y-1">
              <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest pl-1">Hora Fim</label>
              <input
                type="time"
                value={formData.horario_fim}
                onChange={e => setFormData({ ...formData, horario_fim: e.target.value })}
                className="w-full bg-slate-100 border-none rounded-xl px-4 py-2 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all"
              />
            </div>
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
                <option value="concluÃ­do">ConcluÃ­do</option>
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest pl-1">Tag (ClassificaÃ§Ã£o)</label>
              <select
                value={formData.categoria}
                onChange={e => {
                  setFormData({ ...formData, categoria: e.target.value as Categoria });
                  setAutoClassified(true); // Marca que o usuÃ¡rio alterou manualmente
                }}
                className="w-full bg-slate-100 border-none rounded-xl px-4 py-2 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-black uppercase text-[9px] tracking-widest"
              >
                <option value="GERAL">Geral</option>
                <option value="NÃƒO CLASSIFICADA">NÃ£o Classificada</option>
                <option value="CLC">CLC</option>
                <option value="ASSISTÃŠNCIA">AssistÃªncia Estudantil</option>
                {unidades.filter(u => u.nome !== 'CLC' && u.nome !== 'AssistÃªncia Estudantil').map(u => (
                  <option key={u.id} value={u.nome.toUpperCase()}>{u.nome}</option>
                ))}
              </select>
            </div>
          </div>
        </div>

        <div className="p-4 bg-slate-50 border-t border-slate-100 flex gap-3 flex-shrink-0">
          <button onClick={onClose} className="flex-1 px-4 py-2.5 rounded-xl text-[9px] font-black uppercase tracking-widest text-slate-500 hover:bg-slate-200 transition-all border border-slate-200">Cancelar</button>
          <button
            onClick={() => {
              if (!formData.titulo || !formData.data_limite) {
                showAlert("AtenÃ§Ã£o", "Preencha o tÃ­tulo e o prazo final.");
                return;
              }

              // Validation
              if (!formData.is_single_day && formData.data_inicio > formData.data_limite) {
                showAlert("AtenÃ§Ã£o", "A data de inÃ­cio deve ser anterior ou igual ao prazo final.");
                return;
              }

              let finalNotes = formData.notas;
              if (formData.categoria !== 'NÃƒO CLASSIFICADA') {
                const tagStr = `Tag: ${formData.categoria}`;
                finalNotes = finalNotes ? `${finalNotes}\n\n${tagStr}` : tagStr;
              }

              onSave({
                ...formData,
                notas: finalNotes,
                data_criacao: new Date().toISOString()
              });
              onClose();
            }}
            className="flex-1 bg-blue-600 text-white px-4 py-2.5 rounded-xl text-[9px] font-black uppercase tracking-widest shadow-lg hover:bg-blue-700 transition-all"
          >
            Criar AÃ§Ã£o
          </button>
        </div>
      </div>
    </div>
  );
};
export const TaskEditModal = ({ unidades, task, onSave, onDelete, onClose, showAlert, showConfirm, pgcEntregas = [] }: { unidades: { id: string, nome: string }[], task: Tarefa, onSave: (id: string, updates: Partial<Tarefa>) => void, onDelete: (id: string) => void, onClose: () => void, showAlert: (title: string, message: string) => void, showConfirm: (title: string, message: string, onConfirm: () => void) => void, pgcEntregas?: EntregaInstitucional[] }) => {
  const [formData, setFormData] = useState({
    titulo: task.titulo,
    data_inicio: task.data_inicio || (task.data_criacao ? task.data_criacao.split('T')[0] : ''),
    data_limite: task.data_limite === '-' ? '' : task.data_limite,
    data_criacao: task.data_criacao,
    status: task.status,
    categoria: task.categoria || 'NÃƒO CLASSIFICADA',
    notas: task.notas || '',
    is_single_day: !!task.is_single_day,
    entregas_relacionadas: task.entregas_relacionadas || [],
    horario_inicio: task.horario_inicio || '',
    horario_fim: task.horario_fim || ''
  });

  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-2 md:p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-300">
      <div className="bg-white w-full h-auto max-h-[95vh] md:max-w-md flex flex-col rounded-2xl md:rounded-[2rem] shadow-2xl overflow-hidden animate-in zoom-in-95 duration-300">
        <div className="p-4 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between flex-shrink-0">
          <h3 className="text-lg font-black text-slate-900 tracking-tight">Editar Demanda</h3>
          <button onClick={onClose} className="p-1.5 hover:bg-slate-200 rounded-full transition-colors">
            <svg className="w-5 h-5 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        <div className="p-4 space-y-3 overflow-y-auto custom-scrollbar flex-1">
          <div className="space-y-1">
            <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest pl-1">TÃ­tulo da Tarefa</label>
            <input
              type="text"
              value={formData.titulo}
              onChange={e => setFormData({ ...formData, titulo: e.target.value })}
              className="w-full bg-slate-100 border-none rounded-xl px-4 py-2.5 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-sans"
              placeholder="TÃ­tulo da demanda..."
            />
          </div>

          <div className="flex items-center gap-3 bg-slate-50 p-2.5 rounded-xl border border-slate-100">
            <input
              type="checkbox"
              id="edit-single-day"
              checked={formData.is_single_day}
              onChange={e => {
                const checked = e.target.checked;
                setFormData(prev => ({
                  ...prev,
                  is_single_day: checked,
                  data_inicio: checked ? prev.data_limite || prev.data_inicio : prev.data_inicio
                }));
              }}
              className="w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500 transition-all cursor-pointer"
            />
            <label htmlFor="edit-single-day" className="text-[11px] font-bold text-slate-700 cursor-pointer select-none">Tarefa de um dia sÃ³ (Apenas Prazo Final)</label>
          </div>

          <div className="grid grid-cols-2 gap-3">
            {!formData.is_single_day && (
              <div className="space-y-1">
                <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest pl-1">InÃ­cio</label>
                <input
                  type="date"
                  value={formData.data_inicio}
                  onChange={e => setFormData({ ...formData, data_inicio: e.target.value })}
                  className="w-full bg-slate-100 border-none rounded-xl px-4 py-2 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-sans"
                />
              </div>
            )}
            <div className={`space-y-1 ${formData.is_single_day ? 'col-span-2' : ''}`}>
              <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest pl-1">Prazo Final</label>
              <input
                type="date"
                value={formData.data_limite}
                onChange={e => {
                  const newLimit = e.target.value;
                  setFormData(prev => ({
                    ...prev,
                    data_limite: newLimit,
                    data_inicio: prev.is_single_day ? newLimit : prev.data_inicio
                  }));
                }}
                className="w-full bg-slate-100 border-none rounded-xl px-4 py-2 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-sans"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest pl-1">Hora InÃ­cio</label>
              <input
                type="time"
                value={formData.horario_inicio}
                onChange={e => setFormData({ ...formData, horario_inicio: e.target.value })}
                className="w-full bg-slate-100 border-none rounded-xl px-4 py-2 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all"
              />
            </div>
            <div className="space-y-1">
              <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest pl-1">Hora Fim</label>
              <input
                type="time"
                value={formData.horario_fim}
                onChange={e => setFormData({ ...formData, horario_fim: e.target.value })}
                className="w-full bg-slate-100 border-none rounded-xl px-4 py-2 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3">
            <div className="space-y-1">
              <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest pl-1">Tag (ClassificaÃ§Ã£o)</label>
              <select
                value={formData.categoria}
                onChange={e => setFormData({ ...formData, categoria: e.target.value as Categoria })}
                className="w-full bg-slate-100 border-none rounded-xl px-4 py-2 text-xs font-bold text-slate-900 focus:ring-2 focus:ring-slate-900 transition-all font-black uppercase text-[9px] tracking-widest"
              >
                <option value="GERAL">Geral</option>
                <option value="NÃƒO CLASSIFICADA">NÃ£o Classificada</option>
                <option value="CLC">CLC</option>
                <option value="ASSISTÃŠNCIA">AssistÃªncia Estudantil</option>
                {unidades.filter(u => u.nome !== 'CLC' && u.nome !== 'AssistÃªncia Estudantil').map(u => (
                  <option key={u.id} value={u.nome.toUpperCase()}>{u.nome}</option>
                ))}
              </select>
            </div>

            {(formData.categoria === 'CLC' || formData.categoria === 'ASSISTÃŠNCIA' || formData.categoria === 'ASSISTÃŠNCIA ESTUDANTIL') && (
              <div className="space-y-1 animate-in fade-in slide-in-from-top-2">
                <label className="text-[9px] font-black text-blue-600 uppercase tracking-widest pl-1">Vincular ao PGC</label>
                <select
                  value={formData.entregas_relacionadas[0] || ''}
                  onChange={e => setFormData({ ...formData, entregas_relacionadas: e.target.value ? [e.target.value] : [] })}
                  className="w-full bg-blue-50 border-blue-100 rounded-xl px-4 py-2 text-[10px] font-bold text-blue-900 focus:ring-2 focus:ring-blue-500 transition-all"
                >
                  <option value="">NÃ£o vinculado ao PGC</option>
                  {pgcEntregas.map(e => (
                    <option key={e.id} value={e.id}>{e.entrega}</option>
                  ))}
                </select>
              </div>
            )}
          </div>
        </div>

        <div className="p-4 bg-slate-50 border-t border-slate-100 flex flex-col md:flex-row gap-2 flex-shrink-0">
          <button
            onClick={() => {
              if (!formData.titulo || !formData.data_limite) {
                showAlert("AtenÃ§Ã£o", "Preencha o tÃ­tulo e o prazo final.");
                return;
              }
              if (!formData.is_single_day && formData.data_inicio > formData.data_limite) {
                showAlert("AtenÃ§Ã£o", "A data de inÃ­cio deve ser anterior ou igual ao prazo final.");
                return;
              }
              onSave(task.id, formData);
              onClose();
            }}
            className="w-full md:flex-1 bg-slate-900 text-white px-4 py-2.5 rounded-xl text-[9px] font-black uppercase tracking-widest shadow-lg hover:bg-slate-800 transition-all order-1 md:order-2"
          >
            Salvar AlteraÃ§Ãµes
          </button>

          <div className="flex gap-2 order-2">
            <button
              onClick={() => {
                showConfirm("Confirmar ExclusÃ£o", "Deseja realmente excluir esta tarefa?", () => {
                   onDelete(task.id);
                   onClose();
                });
              }}
              className="flex-1 md:flex-none px-4 py-2.5 rounded-xl text-[9px] font-black uppercase tracking-widest transition-all border flex items-center justify-center gap-2 text-rose-600 hover:bg-rose-50 border-rose-100"
            >
              Excluir
            </button>
            <button
              onClick={onClose}
              className="flex-1 md:px-6 py-2.5 rounded-xl text-[9px] font-black uppercase tracking-widest text-slate-500 hover:bg-slate-200 transition-all border border-slate-200"
            >
              Cancelar
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};






