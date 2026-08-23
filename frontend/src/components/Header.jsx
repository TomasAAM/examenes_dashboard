import React from 'react';
import { Activity, ShieldCheck, Sparkles, Database, Trash2, FileText } from 'lucide-react';

export default function Header({ hasData, onDemo, onLocal, onClear, loading, isLocalAvailable }) {
  return (
    <header className="border-b border-slate-800/80 bg-slate-950/70 backdrop-blur-md sticky top-0 z-40">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between py-3.5 gap-3">
          {/* Logo & Title */}
          <div className="flex items-center space-x-3">
            <div className="h-10 w-10 rounded-xl bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center shadow-lg shadow-cyan-500/20 ring-1 ring-cyan-400/30">
              <Activity className="h-5 w-5 text-white stroke-[2.5]" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-lg font-bold tracking-tight text-white">
                  Exámenes <span className="text-cyan-400 font-normal text-sm sm:text-base">Dashboard</span>
                </h1>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-950/60 text-emerald-300 border border-emerald-500/30">
                  <ShieldCheck className="h-3 w-3 text-emerald-400" />
                  <span className="hidden xs:inline">100% In-Memory</span>
                  <span className="xs:hidden">Privado</span>
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Visualizador de exámenes de laboratorio BioNet
              </p>
            </div>
          </div>

          {/* Action Bar */}
          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={onDemo}
              disabled={loading}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700/60 transition-all hover:border-slate-600 disabled:opacity-50 shadow-sm"
              title="Cargar resultados de ejemplo para probar la aplicación"
            >
              <Sparkles className="h-3.5 w-3.5 text-amber-400" />
              <span>Ver Demo</span>
            </button>

            {isLocalAvailable && (
              <button
                onClick={onLocal}
                disabled={loading}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700/60 transition-all hover:border-cyan-500/40 disabled:opacity-50 shadow-sm"
                title="Cargar los datos guardados en data/labs.duckdb"
              >
                <Database className="h-3.5 w-3.5 text-cyan-400" />
                <span>Base Local</span>
              </button>
            )}

            {hasData && (
              <button
                onClick={onClear}
                disabled={loading}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-rose-950/40 hover:bg-rose-900/60 text-rose-300 border border-rose-800/40 transition-all disabled:opacity-50"
                title="Borrar datos de la memoria y reiniciar"
              >
                <Trash2 className="h-3.5 w-3.5 text-rose-400" />
                <span>Limpiar</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
