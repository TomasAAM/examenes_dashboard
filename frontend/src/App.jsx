import React, { useState, useEffect } from 'react';
import Header from './components/Header.jsx';
import UploadZone from './components/UploadZone.jsx';
import KpiCards from './components/KpiCards.jsx';
import TrendChart from './components/TrendChart.jsx';
import PanelMatrix from './components/PanelMatrix.jsx';
import UnmappedAlert from './components/UnmappedAlert.jsx';
import { Shield, Sparkles, Zap, Lock, RefreshCw } from 'lucide-react';

export default function App() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [isLocalAvailable, setIsLocalAvailable] = useState(false);
  const [selectedAnalyte, setSelectedAnalyte] = useState(null);

  // Check if static data.json exists or local API DB exists
  useEffect(() => {
    // 1. Try loading static data.json (for GitHub Pages and offline static mode)
    fetch('./data.json')
      .then((res) => {
        if (res.ok) return res.json();
        throw new Error('No static data');
      })
      .then((json) => {
        if (json && json.observations && json.observations.length > 0) {
          setData(json);
        }
      })
      .catch(() => {
        // Fallback: check if local backend API exists
        fetch('/api/local')
          .then((res) => {
            if (res.ok) setIsLocalAvailable(true);
          })
          .catch(() => setIsLocalAvailable(false));
      });

    // Also check if local API is available for live reload
    fetch('/api/local')
      .then((res) => {
        if (res.ok) setIsLocalAvailable(true);
      })
      .catch(() => setIsLocalAvailable(false));
  }, []);

  const handleFilesSelected = async (files) => {
    if (!files || files.length === 0) return;
    setLoading(true);
    setError(null);

    const formData = new FormData();
    files.forEach((file) => {
      formData.append('files', file);
    });

    try {
      const response = await fetch('/api/parse', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errJson = await response.json().catch(() => ({}));
        throw new Error(errJson.detail || `Error HTTP ${response.status}`);
      }

      const json = await response.json();
      setData(json);
    } catch (err) {
      console.error('Failed to parse PDFs:', err);
      setError(err.message || 'Ocurrió un error al procesar los archivos PDF.');
    } finally {
      setLoading(false);
    }
  };

  const handleDemo = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/demo');
      if (!response.ok) throw new Error('No se pudo cargar los datos de demostración.');
      const json = await response.json();
      setData(json);
    } catch (err) {
      console.error(err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleLocal = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/local');
      if (!response.ok) throw new Error('No se pudo cargar la base de datos local.');
      const json = await response.json();
      setData(json);
    } catch (err) {
      console.error(err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleClear = () => {
    setData(null);
    setError(null);
    setSelectedAnalyte(null);
  };

  return (
    <div className="min-h-screen flex flex-col bg-[#0B0F19] text-slate-100 antialiased">
      {/* Top Navigation */}
      <Header
        hasData={Boolean(data)}
        onDemo={handleDemo}
        onLocal={handleLocal}
        onClear={handleClear}
        loading={loading}
        isLocalAvailable={isLocalAvailable}
      />

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8 space-y-6">
        {!data ? (
          /* Empty / Welcome State */
          <div className="max-w-3xl mx-auto space-y-8 py-4 sm:py-8">
            {/* Hero text */}
            <div className="text-center space-y-3">
              <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-cyan-950/60 text-cyan-300 border border-cyan-500/30">
                <Sparkles className="h-3.5 w-3.5 text-cyan-400" />
                <span>Visualizador Efímero de Laboratorio</span>
              </div>
              <h2 className="text-2xl sm:text-4xl font-extrabold tracking-tight text-white">
                Compara tus exámenes de sangre en segundos
              </h2>
              <p className="text-sm sm:text-base text-slate-400 max-w-xl mx-auto">
                Arrastra tus informes PDF de BioNet para ver la evolución de tus parámetros, rangos de referencia y alertas fuera de rango.
              </p>
            </div>

            {/* Upload Area */}
            <UploadZone
              onFilesSelected={handleFilesSelected}
              loading={loading}
              error={error}
              onDemo={handleDemo}
            />

            {/* Feature Highlights */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-4">
              <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800/80 flex items-start gap-3">
                <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 shrink-0">
                  <Lock className="h-4 w-4" />
                </div>
                <div>
                  <h4 className="text-xs font-semibold text-white">100% Privado en RAM</h4>
                  <p className="text-[11px] text-slate-400 mt-0.5">
                    Tus datos existen sólo durante tu sesión. Al cerrar la pestaña todo se borra de la memoria.
                  </p>
                </div>
              </div>

              <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800/80 flex items-start gap-3">
                <div className="p-2 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 shrink-0">
                  <Zap className="h-4 w-4" />
                </div>
                <div>
                  <h4 className="text-xs font-semibold text-white">Extracción de Coordenadas</h4>
                  <p className="text-[11px] text-slate-400 mt-0.5">
                    Elimina textos invisibles, desambigua nombres duplicados y normaliza unidades.
                  </p>
                </div>
              </div>

              <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800/80 flex items-start gap-3">
                <div className="p-2 rounded-lg bg-blue-500/10 text-blue-400 border border-blue-500/20 shrink-0">
                  <Shield className="h-4 w-4" />
                </div>
                <div>
                  <h4 className="text-xs font-semibold text-white">Rango vs Asterisco</h4>
                  <p className="text-[11px] text-slate-400 mt-0.5">
                    Recalcula matemáticamente si un valor está fuera de rango sin fiarse solo de asteriscos.
                  </p>
                </div>
              </div>
            </div>
          </div>
        ) : (
          /* Active Dashboard State */
          <div className="space-y-6">
            {/* Unmapped analytes warning (if any) */}
            <UnmappedAlert unmapped={data.unmapped} />

            {/* KPI Summary Cards */}
            <KpiCards kpis={data.kpis} />

            {/* Longitudinal Trend Visualizer */}
            <TrendChart
              observations={data.observations}
              analytes={data.analytes}
              draws={data.draws}
              selectedAnalyteFromTable={selectedAnalyte}
            />

            {/* Cross-Draw Multi-Panel Matrix */}
            <PanelMatrix
              observations={data.observations}
              draws={data.draws}
              categories={data.categories}
              onSelectAnalyte={setSelectedAnalyte}
            />
          </div>
        )}
      </main>

      {/* Clean Footer */}
      <footer className="border-t border-slate-800/60 py-4 bg-slate-950/40 mt-auto text-center text-[11px] text-slate-500">
        <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-2">
          <span>Exámenes Dashboard • Ingestión y visualización local</span>
          <span className="flex items-center gap-1 text-slate-400">
            <Lock className="h-3 w-3 text-emerald-400" /> Sin almacenamiento en servidores externos
          </span>
        </div>
      </footer>
    </div>
  );
}
