interface Props {
  minYear: number;
  maxYear: number;
  fromYear: number;
  toYear: number;
  onChange: (fromYear: number, toYear: number) => void;
}

// Occurrence time filter. Emits year bounds; App turns them into
// /api/occurrences?from=&to= and refetches live.
export default function TimeFilter({
  minYear,
  maxYear,
  fromYear,
  toYear,
  onChange,
}: Props) {
  const clamp = (v: number) => Math.min(maxYear, Math.max(minYear, v));

  return (
    <div className="timefilter">
      <div className="fieldlog__section-label">Occurrence window (year)</div>

      <input
        type="range"
        min={minYear}
        max={maxYear}
        value={fromYear}
        onChange={(e) => onChange(clamp(Number(e.target.value)), toYear)}
        aria-label="from year"
      />
      <input
        type="range"
        min={minYear}
        max={maxYear}
        value={toYear}
        onChange={(e) => onChange(fromYear, clamp(Number(e.target.value)))}
        aria-label="to year"
      />

      <div className="timefilter__row">
        <label htmlFor="from-year">from</label>
        <input
          id="from-year"
          type="number"
          min={minYear}
          max={maxYear}
          value={fromYear}
          onChange={(e) => onChange(clamp(Number(e.target.value)), toYear)}
        />
        <label htmlFor="to-year">to</label>
        <input
          id="to-year"
          type="number"
          min={minYear}
          max={maxYear}
          value={toYear}
          onChange={(e) => onChange(fromYear, clamp(Number(e.target.value)))}
        />
      </div>
    </div>
  );
}
