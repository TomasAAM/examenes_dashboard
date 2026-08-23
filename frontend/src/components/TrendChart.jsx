import React, { useState, useMemo } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';
import annotationPlugin from 'chartjs-plugin-annotation';
import { Line } from 'react-chartjs-2';
import { TrendingUp, Search, Info, AlertTriangle, CheckCircle2, ChevronRight } from 'lucide-react';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
  annotationPlugin
);

export default function TrendChart({ observations, analytes, draws, selectedAnalyteFromTable }) {
  // Collect all unique analytes that have numeric values
  const availableAnalytes = useMemo(() => {
    if (!observations || observations.length === 0) return [];
    const codeMap = new Map();

    observations.forEach((o) => {
      if (o.value_num !== null && !codeMap.has(o.analyte_code)) {
        codeMap.set(o.analyte_code, {
          code: o.analyte_code,
          name_es: o.display_name_es || o.analyte_name_raw,
          name_en: o.display_name_en,
          category: o.category || 'General',
          unit: o.unit || o.canonical_unit || '',
        });
      }
    });

    return Array.from(codeMap.values()).sort((a, b) =>
      a.name_es.localeCompare(b.name_es, 'es', { sensitivity: 'base' })
    );
  }, [observations]);

  // Default selection: Ferritin, Cholesterol, Glucose, or the first available
  const [selectedCode, setSelectedCode] = useState(() => {
    const preferred = ['ferritin', 'cholesterol_total', 'glucose', 'vitamin_d_25oh', 'alt', 'hemoglobin_blood'];
    const match = availableAnalytes.find((a) => preferred.includes(a.code));
    return match ? match.code : availableAnalytes[0]?.code || '';
  });

  React.useEffect(() => {
    if (selectedAnalyteFromTable && availableAnalytes.some((a) => a.code === selectedAnalyteFromTable)) {
      setSelectedCode(selectedAnalyteFromTable);
    }
  }, [selectedAnalyteFromTable, availableAnalytes]);

  const [searchTerm, setSearchTerm] = useState('');

  // Filter analytes for dropdown search
  const filteredAnalytes = useMemo(() => {
    if (!searchTerm) return availableAnalytes;
    const term = searchTerm.toLowerCase();
    return availableAnalytes.filter(
      (a) =>
        a.name_es.toLowerCase().includes(term) ||
        (a.name_en && a.name_en.toLowerCase().includes(term)) ||
        a.category.toLowerCase().includes(term) ||
        a.code.toLowerCase().includes(term)
    );
  }, [availableAnalytes, searchTerm]);

  // Extract time-series data for the selected analyte
  const currentSeries = useMemo(() => {
    if (!selectedCode || !observations) return [];
    return observations
      .filter((o) => o.analyte_code === selectedCode && o.value_num !== null)
      .sort((a, b) => (a.sample_date || '').localeCompare(b.sample_date || ''));
  }, [selectedCode, observations]);

  if (availableAnalytes.length === 0) {
    return null;
  }

  const selectedMeta = availableAnalytes.find((a) => a.code === selectedCode) || availableAnalytes[0];
  const latestObs = currentSeries[currentSeries.length - 1];
  const previousObs = currentSeries.length > 1 ? currentSeries[currentSeries.length - 2] : null;

  // Compute reference bounds from series (use latest valid reference)
  const refLow = latestObs?.ref_low ?? currentSeries.find((o) => o.ref_low !== null)?.ref_low;
  const refHigh = latestObs?.ref_high ?? currentSeries.find((o) => o.ref_high !== null)?.ref_high;
  const unit = latestObs?.unit || selectedMeta?.unit || '';

  // Chart dataset and configuration
  const labels = currentSeries.map((o) => {
    if (!o.sample_date) return 'S/F';
    const [y, m, d] = o.sample_date.split('-');
    return new Date(parseInt(y), parseInt(m) - 1, parseInt(d)).toLocaleDateString('es-CL', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    });
  });

  const values = currentSeries.map((o) => o.value_num);
  const pointColors = currentSeries.map((o) =>
    o.out_of_range ? 'rgba(251, 146, 60, 1)' : 'rgba(14, 165, 233, 1)'
  );
  const pointBorderColors = currentSeries.map((o) =>
    o.out_of_range ? 'rgba(234, 88, 12, 1)' : 'rgba(2, 132, 199, 1)'
  );

  // Determine Y-axis limits comfortably enclosing points and reference range
  const allY = [...values.filter((v) => v !== null)];
  if (refLow !== null && refLow !== undefined) allY.push(refLow);
  if (refHigh !== null && refHigh !== undefined) allY.push(refHigh);

  const minY = Math.min(...allY);
  const maxY = Math.max(...allY);
  const padding = (maxY - minY) * 0.2 || maxY * 0.1 || 5;

  const chartData = {
    labels,
    datasets: [
      {
        label: selectedMeta?.name_es || 'Valor',
        data: values,
        borderColor: '#0ea5e9',
        backgroundColor: 'rgba(14, 165, 233, 0.12)',
        pointBackgroundColor: pointColors,
        pointBorderColor: pointBorderColors,
        pointBorderWidth: 2,
        pointRadius: 6,
        pointHoverRadius: 8,
        tension: 0.25,
        fill: false,
      },
    ],
  };

  const annotations = {};
  if (refLow !== null && refLow !== undefined && refHigh !== null && refHigh !== undefined) {
    annotations.rangeBox = {
      type: 'box',
      yMin: refLow,
      yMax: refHigh,
      backgroundColor: 'rgba(16, 185, 129, 0.08)',
      borderColor: 'rgba(16, 185, 129, 0.3)',
      borderWidth: 1,
      borderDash: [4, 4],
      label: {
        display: true,
        content: `Rango normal: ${refLow} - ${refHigh} ${unit}`,
        position: 'start',
        color: '#6ee7b7',
        font: { size: 10, weight: 'normal' },
      },
    };
  } else if (refHigh !== null && refHigh !== undefined) {
    annotations.highLine = {
      type: 'line',
      yMin: refHigh,
      yMax: refHigh,
      borderColor: 'rgba(16, 185, 129, 0.5)',
      borderWidth: 1.5,
      borderDash: [4, 4],
      label: {
        display: true,
        content: `Límite sup: < ${refHigh} ${unit}`,
        position: 'start',
        color: '#6ee7b7',
        font: { size: 10 },
      },
    };
  } else if (refLow !== null && refLow !== undefined) {
    annotations.lowLine = {
      type: 'line',
      yMin: refLow,
      yMax: refLow,
      borderColor: 'rgba(16, 185, 129, 0.5)',
      borderWidth: 1.5,
      borderDash: [4, 4],
      label: {
        display: true,
        content: `Límite inf: > ${refLow} ${unit}`,
        position: 'start',
        color: '#6ee7b7',
        font: { size: 10 },
      },
    };
  }

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      annotation: { annotations },
      tooltip: {
        backgroundColor: 'rgba(15, 23, 42, 0.95)',
        titleColor: '#f8fafc',
        bodyColor: '#cbd5e1',
        borderColor: 'rgba(51, 65, 85, 0.8)',
        borderWidth: 1,
        padding: 12,
        boxPadding: 6,
        usePointStyle: true,
        callbacks: {
          label: (context) => {
            const obs = currentSeries[context.dataIndex];
            const status = obs.out_of_range ? '⚠️ Fuera de rango' : '✅ En rango';
            const ref = obs.ref_text ? ` (${obs.ref_text})` : '';
            return [`Resultado: ${context.parsed.y} ${unit}`, `Referencia: ${ref || 'No especificada'}`, `Estado: ${status}`];
          },
        },
      },
    },
    scales: {
      x: {
        grid: { color: 'rgba(51, 65, 85, 0.3)' },
        ticks: { color: '#94a3b8', font: { size: 11 } },
      },
      y: {
        min: Math.max(0, minY - padding),
        max: maxY + padding,
        grid: { color: 'rgba(51, 65, 85, 0.3)' },
        ticks: {
          color: '#94a3b8',
          font: { size: 11 },
          callback: (value) => `${value} ${unit}`,
        },
      },
    },
  };

  // Delta computation
  let deltaText = null;
  if (latestObs && previousObs && previousObs.value_num !== null) {
    const diff = latestObs.value_num - previousObs.value_num;
    const sign = diff > 0 ? '+' : '';
    const pct = previousObs.value_num !== 0 ? ((diff / previousObs.value_num) * 100).toFixed(1) : null;
    deltaText = `${sign}${diff.toFixed(2)} ${unit} (${sign}${pct}%) vs toma anterior`;
  }

  return (
    <div className="rounded-2xl bg-slate-900/60 border border-slate-800/80 p-4 sm:p-6 backdrop-blur-sm shadow-sm">
      {/* Header & Analyte Search Picker */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
        <div>
          <div className="flex items-center gap-2">
            <TrendingUp className="h-5 w-5 text-cyan-400" />
            <h2 className="text-base sm:text-lg font-bold text-white">
              Evolución Longitudinal
            </h2>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Compara la trayectoria de cualquier parámetro a lo largo de las distintas tomas
          </p>
        </div>

        {/* Analyte Selector with Search */}
        <div className="flex items-center gap-2 w-full md:w-auto">
          <div className="relative flex-1 md:w-72">
            <select
              value={selectedCode}
              onChange={(e) => setSelectedCode(e.target.value)}
              className="w-full pl-3 pr-8 py-2 text-xs sm:text-sm font-medium rounded-xl bg-slate-800 border border-slate-700 text-white focus:outline-none focus:ring-2 focus:ring-cyan-500/50 focus:border-cyan-500 transition-all appearance-none cursor-pointer"
            >
              {availableAnalytes.map((a) => (
                <option key={a.code} value={a.code}>
                  {a.name_es} ({a.category})
                </option>
              ))}
            </select>
            <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-slate-400">
              <ChevronRight className="h-4 w-4 rotate-90" />
            </div>
          </div>
        </div>
      </div>

      {/* Chart Canvas */}
      <div className="h-64 sm:h-80 w-full relative">
        {currentSeries.length > 0 ? (
          <Line data={chartData} options={chartOptions} />
        ) : (
          <div className="h-full flex items-center justify-center text-slate-500 text-xs">
            Sin datos numéricos disponibles para este analito
          </div>
        )}
      </div>

      {/* Metric Detail Summary Box */}
      {latestObs && (
        <div className="mt-5 grid grid-cols-1 sm:grid-cols-3 gap-3 pt-4 border-t border-slate-800/80 text-xs">
          <div className="p-3 rounded-xl bg-slate-950/40 border border-slate-800/60">
            <span className="text-slate-400 block text-[11px]">Última Lectura</span>
            <div className="flex items-baseline gap-1.5 mt-0.5">
              <span className="text-lg font-bold text-white">
                {latestObs.value_num ?? latestObs.value_text}
              </span>
              <span className="text-slate-400 text-xs">{unit}</span>
              {latestObs.out_of_range ? (
                <span className="ml-auto inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-amber-950/60 text-amber-300 border border-amber-500/30">
                  <AlertTriangle className="h-2.5 w-2.5" /> Fuera de rango
                </span>
              ) : (
                <span className="ml-auto inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-950/60 text-emerald-300 border border-emerald-500/30">
                  <CheckCircle2 className="h-2.5 w-2.5" /> Normal
                </span>
              )}
            </div>
            {deltaText && <span className="text-[10px] text-cyan-400 block mt-1">{deltaText}</span>}
          </div>

          <div className="p-3 rounded-xl bg-slate-950/40 border border-slate-800/60">
            <span className="text-slate-400 block text-[11px]">Rango de Referencia</span>
            <span className="text-sm font-semibold text-slate-200 block mt-0.5">
              {latestObs.ref_text ? `${latestObs.ref_text} ${unit}` : 'No definido'}
            </span>
            <span className="text-[10px] text-slate-500 block mt-1">
              {latestObs.method ? `Método: ${latestObs.method}` : 'Laboratorio BioNet'}
            </span>
          </div>

          <div className="p-3 rounded-xl bg-slate-950/40 border border-slate-800/60">
            <span className="text-slate-400 block text-[11px]">Panel & Ubicación</span>
            <span className="text-sm font-semibold text-slate-200 block mt-0.5 truncate">
              {latestObs.panel || 'Panel General'}
            </span>
            <span className="text-[10px] text-slate-500 block mt-1 truncate">
              {latestObs.source_file} (pág. {latestObs.source_page})
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
