import React, { useState, useRef } from 'react';
import { UploadCloud, FileText, Loader2, Sparkles, AlertCircle } from 'lucide-react';

export default function UploadZone({ onFilesSelected, loading, error, onDemo }) {
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef(null);

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragOver(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const pdfFiles = Array.from(e.dataTransfer.files).filter(
        (f) => f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf')
      );
      if (pdfFiles.length > 0) {
        onFilesSelected(pdfFiles);
      }
    }
  };

  const handleFileInput = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      onFilesSelected(Array.from(e.target.files));
    }
  };

  return (
    <div className="w-full">
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => !loading && fileInputRef.current?.click()}
        className={`relative group cursor-pointer rounded-2xl border-2 border-dashed transition-all duration-200 p-8 sm:p-12 text-center flex flex-col items-center justify-center ${
          isDragOver
            ? 'border-cyan-400 bg-cyan-950/20 scale-[1.01]'
            : 'border-slate-700/80 hover:border-cyan-500/50 bg-slate-900/50 hover:bg-slate-900/80'
        } ${loading ? 'pointer-events-none opacity-80' : ''}`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,application/pdf"
          multiple
          onChange={handleFileInput}
          className="hidden"
        />

        {loading ? (
          <div className="flex flex-col items-center py-4">
            <div className="h-14 w-14 rounded-full bg-cyan-500/10 flex items-center justify-center text-cyan-400 mb-4 animate-pulse">
              <Loader2 className="h-8 w-8 animate-spin" />
            </div>
            <h3 className="text-base font-semibold text-white">Analizando exámenes en memoria...</h3>
            <p className="text-xs text-slate-400 mt-1 max-w-sm">
              Extrayendo coordenadas, analitos, rangos de referencia y normalizando valores sin guardar nada en disco.
            </p>
          </div>
        ) : (
          <div className="flex flex-col items-center">
            <div className="h-16 w-16 rounded-2xl bg-gradient-to-b from-slate-800 to-slate-900 border border-slate-700/80 group-hover:border-cyan-500/50 group-hover:shadow-lg group-hover:shadow-cyan-500/10 flex items-center justify-center text-cyan-400 mb-4 transition-all group-hover:scale-110">
              <UploadCloud className="h-8 w-8" />
            </div>

            <h3 className="text-base sm:text-lg font-bold text-white mb-1">
              Arrastra tus informes de laboratorio PDF aquí
            </h3>
            <p className="text-xs sm:text-sm text-slate-400 max-w-md mb-4">
              Compatible con informes <span className="text-cyan-400 font-medium">BioNet</span>. Puedes subir 1 o múltiples archivos a la vez para comparar tu evolución.
            </p>

            <div className="flex flex-wrap items-center justify-center gap-3">
              <button
                type="button"
                className="px-4 py-2 text-xs font-semibold rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 transition-all shadow-md shadow-cyan-500/20"
              >
                Seleccionar archivos PDF
              </button>

              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onDemo();
                }}
                className="px-4 py-2 text-xs font-medium rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-all flex items-center gap-1.5"
              >
                <Sparkles className="h-3.5 w-3.5 text-amber-400" />
                <span>¿No tienes PDFs a mano? Probar Demo</span>
              </button>
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="mt-4 p-3.5 rounded-xl bg-rose-950/40 border border-rose-800/60 text-rose-300 text-xs flex items-start gap-2.5">
          <AlertCircle className="h-4 w-4 text-rose-400 shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold">Error al procesar: </span>
            {error}
          </div>
        </div>
      )}
    </div>
  );
}
