import React, { useState, useMemo } from 'react';
import { Search, Filter, AlertTriangle, Layers, ArrowUpRight, ArrowDownRight, Eye } from 'lucide-react';

export default function PanelMatrix({ observations, draws, categories, onSelectAnalyte }) {
  const [selectedCategory, setSelectedCategory] = useState('ALL');
  const [searchTerm, setSearchTerm] = useState('');
  const [onlyOutOfRange, setOnlyOutOfRange] = useState(false);

  // Sorted list of unique sample dates
  const sampleDates = useMemo(() => {
    if (!draws || draws.length === 0) return [];
    return draws
      .map((d) => d.sample_date)
      .filter(Boolean)
      .sort();
  }, [draws]);

  const formatDateHeader = (dStr) => {
    if (!dStr) return '';
    try {
      const [y, m, d] = dStr.split('-');
      const date = new Date(parseInt(y), parseInt(m) - 1, parseInt(d));
      return date.toLocaleDateString('es-CL', { day: 'numeric', month: 'short', year: '2-digit' });
    } catch {
      return dStr;
    }
  };

  // Group observations by analyte_code
  const rows = useMemo(() => {
    if (!observations) return [];

    const map = new Map();

    observations.forEach((obs) => {
      const key = obs.analyte_code;
      if (!map.has(key)) {
        map.set(key, {
          code: obs.analyte_code,
          name_es: obs.display_name_es || obs.analyte_name_raw,
          name_en: obs.display_name_en,
          category: obs.category || 'Otros',
          panel: obs.panel,
          unit: obs.unit || obs.canonical_unit || '',
          ref_text: obs.ref_text || (obs.ref_low !== null && obs.ref_high !== null ? `${obs.ref_low} - ${obs.ref_high}` : ''),
          ref_low: obs.ref_low,
          ref_high: obs.ref_high,
          concerning_direction: obs.concerning_direction,
          valuesByDate: {},
          hasOutOfRange: false,
        });
      }

      const item = map.get(key);
      if (obs.sample_date) {
        item.valuesByDate[obs.sample_date] = obs;
      }
      if (obs.out_of_range) {
        item.hasOutOfRange = true;
      }
      if (!item.ref_text && obs.ref_text) {
        item.ref_text = obs.ref_text;
      }
      if (item.ref_low === null && obs.ref_low !== null) item.ref_low = obs.ref_low;
      if (item.ref_high === null && obs.ref_high !== null) item.ref_high = obs.ref_high;
    });

    let list = Array.from(map.values());

    // Filter by category tab
    if (selectedCategory !== 'ALL') {
      list = list.filter((r) => r.category === selectedCategory);
    }

    // Filter by out-of-range toggle
    if (onlyOutOfRange) {
      list = list.filter((r) => r.hasOutOfRange);
    }

    // Filter by search query
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      list = list.filter(
        (r) =>
          r.name_es.toLowerCase().includes(term) ||
          (r.name_en && r.name_en.toLowerCase().includes(term)) ||
          r.code.toLowerCase().includes(term) ||
          (r.panel && r.panel.toLowerCase().includes(term))
      );
    }

    return list.sort((a, b) => {
      if (a.category !== b.category) {
        return a.category.localeCompare(b.category, 'es');
      }
      return a.name_es.localeCompare(b.name_es, 'es');
    });
  }, [observations, selectedCategory, searchTerm, onlyOutOfRange]);

  return (
    <div className="rounded-2xl bg-slate-900/60 border border-slate-800/80 p-4 sm:p-6 backdrop-blur-sm shadow-sm">
      {/* Title and Controls */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 mb-5">
        <div>
          <div className="flex items-center gap-2">
            <Layers className="h-5 w-5 text-cyan-400" />
            <h2 className="text-base sm:text-lg font-bold text-white">
              Matriz Comparativa por Tomas
            </h2>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Vista horizontal de todos los exámenes agrupados por categoría y fecha
          </p>
        </div>

        {/* Filter Bar */}
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Search Box */}
          <div className="relative w-full sm:w-56">
            <Search className="h-3.5 w-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              placeholder="Buscar examen..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 text-xs rounded-xl bg-slate-800 border border-slate-700 text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-cyan-500/50 focus:border-cyan-500 transition-all"
            />
          </div>

          {/* Out of Range Toggle */}
          <button
            onClick={() => setOnlyOutOfRange(!onlyOutOfRange)}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl border transition-all ${
              onlyOutOfRange
                ? 'bg-amber-950/60 text-amber-300 border-amber-500/50'
                : 'bg-slate-800 text-slate-300 border-slate-700 hover:bg-slate-700'
            }`}
          >
            <AlertTriangle className={`h-3 w-3 ${onlyOutOfRange ? 'text-amber-400' : 'text-slate-400'}`} />
            <span>Solo fuera de rango</span>
          </button>
        </div>
      </div>

      {/* Category Tabs */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-2 mb-4 scrollbar-thin">
        <button
          onClick={() => setSelectedCategory('ALL')}
          className={`px-3 py-1.5 text-xs font-medium rounded-lg whitespace-nowrap transition-all ${
            selectedCategory === 'ALL'
              ? 'bg-cyan-500 text-slate-950 font-semibold shadow-sm shadow-cyan-500/20'
              : 'bg-slate-800/80 text-slate-400 hover:text-slate-200 hover:bg-slate-800'
          }`}
        >
          Todos ({observations?.length || 0})
        </button>
        {categories.map((cat) => (
          <button
            key={cat}
            onClick={() => setSelectedCategory(cat)}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg whitespace-nowrap transition-all ${
              selectedCategory === cat
                ? 'bg-cyan-500 text-slate-950 font-semibold shadow-sm shadow-cyan-500/20'
                : 'bg-slate-800/80 text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* Table Container */}
      <div className="overflow-x-auto rounded-xl border border-slate-800/90 bg-slate-950/40">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="border-b border-slate-800 bg-slate-900/80 text-slate-400 font-semibold">
              <th className="py-3 px-3.5 sticky left-0 bg-slate-900/95 z-10 w-52 sm:w-64 min-w-[200px]">
                Examen / Analito
              </th>
              <th className="py-3 px-3 text-slate-400 w-32 min-w-[110px]">
                Referencia
              </th>
              {sampleDates.map((dStr) => (
                <th key={dStr} className="py-3 px-3 text-center min-w-[100px] text-slate-300">
                  <div className="font-semibold">{formatDateHeader(dStr)}</div>
                  <div className="text-[10px] text-slate-500 font-normal">{dStr}</div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {rows.length > 0 ? (
              rows.map((row) => (
                <tr
                  key={row.code}
                  onClick={() => onSelectAnalyte?.(row.code)}
                  className="hover:bg-slate-800/40 transition-colors group cursor-pointer"
                >
                  {/* Analyte Name */}
                  <td className="py-2.5 px-3.5 sticky left-0 bg-slate-950/90 group-hover:bg-slate-900/90 transition-colors z-10">
                    <div className="flex items-center gap-1.5">
                      <span className="font-medium text-slate-100 group-hover:text-cyan-300 transition-colors">
                        {row.name_es}
                      </span>
                      {row.hasOutOfRange && (
                        <span className="h-1.5 w-1.5 rounded-full bg-amber-400 shrink-0" title="Valor fuera de rango" />
                      )}
                    </div>
                    <div className="text-[10px] text-slate-500 flex items-center gap-1">
                      <span>{row.category}</span>
                      {row.unit && <span>• {row.unit}</span>}
                    </div>
                  </td>

                  {/* Reference Range */}
                  <td className="py-2.5 px-3 text-slate-400 font-mono text-[11px]">
                    {row.ref_text ? `${row.ref_text}` : '—'}
                  </td>

                  {/* Draw Values */}
                  {sampleDates.map((dStr) => {
                    const obs = row.valuesByDate[dStr];
                    if (!obs) {
                      return (
                        <td key={dStr} className="py-2.5 px-3 text-center text-slate-600">
                          —
                        </td>
                      );
                    }

                    const isOut = obs.out_of_range;
                    const val = obs.value_num !== null ? obs.value_num : obs.value_text;

                    return (
                      <td key={dStr} className="py-2.5 px-3 text-center">
                        {isOut ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md font-semibold text-xs bg-amber-950/70 text-amber-300 border border-amber-500/40">
                            {val}
                            {obs.ref_high && obs.value_num > obs.ref_high ? (
                              <ArrowUpRight className="h-3 w-3 text-amber-400" />
                            ) : obs.ref_low && obs.value_num < obs.ref_low ? (
                              <ArrowDownRight className="h-3 w-3 text-amber-400" />
                            ) : null}
                          </span>
                        ) : (
                          <span className="text-slate-200 font-medium">
                            {val}
                          </span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={sampleDates.length + 2} className="py-8 text-center text-slate-500 text-xs">
                  No se encontraron exámenes con los filtros seleccionados.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
