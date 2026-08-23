import React, { useState } from 'react';
import { AlertCircle, ChevronDown, ChevronUp, FileCode2 } from 'lucide-react';

export default function UnmappedAlert({ unmapped }) {
  const [isOpen, setIsOpen] = useState(false);

  if (!unmapped || unmapped.length === 0) return null;

  return (
    <div className="rounded-2xl bg-amber-950/30 border border-amber-500/40 p-4 text-xs text-amber-200 backdrop-blur-sm">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <AlertCircle className="h-4 w-4 text-amber-400 shrink-0" />
          <span className="font-semibold text-amber-300">
            Se encontraron {unmapped.length} analitos no mapeados en tus PDFs
          </span>
        </div>
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="text-amber-400 hover:text-amber-300 flex items-center gap-1 font-medium text-[11px]"
        >
          <span>{isOpen ? 'Ocultar detalles' : 'Ver analitos'}</span>
          {isOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        </button>
      </div>

      {isOpen && (
        <div className="mt-3 pt-3 border-t border-amber-800/40 space-y-2">
          <p className="text-[11px] text-amber-300/80">
            Estos exámenes fueron leídos pero sus nombres exactos no están registrados en <code className="bg-amber-900/50 px-1 py-0.5 rounded font-mono text-[10px]">config/aliases.yaml</code>:
          </p>
          <div className="max-h-40 overflow-y-auto space-y-1 pr-1 font-mono text-[11px]">
            {unmapped.map((u, i) => (
              <div key={i} className="p-2 rounded-lg bg-amber-950/60 border border-amber-900/50 flex items-center justify-between">
                <span className="font-medium text-amber-200">{u.name_raw}</span>
                <span className="text-amber-400/70 text-[10px]">{u.panel || 'Panel no especificado'}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
